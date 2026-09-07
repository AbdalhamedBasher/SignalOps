"""
Tests for the recommendation workflow: propose, decide, and record.

The point of this slice is that guidance reaches an engineer with a citation
and does not become action without their decision. These tests are mostly about
that guarantee rather than about retrieval quality.
"""

from fastapi.testclient import TestClient

from app.main import app
from tests.conftest import COLLECTOR, SUPERVISOR

client = TestClient(app)

# INC-1001 in the seed data raised BACKHAUL_DOWN, CELL_OUT_OF_SERVICE,
# S1_LINK_FAILURE and VOLTE_REG_FAILURE, so it matches several runbooks.
BACKHAUL_INCIDENT = "INC-1001"


def propose(incident_id: str = BACKHAUL_INCIDENT) -> list[dict]:
    response = client.post(f"/api/incidents/{incident_id}/recommendations")

    assert response.status_code == 200

    return response.json()


def test_proposals_are_returned_with_a_traceable_citation() -> None:
    recommendations = propose()

    assert recommendations

    for recommendation in recommendations:
        section = recommendation["section"]

        assert section["runbook_title"]
        assert section["heading"]
        assert section["source_name"].endswith(".md")
        assert section["body"]
        assert recommendation["matched_codes"]
        assert recommendation["status"] == "proposed"


def test_every_proposal_matches_an_alarm_the_incident_actually_raised() -> None:
    incident = client.get("/api/incidents").json()
    raised = {
        alarm["code"]
        for entry in incident
        if entry["id"] == BACKHAUL_INCIDENT
        for alarm in entry["alarms"]
    }

    for recommendation in propose():
        assert set(recommendation["matched_codes"]).issubset(raised)


def test_proposing_twice_does_not_duplicate_recommendations() -> None:
    first = propose()
    second = propose()

    assert [item["id"] for item in first] == [item["id"] for item in second]


def test_an_engineer_can_approve_a_recommendation() -> None:
    recommendation = propose()[0]

    response = client.post(
        f"/api/recommendations/{recommendation['id']}/approve",
        json={"note": "Matches what we saw on site."},
    )

    assert response.status_code == 200

    decided = response.json()
    assert decided["status"] == "approved"
    assert decided["decided_by"] == "nadia.k"
    assert decided["decided_at"] is not None


def test_an_engineer_can_approve_with_modified_steps() -> None:
    recommendation = propose()[0]

    response = client.post(
        f"/api/recommendations/{recommendation['id']}/approve",
        json={
            "modified_steps": "Skipped step 2, the far end was already down.",
        },
    )

    assert response.status_code == 200
    assert response.json()["modified_steps"].startswith("Skipped step 2")

    audit = client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/audit").json()
    actions = [event["action"] for event in audit]

    assert "recommendation.approved_with_modification" in actions


def test_an_engineer_can_reject_a_recommendation() -> None:
    recommendation = propose()[0]

    response = client.post(
        f"/api/recommendations/{recommendation['id']}/reject",
        json={"note": "Already ruled out transport."},
    )

    assert response.status_code == 200

    decided = response.json()
    assert decided["status"] == "rejected"
    # A rejection must not quietly carry modified steps forward as guidance.
    assert decided["modified_steps"] is None


def test_a_decision_is_attributed_to_the_token_not_the_request_body() -> None:
    """
    The whole point of putting authentication under this.

    A caller cannot decide as somebody else, however they fill in the body:
    `decided_by` is not a field the API reads.
    """
    recommendation = propose()[0]

    response = client.post(
        f"/api/recommendations/{recommendation['id']}/approve",
        json={"decided_by": "someone.else", "note": "Trying to sign as another."},
        headers=SUPERVISOR,
    )

    assert response.status_code == 200
    # Signed in as sam.o, so sam.o is who decided — not the name in the body.
    assert response.json()["decided_by"] == "sam.o"


def test_proposing_records_the_proposal_in_the_audit_trail() -> None:
    propose()

    audit = client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/audit").json()

    assert audit
    assert all(event["action"] == "recommendation.proposed" for event in audit)
    assert all(event["actor"] == "signalops" for event in audit)


def test_the_audit_trail_records_who_decided_and_when() -> None:
    recommendation = propose()[0]

    client.post(
        f"/api/recommendations/{recommendation['id']}/reject",
        json={"note": "Not applicable at this site."},
        headers=SUPERVISOR,
    )

    audit = client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/audit").json()
    rejection = next(
        event for event in audit if event["action"] == "recommendation.rejected"
    )

    assert rejection["actor"] == "sam.o"
    assert rejection["recommendation_id"] == recommendation["id"]
    assert rejection["detail"] == "Not applicable at this site."
    assert rejection["occurred_at"].endswith("Z")


def test_the_audit_trail_is_append_only_across_decisions() -> None:
    """A later decision adds to the record rather than replacing what it said."""
    recommendation = propose()[0]
    before = len(client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/audit").json())

    client.post(
        f"/api/recommendations/{recommendation['id']}/approve",
        json={},
    )
    client.post(
        f"/api/recommendations/{recommendation['id']}/reject",
        json={"note": "Changed our minds."},
    )

    audit = client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/audit").json()

    assert len(audit) == before + 2
    assert audit[-2]["action"] == "recommendation.approved"
    assert audit[-1]["action"] == "recommendation.rejected"


def test_an_unknown_incident_is_a_404_not_an_empty_list() -> None:
    assert client.get("/api/incidents/INC-0000/recommendations").status_code == 404
    assert client.post("/api/incidents/INC-0000/recommendations").status_code == 404
    assert client.get("/api/incidents/INC-0000/audit").status_code == 404


def test_deciding_on_an_unknown_recommendation_is_a_404() -> None:
    response = client.post(
        "/api/recommendations/REC-9999/approve", json={}
    )

    assert response.status_code == 404


def test_an_incident_with_no_matching_runbook_gets_no_recommendations() -> None:
    client.post(
        "/api/alarms",
        json={
            "site_id": "DMM-052",
            "code": "SOMETHING_UNCATALOGUED",
            "message": "An alarm nobody has written a procedure for",
            "occurred_at": "2026-08-30T10:00:00Z",
        },
        headers=COLLECTOR,
    )

    incidents = client.get("/api/incidents").json()
    new_incident = next(
        incident for incident in incidents if incident["site_id"] == "DMM-052"
    )

    assert propose(new_incident["id"]) == []
