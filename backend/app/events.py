"""
Fan-out of incident changes to connected dashboards.

The tricky part is that alarms are ingested by ordinary synchronous request
handlers running in a thread pool, while WebSockets live on the event loop.
Publishing therefore has to cross from a worker thread into the loop, which is
what `call_soon_threadsafe` is for.
"""

import asyncio
import threading
from collections.abc import Iterator
from contextlib import contextmanager

from app.models import IncidentEvent

# A dashboard that cannot keep up is a dashboard nobody is watching. Holding a
# small buffer per connection bounds memory; beyond it we drop messages for
# that one client rather than letting a slow reader grow the queue forever.
MAX_PENDING_MESSAGES = 64


class IncidentBroadcaster:
    def __init__(self) -> None:
        self._subscribers: set[asyncio.Queue[str]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None
        # Guards the subscriber set, which is mutated from the event loop when
        # sockets connect and read from worker threads when alarms arrive.
        self._lock = threading.Lock()

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        """Remember the loop that worker threads must hand messages back to."""
        self._loop = loop

    @property
    def subscriber_count(self) -> int:
        with self._lock:
            return len(self._subscribers)

    @contextmanager
    def subscribe(self) -> Iterator[asyncio.Queue[str]]:
        queue: asyncio.Queue[str] = asyncio.Queue(maxsize=MAX_PENDING_MESSAGES)

        with self._lock:
            self._subscribers.add(queue)

        try:
            yield queue
        finally:
            with self._lock:
                self._subscribers.discard(queue)

    def publish(self, event: IncidentEvent) -> int:
        """
        Send an event to every connected dashboard.

        Safe to call from a synchronous request handler. Returns how many
        subscribers it was delivered to, which is what the tests assert on.
        """
        # Serialised once rather than per subscriber: every client receives
        # exactly the same bytes.
        payload = event.model_dump_json()

        with self._lock:
            targets = list(self._subscribers)

        if not targets:
            return 0

        loop = self._loop

        if loop is None:
            raise RuntimeError(
                "IncidentBroadcaster.publish was called before bind(); the "
                "application lifespan is responsible for binding the loop."
            )

        for queue in targets:
            loop.call_soon_threadsafe(_offer, queue, payload)

        return len(targets)


def _offer(queue: asyncio.Queue[str], payload: str) -> None:
    """
    Hand a message to one subscriber, giving up rather than blocking.

    This runs on the event loop, so waiting for room in a full queue would
    stall every other connection too.
    """
    try:
        queue.put_nowait(payload)
    except asyncio.QueueFull:
        pass


broadcaster = IncidentBroadcaster()
