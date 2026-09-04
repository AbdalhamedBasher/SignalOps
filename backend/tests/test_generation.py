"""
Tests for generated briefings.

No test here calls the Claude API. The model is replaced by stubs, because the
things worth testing are the guardrails around it — that a fabricated citation
is refused, that a disabled feature degrades cleanly, and that what an engineer
was shown is recorded. Whether the prose is any good is an eval question, not a
unit-test one.
"""

import pytest
from fastapi.testclient import TestClient

from app import main
from app.generation import (
    BriefingDraft,
    BriefingUnavailable,
    NullBriefingGenerator,
    UngroundedBriefing,
    build_prompt,
    verify_citations,
)
from app.main import app
from app.models import GeneratedBriefing, Incident, Recommendation

client = TestClient(app)

BACKHAUL_INCIDENT = "INC-1001"


class StubGenerator:
    """Returns a fixed briefing, citing whatever it is told to cite."""

    def __init__(self, cited: list[str] | None = None) -> None:
        self.cited = cited
        self.calls: list[tuple[Incident, list[Recommendation]]] = []

    def generate(
        self, incident: Incident, recommendations: list[Recommendation]
    ) -> GeneratedBriefing:
        self.calls.append((incident, recommendations))

        cited = (
            self.cited
            if self.cited is not None
            else [recommendations[0].section.id]
        )

        return GeneratedBriefing(
            summary="The backhaul link failed and the rest followed from it.",
            first_actions=["Read the optical power levels at both ends."],
            cited_section_ids=cited,
            gaps=None,
            model="stub-model",
        )


class ExplodingGenerator:
    def __init__(self, error: Exception) -> None:
        self.error = error

    def generate(self, incident: Incident, recommendations: list[Recommendation]):
        raise self.error


def propose() -> list[dict]:
    return client.post(f"/api/incidents/{BACKHAUL_INCIDENT}/recommendations").json()


# --------------------------------------------------------------- the guardrail


def draft(cited: list[str]) -> BriefingDraft:
    return BriefingDraft(
        summary="s", first_actions=[], cited_section_ids=cited, gaps=None
    )


def test_citations_the_model_was_given_are_accepted() -> None:
    assert verify_citations(draft(["RBS-0001", "RBS-0004"]), {"RBS-0001", "RBS-0004"}) == [
        "RBS-0001",
        "RBS-0004",
    ]


def test_a_fabricated_citation_is_refused() -> None:
    """
    The failure this whole feature must not have.

    An engineer who follows a citation to a procedure that does not exist has
    been actively misled — worse than having received no briefing at all.
    """
    with pytest.raises(UngroundedBriefing) as caught:
        verify_citations(draft(["RBS-0001", "RBS-9999"]), {"RBS-0001"})

    assert "RBS-9999" in str(caught.value)


def test_citing_nothing_is_allowed() -> None:
    """A briefing that says the runbooks do not cover this is a useful answer."""
    assert verify_citations(draft([]), {"RBS-0001"}) == []


def test_the_prompt_contains_only_the_sections_that_were_retrieved() -> None:
    recommendations = [Recommendation(**item) for item in propose()]
    incident = Incident(
        **next(
            entry
            for entry in client.get("/api/incidents").json()
            if entry["id"] == BACKHAUL_INCIDENT
        )
    )

    prompt = build_prompt(incident, recommendations)

    for recommendation in recommendations:
        assert recommendation.section.id in prompt
        assert recommendation.section.heading in prompt

    # Alarms are presented oldest first, because the earliest one is the one
    # most likely to be the root cause.
    assert prompt.index("BACKHAUL_DOWN") < prompt.index("VOLTE_REG_FAILURE")


# ------------------------------------------------------------------ the routes


def test_briefings_are_unavailable_until_switched_on(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "briefing_generator", NullBriefingGenerator())
    propose()

    response = client.post(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing")

    assert response.status_code == 503
    assert "ENABLE_BRIEFINGS" in response.json()["detail"]


def test_a_generated_briefing_is_stored_and_returned(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(main, "briefing_generator", StubGenerator())
    propose()

    response = client.post(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing")

    assert response.status_code == 200

    briefing = response.json()
    assert briefing["id"].startswith("BRF-")
    assert briefing["model"] == "stub-model"
    assert briefing["cited_section_ids"]

    # And it is readable afterwards without regenerating.
    stored = client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing").json()
    assert stored["id"] == briefing["id"]


def test_the_model_is_only_ever_given_retrieved_sections(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    generator = StubGenerator()
    monkeypatch.setattr(main, "briefing_generator", generator)

    proposed = propose()
    client.post(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing")

    _, recommendations = generator.calls[0]

    assert {item.id for item in recommendations} == {item["id"] for item in proposed}


def test_an_ungrounded_briefing_is_refused_rather_than_shown(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "briefing_generator",
        ExplodingGenerator(UngroundedBriefing("cited RBS-9999")),
    )
    propose()

    response = client.post(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing")

    assert response.status_code == 502

    # Nothing was stored, so the dashboard has nothing to display.
    assert client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing").json() is None


def test_an_api_failure_is_reported_as_unavailable(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        main,
        "briefing_generator",
        ExplodingGenerator(BriefingUnavailable("Could not reach the Claude API.")),
    )
    propose()

    assert client.post(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing").status_code == 503


def test_generating_a_briefing_is_recorded_in_the_audit_trail(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """
    What an engineer was shown has to be reconstructable later, including which
    model wrote it.
    """
    monkeypatch.setattr(main, "briefing_generator", StubGenerator())
    propose()
    client.post(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing")

    audit = client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/audit").json()
    generated = next(
        event for event in audit if event["action"] == "briefing.generated"
    )

    assert generated["actor"] == "stub-model"
    assert "RBS-" in generated["detail"]


def test_an_incident_with_no_briefing_reads_as_null() -> None:
    assert client.get(f"/api/incidents/{BACKHAUL_INCIDENT}/briefing").json() is None


def test_a_briefing_for_an_unknown_incident_is_a_404() -> None:
    assert client.post("/api/incidents/INC-0000/briefing").status_code == 404
    assert client.get("/api/incidents/INC-0000/briefing").status_code == 404
