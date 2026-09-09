"""
Tests for the triage agent and the CAMARA network layer beneath it.

No test here calls Gemini or Nokia. The model is replaced by Pydantic AI's
TestModel, which exercises every tool the agent exposes — which is exactly what
needs proving: that the CAMARA APIs are tools the agent can call, not decoration.
"""

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from pydantic_ai.models.test import TestModel

from app import main
from app.agent import TriageDeps, TriageReport, build_agent, describe_incident
from app.main import app
from app.models import GeneratedTriage, Incident, Recommendation
from app.network_intelligence import (
    CongestionLevel,
    DataSource,
    EngineerLocation,
    LocationVerdict,
    ReachabilityStatus,
    SimulatedNetwork,
    devices_at,
    location_of,
)
from app.triage import TriageUnavailable, UngroundedTriage, verify_citations
from tests.conftest import ENGINEER

client = TestClient(app)

BACKHAUL_INCIDENT = "INC-1001"


# --------------------------------------------------------- the CAMARA layer


def test_a_site_in_a_critical_state_has_unreachable_devices() -> None:
    network = SimulatedNetwork(degraded_sites={"RUH-104": "critical"})

    reading = network.device_reachability("RUH-104")

    assert reading.devices
    assert all(
        device.status is ReachabilityStatus.NOT_CONNECTED
        for device in reading.devices
    )
    assert reading.source is DataSource.SIMULATOR


def test_a_healthy_site_has_reachable_devices() -> None:
    network = SimulatedNetwork(degraded_sites={})

    reading = network.device_reachability("RUH-104")

    assert reading.unreachable == []
    assert "0 of 3" in reading.summary


def test_readings_are_deterministic_so_a_demo_can_be_rehearsed() -> None:
    first = SimulatedNetwork(degraded_sites={"RUH-207": "high"})
    second = SimulatedNetwork(degraded_sites={"RUH-207": "high"})

    assert [d.status for d in first.device_reachability("RUH-207").devices] == [
        d.status for d in second.device_reachability("RUH-207").devices
    ]


def test_an_unknown_site_reports_no_devices_rather_than_inventing_them() -> None:
    network = SimulatedNetwork(degraded_sites={"XXX-999": "critical"})

    reading = network.device_reachability("XXX-999")

    assert reading.devices == []
    assert "cannot" in reading.summary or "No devices" in reading.summary


def test_congestion_tracks_the_state_of_the_site() -> None:
    degraded = SimulatedNetwork(degraded_sites={"RUH-207": "high"})
    quiet = SimulatedNetwork(degraded_sites={})

    assert degraded.congestion("RUH-207").level is CongestionLevel.HIGH
    assert quiet.congestion("RUH-207").level is CongestionLevel.LOW


def test_every_reading_says_where_it_came_from() -> None:
    """
    Simulated data must never be mistaken for live network data — by a judge,
    an engineer, or the agent itself.
    """
    network = SimulatedNetwork(degraded_sites={"RUH-104": "critical"})

    assert network.congestion("RUH-104").source is DataSource.SIMULATOR
    for device in network.device_reachability("RUH-104").devices:
        assert device.source is DataSource.SIMULATOR


def test_sites_on_the_incident_board_have_devices_registered() -> None:
    """Otherwise the agent has nothing to check and triage is always unknown."""
    for site_id in ["RUH-104", "RUH-207", "JED-031"]:
        assert devices_at(site_id), site_id


# ------------------------------------------------------------ the guardrail


def report(cited: list[str]) -> TriageReport:
    return TriageReport(verdict="confirmed", summary="s", cited_section_ids=cited)


def test_citations_the_agent_was_given_are_accepted() -> None:
    assert verify_citations(report(["RBS-0001"]), {"RBS-0001", "RBS-0002"}) == [
        "RBS-0001"
    ]


def test_a_fabricated_citation_is_refused() -> None:
    with pytest.raises(UngroundedTriage) as caught:
        verify_citations(report(["RBS-0001", "RBS-9999"]), {"RBS-0001"})

    assert "RBS-9999" in str(caught.value)


# ----------------------------------------------- the agent and its tools


def proposed_recommendations() -> list[Recommendation]:
    raw = client.post(
        f"/api/incidents/{BACKHAUL_INCIDENT}/recommendations", headers=ENGINEER
    ).json()

    return [Recommendation(**item) for item in raw]


