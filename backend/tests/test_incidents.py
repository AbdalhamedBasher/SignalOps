from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import COLLECTOR

client = TestClient(app)


def get_incident(incident_id: str) -> dict:
    """Look incidents up by id: board order is a presentation choice, not a
    contract tests should depend on."""
    incidents = client.get("/api/incidents").json()

    return next(incident for incident in incidents if incident["id"] == incident_id)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_incidents_are_returned_with_the_expected_contract() -> None:
    response = client.get("/api/incidents")

    assert response.status_code == 200

    incidents = response.json()
    assert len(incidents) == 3

    backhaul = next(
        incident for incident in incidents if incident["id"] == "INC-1001"
    )
    assert backhaul["severity"] == "critical"
    assert backhaul["affected_subscribers"] == 1240

    alarm_codes = {alarm["code"] for alarm in backhaul["alarms"]}
    assert alarm_codes == {
        "BACKHAUL_DOWN",
        "CELL_OUT_OF_SERVICE",
        "S1_LINK_FAILURE",
        "VOLTE_REG_FAILURE",
    }


def test_the_board_shows_the_most_recent_incident_first() -> None:
    incidents = client.get("/api/incidents").json()
    opened_timestamps = [incident["opened_at"] for incident in incidents]

    assert opened_timestamps == sorted(opened_timestamps, reverse=True)


def test_alarm_identifiers_are_unique_across_incidents() -> None:
    """An alarm belongs to exactly one incident, so its id must not repeat."""
    response = client.get("/api/incidents")

    alarm_ids = [
        alarm["id"] for incident in response.json() for alarm in incident["alarms"]
    ]

    assert len(alarm_ids) == len(set(alarm_ids))


def test_alarms_come_back_in_arrival_order_not_event_order() -> None:
    """
    The API promises arrival order, which is not chronological order.

    Both halves matter. Promising *an* order stops the answer depending on the
    query planner, and promising this particular one keeps the frontend
    responsible for putting the cascade back into causal sequence.
    """
    backhaul_alarms = get_incident("INC-1001")["alarms"]

    alarm_ids = [alarm["id"] for alarm in backhaul_alarms]
    assert alarm_ids == sorted(alarm_ids)

    occurred_timestamps = [alarm["occurred_at"] for alarm in backhaul_alarms]
    assert occurred_timestamps != sorted(occurred_timestamps)


def test_an_alarm_at_a_quiet_site_opens_a_new_incident() -> None:
    response = client.post(
        "/api/alarms",
        json={
            "site_id": "DMM-052",
            "code": "BACKHAUL_DOWN",
            "message": "Fiber backhaul link is unavailable",
            "occurred_at": "2026-08-30T10:00:00Z",
        },
        headers=COLLECTOR,
    )

    assert response.status_code == 201

    result = response.json()
    assert result["incident_created"] is True
    assert result["duplicate"] is False
    assert result["incident"]["site_id"] == "DMM-052"
    assert result["incident"]["severity"] == "critical"
    assert result["incident"]["affected_subscribers"] == 320
    assert len(result["incident"]["alarms"]) == 1

    assert len(client.get("/api/incidents").json()) == 4


def test_a_following_alarm_joins_the_incident_instead_of_creating_one() -> None:
    first = client.post(
        "/api/alarms",
        json={
            "site_id": "DMM-052",
            "code": "BACKHAUL_DOWN",
            "message": "Fiber backhaul link is unavailable",
            "occurred_at": "2026-08-30T10:00:00Z",
        },
        headers=COLLECTOR,
    )

    second = client.post(
        "/api/alarms",
        json={
            "site_id": "DMM-052",
            "code": "VOLTE_REG_FAILURE",
            "message": "VoLTE registrations are failing",
            "occurred_at": "2026-08-30T10:03:00Z",
        },
        headers=COLLECTOR,
    )

    assert second.status_code == 201

    result = second.json()
    assert result["incident_created"] is False
    assert result["incident"]["id"] == first.json()["incident"]["id"]
    assert len(result["incident"]["alarms"]) == 2

    # One fault, one incident: the board did not grow twice.
    assert len(client.get("/api/incidents").json()) == 4


def test_a_redelivered_alarm_is_recognised_and_not_counted_twice() -> None:
    payload = {
        "site_id": "DMM-052",
        "code": "BACKHAUL_DOWN",
        "message": "Fiber backhaul link is unavailable",
        "occurred_at": "2026-08-30T10:00:00Z",
        "external_id": "collector-abc-123",
    }

    first = client.post("/api/alarms", json=payload, headers=COLLECTOR)
    retry = client.post("/api/alarms", json=payload, headers=COLLECTOR)

    assert first.status_code == 201
    assert first.json()["duplicate"] is False

    # A retry is a success, not an error, but nothing new was recorded.
    assert retry.status_code == 200
    assert retry.json()["duplicate"] is True
    assert retry.json()["incident"]["id"] == first.json()["incident"]["id"]
    assert len(retry.json()["incident"]["alarms"]) == 1

    assert len(client.get("/api/incidents").json()) == 4


def test_an_alarm_without_a_timezone_is_rejected() -> None:
    response = client.post(
        "/api/alarms",
        json={
            "site_id": "DMM-052",
            "code": "BACKHAUL_DOWN",
            "message": "Fiber backhaul link is unavailable",
            "occurred_at": "2026-08-30T10:00:00",
        },
        headers=COLLECTOR,
    )

    assert response.status_code == 422
    assert "UTC offset" in response.text


def test_an_ingested_alarm_is_visible_on_the_incident_board() -> None:
    client.post(
        "/api/alarms",
        json={
            "site_id": "RUH-315",
            "code": "TEMPERATURE_HIGH",
            "message": "Cabinet temperature above threshold",
            "occurred_at": "2026-08-30T11:30:00Z",
        },
        headers=COLLECTOR,
    )

    incidents = client.get("/api/incidents").json()
    new_incident = next(
        incident for incident in incidents if incident["site_id"] == "RUH-315"
    )

    assert new_incident["title"] == "Site temperature alarm"
    assert new_incident["status"] == "active"
    assert new_incident["affected_subscribers"] == 880
