"""
Tests for authentication and roles.

The rules themselves (hashing, token encoding, role implication) are tested
without a web framework; the routes are then checked for who they let in.
"""

from datetime import UTC, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.security import (
    InvalidToken,
    Role,
    hash_password,
    issue_token,
    read_token,
    satisfies,
    verify_password,
)
from tests.conftest import COLLECTOR, ENGINEER, SUPERVISOR

client = TestClient(app)

SECRET = "test-signing-secret"


# ------------------------------------------------------------------ the rules


def test_a_password_is_never_stored_in_a_readable_form() -> None:
    stored = hash_password("correct horse battery staple")

    assert "correct horse" not in stored
    assert stored.startswith("$argon2")


def test_the_right_password_verifies_and_the_wrong_one_does_not() -> None:
    stored = hash_password("correct horse battery staple")

    assert verify_password("correct horse battery staple", stored)
    assert not verify_password("Correct horse battery staple", stored)
    assert not verify_password("", stored)


def test_the_same_password_hashes_differently_every_time() -> None:
    """
    Argon2 salts each hash. Two people with the same password must not have
    the same stored value, or one leak reveals both.
    """
    assert hash_password("same input") != hash_password("same input")


def test_verifying_against_a_corrupt_hash_fails_rather_than_raising() -> None:
    assert not verify_password("anything", "not-a-hash")


def test_a_token_round_trips() -> None:
    token = issue_token(username="nadia.k", role=Role.ENGINEER, secret=SECRET)

    assert read_token(token, secret=SECRET) == ("nadia.k", Role.ENGINEER)


def test_a_token_signed_with_another_secret_is_refused() -> None:
    token = issue_token(username="nadia.k", role=Role.SUPERVISOR, secret="other-secret")

    with pytest.raises(InvalidToken):
        read_token(token, secret=SECRET)


def test_an_expired_token_is_refused() -> None:
    token = issue_token(
        username="nadia.k",
        role=Role.ENGINEER,
        secret=SECRET,
        now=datetime.now(UTC) - timedelta(days=2),
    )

    with pytest.raises(InvalidToken):
        read_token(token, secret=SECRET)


def test_an_unsigned_token_is_refused() -> None:
    """
    The classic JWT attack: set the algorithm to "none", drop the signature,
    and claim to be anyone. Pinning `algorithms` on decode is what stops it.
    """
    import jwt  # noqa: PLC0415

    forged = jwt.encode(
        {"sub": "sam.o", "role": "supervisor"}, key="", algorithm="none"
    )

    with pytest.raises(InvalidToken):
        read_token(forged, secret=SECRET)


def test_a_supervisor_can_act_as_an_engineer_but_not_the_reverse() -> None:
    assert satisfies(Role.SUPERVISOR, Role.ENGINEER)
    assert satisfies(Role.SUPERVISOR, Role.SUPERVISOR)
    assert not satisfies(Role.ENGINEER, Role.SUPERVISOR)

    # A collector is a machine and is not a junior engineer.
    assert not satisfies(Role.COLLECTOR, Role.ENGINEER)
    assert not satisfies(Role.ENGINEER, Role.COLLECTOR)


# ----------------------------------------------------------------- the routes


def test_signing_in_returns_a_token_and_who_you_are() -> None:
    response = client.post(
        "/api/auth/login",
        json={"username": "nadia.k", "password": "engineer-dev-password"},
    )

    assert response.status_code == 200

    body = response.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"] == {
        "username": "nadia.k",
        "display_name": "Nadia Karim",
        "role": "engineer",
    }
    # A password must not come back out, in any form.
    assert "password" not in response.text