def backhaul_incident() -> Incident:
    incidents = client.get("/api/incidents", headers=ENGINEER).json()

    return Incident(
        **next(item for item in incidents if item["id"] == BACKHAUL_INCIDENT)
    )


def test_the_agent_calls_the_camara_apis_rather_than_only_reading_runbooks() -> None:
    """
    The requirement the whole submission turns on: the network APIs are tools
    the agent invokes, not buttons a user presses.

    TestModel calls every tool the agent exposes, so this proves the CAMARA
    tools are reachable, correctly typed, and actually wired to the network
    client — without spending a Gemini request.
    """
    incident = backhaul_incident()
    recommendations = proposed_recommendations()
    trace: list[str] = []

    agent = build_agent("gemini-2.5-flash", api_key="not-used-by-testmodel")
    deps = TriageDeps(
        incident=incident,
        recommendations=recommendations,
        network=SimulatedNetwork(degraded_sites={incident.site_id: "critical"}),
        trace=trace,
    )

    with agent.override(model=TestModel()):
        result = agent.run_sync(describe_incident(incident), deps=deps)

    assert isinstance(result.output, TriageReport)

    joined = " ".join(trace)
    assert "Device Reachability" in joined
    assert "Congestion Insights" in joined
    assert "runbook section" in joined


def test_the_prompt_tells_the_agent_not_to_trust_the_alarm_count() -> None:
    prompt = describe_incident(backhaul_incident())

    assert "verify this against the network" in prompt
    # Alarms oldest first, so the root cause leads.
    assert prompt.index("BACKHAUL_DOWN") < prompt.index("VOLTE_REG_FAILURE")


# ----------------------------------------------------------------- routes


class StubTriage:
    def __init__(self, result: GeneratedTriage | Exception) -> None:
        self.result = result
        self.calls: list[tuple[Incident, list[Recommendation]]] = []

    def triage(self, incident, recommendations, network) -> GeneratedTriage:
        self.calls.append((incident, recommendations))

        if isinstance(self.result, Exception):
            raise self.result

        return self.result


def a_triage(cited: list[str]) -> GeneratedTriage:
    return GeneratedTriage(
        verdict="confirmed",
        summary="Backhaul is down and devices at the site are unreachable.",
        evidence=["3 of 3 devices at RUH-104 unreachable (CAMARA reachability)"],
        first_actions=["Read optical power at both ends."],
        cited_section_ids=cited,
        model="stub",
        trace=["Called CAMARA Device Reachability Status for RUH-104"],
    )


def test_triage_is_unavailable_until_a_key_is_configured(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from app.triage import NullTriageService  # noqa: PLC0415

    monkeypatch.setattr(main, "triage_service", NullTriageService())

    response = client.post(
        f"/api/incidents/{BACKHAUL_INCIDENT}/triage", headers=ENGINEER
    )

    assert response.status_code == 503
    assert "GOOGLE_API_KEY" in response.json()["detail"]


def test_a_triage_report_is_stored_and_readable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed = proposed_recommendations()
    monkeypatch.setattr(
        main, "triage_service", StubTriage(a_triage([proposed[0].section.id]))
    )

    response = client.post(
        f"/api/incidents/{BACKHAUL_INCIDENT}/triage", headers=ENGINEER
    )

    assert response.status_code == 200

    body = response.json()
    assert body["id"].startswith("TRI-")
    assert body["verdict"] == "confirmed"
    assert body["evidence"]
    assert body["trace"]

    stored = client.get(
        f"/api/incidents/{BACKHAUL_INCIDENT}/triage", headers=ENGINEER
    ).json()
    assert stored["id"] == body["id"]


def test_an_ungrounded_report_is_refused_rather_than_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "triage_service", StubTriage(UngroundedTriage("cited RBS-9999"))
    )
    proposed_recommendations()

    response = client.post(
        f"/api/incidents/{BACKHAUL_INCIDENT}/triage", headers=ENGINEER
    )

    assert response.status_code == 502
    assert (
        client.get(
            f"/api/incidents/{BACKHAUL_INCIDENT}/triage", headers=ENGINEER
        ).json()
        is None
    )


