"""Tests for the live incident feed."""

import json

from fastapi.testclient import TestClient

from app.events import IncidentBroadcaster
from app.main import app

BACKHAUL_AT_QUIET_SITE = {
    "site_id": "DMM-052",
    "code": "BACKHAUL_DOWN",
    "message": "Fiber backhaul link is unavailable",
    "occurred_at": "2026-08-30T10:00:00Z",
}


def test_opening_an_incident_is_announced_to_a_connected_dashboard() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws/incidents") as websocket:
            client.post("/api/alarms", json=BACKHAUL_AT_QUIET_SITE)

            event = json.loads(websocket.receive_text())

    assert event["type"] == "incident.opened"
    assert event["incident"]["site_id"] == "DMM-052"
    assert event["incident"]["severity"] == "critical"


def test_a_following_alarm_is_announced_as_an_update() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws/incidents") as websocket:
            client.post("/api/alarms", json=BACKHAUL_AT_QUIET_SITE)
            opened = json.loads(websocket.receive_text())

            client.post(
                "/api/alarms",
                json={
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

    with TestClient(app) as client:
        with client.websocket_connect("/ws/incidents") as websocket:
            client.post("/api/alarms", json=payload)
            first = json.loads(websocket.receive_text())

            retry = client.post("/api/alarms", json=payload)
            assert retry.status_code == 200

            # Prove nothing followed by sending a genuinely new alarm and
            # checking that *it* is the very next message on the socket.
            client.post(
                "/api/alarms",
                json={
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
    with TestClient(app) as client:
        with (
            client.websocket_connect("/ws/incidents") as first_screen,
            client.websocket_connect("/ws/incidents") as second_screen,
        ):
            client.post("/api/alarms", json=BACKHAUL_AT_QUIET_SITE)

            seen_by_first = json.loads(first_screen.receive_text())
            seen_by_second = json.loads(second_screen.receive_text())

    assert seen_by_first == seen_by_second


def test_a_disconnected_dashboard_stops_being_a_subscriber() -> None:
    with TestClient(app) as client:
        with client.websocket_connect("/ws/incidents"):
            pass

        # Publishing to nobody must not raise, and must not keep the queue of a
        # socket that has gone away.
        with client.websocket_connect("/ws/incidents") as websocket:
            client.post("/api/alarms", json=BACKHAUL_AT_QUIET_SITE)
            assert json.loads(websocket.receive_text())["type"] == "incident.opened"


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
