"""
In-memory incident storage.

This is the seam where persistence will eventually go (Slice 4). Everything
that knows *how* incidents are kept lives here; the correlation rules and the
route handlers do not. Swapping this for PostgreSQL should not require either
of them to change.
"""

import threading
from collections.abc import Iterable, Iterator, Sequence
from itertools import count

from app.catalog import alarm_definition
from app.correlation import attach_alarm, find_correlated_incident, open_incident
from app.models import Alarm, AlarmIngestResult, AlarmSubmission, Incident


def _numbers_after(existing: Iterable[str], prefix: str) -> Iterator[int]:
    """Continue an id sequence above whatever the seed data already used."""
    highest = 0

    for identifier in existing:
        suffix = identifier.removeprefix(prefix)
        if suffix != identifier and suffix.isdigit():
            highest = max(highest, int(suffix))

    return count(highest + 1)


class IncidentStore:
    def __init__(self, seed: Sequence[Incident] = ()) -> None:
        # FastAPI runs synchronous handlers in a thread pool, so two alarms can
        # be ingested at the same moment. Without this lock, concurrent
        # correlation could hand out one id twice or lose an append.
        self._lock = threading.Lock()
        self._incidents: list[Incident] = []
        self._incident_id_by_external_id: dict[str, str] = {}
        self._incident_numbers: Iterator[int] = count(1)
        self._alarm_numbers: Iterator[int] = count(1)

        self.reset(seed)

    def reset(self, seed: Sequence[Incident]) -> None:
        """Reseed the store. Used by tests to get a clean slate per case."""
        with self._lock:
            self._incidents = [incident.model_copy(deep=True) for incident in seed]
            self._incident_id_by_external_id = {
                alarm.external_id: incident.id
                for incident in self._incidents
                for alarm in incident.alarms
                if alarm.external_id is not None
            }
            self._incident_numbers = _numbers_after(
                (incident.id for incident in self._incidents), "INC-"
            )
            self._alarm_numbers = _numbers_after(
                (alarm.id for incident in self._incidents for alarm in incident.alarms),
                "ALM-",
            )

    def list_incidents(self) -> list[Incident]:
        """Hand out copies so callers cannot mutate stored state by accident."""
        with self._lock:
            return [incident.model_copy(deep=True) for incident in self._incidents]

    def ingest(self, submission: AlarmSubmission) -> AlarmIngestResult:
        with self._lock:
            duplicate_of = self._find_duplicate(submission)
            if duplicate_of is not None:
                return AlarmIngestResult(
                    incident=duplicate_of.model_copy(deep=True),
                    incident_created=False,
                    duplicate=True,
                )

            alarm = Alarm(
                id=f"ALM-{next(self._alarm_numbers):04d}",
                site_id=submission.site_id,
                code=submission.code,
                message=submission.message,
                severity=alarm_definition(submission.code).severity,
                occurred_at=submission.occurred_at,
                external_id=submission.external_id,
            )

            match = find_correlated_incident(self._incidents, alarm)

            if match is None:
                incident = open_incident(
                    f"INC-{next(self._incident_numbers):04d}", alarm
                )
                self._incidents.append(incident)
                incident_created = True
            else:
                incident = attach_alarm(match, alarm)
                incident_created = False

            if alarm.external_id is not None:
                self._incident_id_by_external_id[alarm.external_id] = incident.id

            return AlarmIngestResult(
                incident=incident.model_copy(deep=True),
                incident_created=incident_created,
                duplicate=False,
            )

    def _find_duplicate(self, submission: AlarmSubmission) -> Incident | None:
        """
        Detect a redelivery of an alarm we have already ingested.

        Collectors retry, and a retried alarm must not be counted twice: it
        would inflate the incident's alarm list and could drag its severity or
        its apparent start time around. Identity comes from the sender, since
        only the sender knows that two deliveries describe one event.
        """
        if submission.external_id is None:
            return None

        incident_id = self._incident_id_by_external_id.get(submission.external_id)
        if incident_id is None:
            return None

        return next(
            (
                incident
                for incident in self._incidents
                if incident.id == incident_id
            ),
            None,
        )