def test_a_model_failure_degrades_to_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main, "triage_service", StubTriage(TriageUnavailable("rate limited"))
    )

    assert (
        client.post(
            f"/api/incidents/{BACKHAUL_INCIDENT}/triage", headers=ENGINEER
        ).status_code
        == 503
    )


def test_running_triage_is_recorded_in_the_audit_trail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    proposed = proposed_recommendations()
    monkeypatch.setattr(
        main, "triage_service", StubTriage(a_triage([proposed[0].section.id]))
    )

    client.post(f"/api/incidents/{BACKHAUL_INCIDENT}/triage", headers=ENGINEER)

    audit = client.get(
        f"/api/incidents/{BACKHAUL_INCIDENT}/audit", headers=ENGINEER
    ).json()
    entry = next(event for event in audit if event["action"] == "triage.generated")

    assert entry["actor"] == "stub"
    assert "confirmed" in entry["detail"]


def test_triage_requires_authentication() -> None:
    bare = TestClient(app)

    assert bare.post(f"/api/incidents/{BACKHAUL_INCIDENT}/triage").status_code == 401
    assert bare.get(f"/api/incidents/{BACKHAUL_INCIDENT}/triage").status_code == 401


# ------------------------------------------------- location verification


def test_the_simulator_can_place_the_engineer_on_or_off_site() -> None:
    """
    Rehearsal needs both answers.

    Nokia's Simulator mode returns TRUE for every coordinate, so the local
    simulator is the only place a `FALSE` can be demonstrated.
    """
    network = SimulatedNetwork(degraded_sites={})
    results = {
        network.engineer_at_site(site).result
        for site in ["RUH-104", "RUH-207", "RUH-315", "JED-031", "JED-118", "DMM-052"]
    }

    assert LocationVerdict.TRUE in results
    assert LocationVerdict.FALSE in results


def test_engineer_location_is_deterministic() -> None:
    first = SimulatedNetwork(degraded_sites={}).engineer_at_site("RUH-104")
    second = SimulatedNetwork(degraded_sites={}).engineer_at_site("RUH-104")

    assert first.result is second.result
    assert first.device_id == second.device_id


def test_a_non_discriminating_reading_says_so_in_its_own_summary() -> None:
    """
    The guard against the demo's worst failure: presenting a meaningless TRUE
    as proof an engineer arrived. Measured against the live API, which answered
    TRUE for Riyadh, Sydney and Reykjavik alike.
    """
    reading = EngineerLocation(
        site_id="RUH-104",
        device_id="+3670123457",
        result=LocationVerdict.TRUE,
        source=DataSource.NOKIA_NETWORK_AS_CODE,
        checked_at=datetime(2026, 9, 9, 10, 0, tzinfo=UTC),
        discriminating=False,
    )

    assert "Simulator mode" in reading.summary
    assert "unverified" in reading.summary.lower()


def test_a_discriminating_reading_states_the_answer_plainly() -> None:
    reading = EngineerLocation(
        site_id="RUH-104",
        device_id="+3670123457",
        result=LocationVerdict.FALSE,
        source=DataSource.SIMULATOR,
        checked_at=datetime(2026, 9, 9, 10, 0, tzinfo=UTC),
        discriminating=True,
    )

    assert "NOT within" in reading.summary
    assert "Simulator mode" not in reading.summary


def test_every_site_on_the_board_has_coordinates_to_verify_against() -> None:
    for site_id in ["RUH-104", "RUH-207", "JED-031"]:
        assert location_of(site_id) is not None, site_id


def test_the_agent_can_call_all_three_camara_tools() -> None:
    """The orchestration claim, now across three CAMARA APIs rather than two."""
    incident = backhaul_incident()
    trace: list[str] = []

    agent = build_agent("gemini-flash-lite-latest", api_key="not-used-by-testmodel")
    deps = TriageDeps(
        incident=incident,
        recommendations=proposed_recommendations(),
        network=SimulatedNetwork(degraded_sites={incident.site_id: "critical"}),
        trace=trace,
    )

    with agent.override(model=TestModel()):
        agent.run_sync(describe_incident(incident), deps=deps)

    joined = " ".join(trace)
    assert "Device Reachability" in joined
    assert "Congestion Insights" in joined
    assert "Location Verification" in joined
