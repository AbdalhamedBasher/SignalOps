from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_incidents_are_returned_with_the_expected_contract() -> None:
    response = client.get("/api/incidents")

    assert response.status_code == 200

    incidents = response.json()
    assert len(incidents) == 3
    assert incidents[0]["id"] == "INC-1001"
    assert incidents[0]["severity"] == "critical"
    assert incidents[0]["affected_subscribers"] == 1240

    alarm_codes = {alarm["code"] for alarm in incidents[0]["alarms"]}
    assert alarm_codes == {
        "BACKHAUL_DOWN",
        "CELL_OUT_OF_SERVICE",
        "S1_LINK_FAILURE",
        "VOLTE_REG_FAILURE",
    }


def test_alarm_identifiers_are_unique_across_incidents() -> None:
    """An alarm belongs to exactly one incident, so its id must not repeat."""
    response = client.get("/api/incidents")

    alarm_ids = [
        alarm["id"] for incident in response.json() for alarm in incident["alarms"]
    ]

    assert len(alarm_ids) == len(set(alarm_ids))


def test_the_api_does_not_promise_a_chronological_alarm_order() -> None:
    """
    Alarms are stored in arrival order, not event order. This test pins that
    fact down so nobody assumes ordering is guaranteed by the API: the
    frontend is the layer responsible for sorting them for display.
    """
    response = client.get("/api/incidents")

    backhaul_alarms = response.json()[0]["alarms"]
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
    )

    second = client.post(
        "/api/alarms",
        json={
            "site_id": "DMM-052",
            "code": "VOLTE_REG_FAILURE",
            "message": "VoLTE registrations are failing",
            "occurred_at": "2026-08-30T10:03:00Z",
        },
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

    first = client.post("/api/alarms", json=payload)
    retry = client.post("/api/alarms", json=payload)

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
    )

    incidents = client.get("/api/incidents").json()
    new_incident = next(
        incident for incident in incidents if incident["site_id"] == "RUH-315"
    )

    assert new_incident["title"] == "Site temperature alarm"
    assert new_incident["status"] == "active"
    assert new_incident["affected_subscribers"] == 880