def test_a_wrong_password_and_an_unknown_user_are_indistinguishable() -> None:
    """
    Different answers here would let anyone enumerate valid usernames.
    """
    wrong_password = client.post(
        "/api/auth/login",
        json={"username": "nadia.k", "password": "not-the-password"},
    )
    unknown_user = client.post(
        "/api/auth/login",
        json={"username": "nobody.here", "password": "not-the-password"},
    )

    assert wrong_password.status_code == unknown_user.status_code == 401
    assert wrong_password.json() == unknown_user.json()


def test_the_board_is_not_public() -> None:
    bare = TestClient(app)

    assert bare.get("/api/incidents").status_code == 401
    assert bare.get("/api/incidents/INC-1001/recommendations").status_code == 401
    assert bare.get("/api/incidents/INC-1001/audit").status_code == 401
    assert bare.post("/api/incidents/INC-1001/triage").status_code == 401


def test_health_stays_open_because_load_balancers_have_no_credentials() -> None:
    assert TestClient(app).get("/health").status_code == 200


def test_a_garbled_authorization_header_is_rejected() -> None:
    for header in ["", "Bearer", "Bearer   ", "Basic abc", "nonsense"]:
        response = client.get(
            "/api/incidents", headers={"Authorization": header}
        )

        assert response.status_code == 401, header


def test_an_engineer_cannot_pretend_to_be_a_collector() -> None:
    """Only machine principals may inject network events."""
    response = client.post(
        "/api/alarms",
        json={
            "site_id": "DMM-052",
            "code": "BACKHAUL_DOWN",
            "message": "Fabricated by a human",
            "occurred_at": "2026-08-30T10:00:00Z",
        },
        headers=ENGINEER,
    )

    assert response.status_code == 403


def test_a_collector_cannot_approve_anything() -> None:
    """And a stolen collector token is not a way into the approval workflow."""
    client.post("/api/incidents/INC-1001/recommendations", headers=ENGINEER)

    response = client.post(
        "/api/recommendations/REC-0001/approve", json={}, headers=COLLECTOR
    )

    assert response.status_code == 403


def test_me_reports_the_signed_in_user() -> None:
    response = client.get("/api/auth/me", headers=SUPERVISOR)

    assert response.status_code == 200
    assert response.json()["role"] == "supervisor"


# ------------------------------------------------- the supervisor-gated rule


def supervisor_gated_recommendation() -> dict:
    proposed = client.post(
        "/api/incidents/INC-1001/recommendations", headers=ENGINEER
    ).json()

    return next(
        item for item in proposed if item["section"]["requires_supervisor"]
    )


def test_some_runbook_sections_declare_that_they_need_a_supervisor() -> None:
    """The authority comes from the runbook text, not from this codebase."""
    recommendation = supervisor_gated_recommendation()

    assert recommendation["section"]["heading"] in {
        "Never reset equipment blind",
        "Protect emergency calling",
    }


def test_an_engineer_cannot_approve_a_supervisor_gated_procedure() -> None:
    recommendation = supervisor_gated_recommendation()

    response = client.post(
        f"/api/recommendations/{recommendation['id']}/approve",
        json={},
        headers=ENGINEER,
    )

    assert response.status_code == 403
    assert "supervisor" in response.json()["detail"]


def test_a_supervisor_can_approve_a_supervisor_gated_procedure() -> None:
    recommendation = supervisor_gated_recommendation()

    response = client.post(
        f"/api/recommendations/{recommendation['id']}/approve",
        json={},
        headers=SUPERVISOR,
    )

    assert response.status_code == 200
    assert response.json()["decided_by"] == "sam.o"


def test_an_engineer_can_still_reject_a_supervisor_gated_procedure() -> None:
    """
    Declining to act is always safe. Requiring escalation to say "not this
    one" would slow an outage down for no gain.
    """
    recommendation = supervisor_gated_recommendation()

    response = client.post(
        f"/api/recommendations/{recommendation['id']}/reject",
        json={"note": "Transport is the fault here."},
        headers=ENGINEER,
    )

    assert response.status_code == 200
    assert response.json()["status"] == "rejected"
