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
