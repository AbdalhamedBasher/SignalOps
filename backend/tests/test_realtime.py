"""Tests for the live incident feed."""

import json

import pytest
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from app.events import IncidentBroadcaster
from app.main import app
from tests.conftest import COLLECTOR, ENGINEER, feed_url

BACKHAUL_AT_QUIET_SITE = {
    "site_id": "DMM-052",
    "code": "BACKHAUL_DOWN",
    "message": "Fiber backhaul link is unavailable",
    "occurred_at": "2026-08-30T10:00:00Z",
}


def post_alarm(client: TestClient, payload: dict):
    return client.post("/api/alarms", json=payload, headers=COLLECTOR)


def test_opening_an_incident_is_announced_to_a_connected_dashboard() -> None:
    with TestClient(app, headers=ENGINEER) as client:
        with client.websocket_connect(feed_url()) as websocket:
            post_alarm(client, BACKHAUL_AT_QUIET_SITE)

            event = json.loads(websocket.receive_text())

    assert event["type"] == "incident.opened"
    assert event["incident"]["site_id"] == "DMM-052"
    assert event["incident"]["severity"] == "critical"


def test_a_following_alarm_is_announced_as_an_update() -> None:
    with TestClient(app, headers=ENGINEER) as client:
        with client.websocket_connect(feed_url()) as websocket:
            post_alarm(client, BACKHAUL_AT_QUIET_SITE)
            opened = json.loads(websocket.receive_text())

            post_alarm(
                client,
                {
                    **BACKHAUL_AT_QUIET_SITE,
                    "code": "VOLTE_REG_FAILURE",
                    "message": "VoLTE registrations are failing",
                    "occurred_at": "2026-08-30T10:03:00Z",
                },
            )
            updated = json.loads(websocket.receive_text())

    assert opened["type"] == "incident.opened"
    assert updated["type"] == "incident.updated"
    assert updated["incident"]["id"] == opened["incident"]["id"]
    assert len(updated["incident"]["alarms"]) == 2


def test_a_redelivered_alarm_is_not_announced() -> None:
    """
    A duplicate changes nothing, so it must not reach the dashboards.

    Announcing it would make every connected screen flash an update for an
    event that did not happen.
    """
    payload = {**BACKHAUL_AT_QUIET_SITE, "external_id": "collector-abc-123"}

    with TestClient(app, headers=ENGINEER) as client:
        with client.websocket_connect(feed_url()) as websocket:
            post_alarm(client, payload)
            first = json.loads(websocket.receive_text())

            retry = post_alarm(client, payload)
            assert retry.status_code == 200

            # Prove nothing followed by sending a genuinely new alarm and
            # checking that *it* is the very next message on the socket.
            post_alarm(
                client,
                {
                    **BACKHAUL_AT_QUIET_SITE,
                    "code": "TEMPERATURE_HIGH",
                    "message": "Cabinet temperature above threshold",
                    "occurred_at": "2026-08-30T10:05:00Z",
                },
            )
            following = json.loads(websocket.receive_text())

    assert first["incident"]["alarms"][0]["code"] == "BACKHAUL_DOWN"
    assert len(following["incident"]["alarms"]) == 2


def test_every_connected_dashboard_receives_the_same_event() -> None:
    with TestClient(app, headers=ENGINEER) as client:
        with (
            client.websocket_connect(feed_url()) as first_screen,
            client.websocket_connect(feed_url()) as second_screen,
        ):
            post_alarm(client, BACKHAUL_AT_QUIET_SITE)

            seen_by_first = json.loads(first_screen.receive_text())
            seen_by_second = json.loads(second_screen.receive_text())

    assert seen_by_first == seen_by_second


def test_a_disconnected_dashboard_stops_being_a_subscriber() -> None:
    with TestClient(app, headers=ENGINEER) as client:
        with client.websocket_connect(feed_url()):
            pass

        # Publishing to nobody must not raise, and must not keep the queue of a
        # socket that has gone away.
        with client.websocket_connect(feed_url()) as websocket:
            post_alarm(client, BACKHAUL_AT_QUIET_SITE)
            assert json.loads(websocket.receive_text())["type"] == "incident.opened"


def test_an_unauthenticated_socket_is_closed_before_it_subscribes() -> None:
    """
    Incident data is not public, and a browser cannot send an Authorization
    header on a WebSocket handshake — so the token travels in the query string
    and is checked before `accept()`.
    """
    with TestClient(app, headers=ENGINEER) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect("/ws/incidents") as websocket:
                websocket.receive_text()


def test_a_socket_with_a_forged_token_is_closed() -> None:
    with TestClient(app, headers=ENGINEER) as client:
        with pytest.raises(WebSocketDisconnect):
            with client.websocket_connect(
                "/ws/incidents?token=not-a-real-token"
            ) as websocket:
                websocket.receive_text()


def test_publishing_to_nobody_is_harmless() -> None:
    """An unbound broadcaster with no subscribers has no work to do."""
    unbound = IncidentBroadcaster()

    assert unbound.subscriber_count == 0


# TODO(you): the case above is the easy half. `publish()` raises a RuntimeError
# when it has subscribers but no bound loop, and nothing tests that — so the
# guard could be deleted and the suite would stay green.
# Write `test_publishing_with_subscribers_but_no_loop_is_a_clear_error`:
# construct an IncidentBroadcaster, put an `asyncio.Queue()` straight into its
# `_subscribers` set (reaching into a private attribute is acceptable here
# because you are deliberately building a state the public API prevents), then
# assert `pytest.raises(RuntimeError)` when you publish an IncidentEvent.
# Hint: build the event with any incident, e.g. from `app.data.SEED_INCIDENTS`.
