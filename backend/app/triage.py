"""
Running the triage agent, and refusing to trust it blindly.

The agent itself lives in `agent.py`. This module owns the two things that
must be true regardless of which model is behind it:

1. Every runbook section the agent cites was actually given to it.
2. A failure — no key, no network, a refused answer — degrades to a clear
   message rather than taking the incident board down.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from app.agent import TriageDeps, TriageReport, build_agent, describe_incident
from app.models import GeneratedTriage, Incident, Recommendation
from app.network_intelligence import NetworkIntelligence

logger = logging.getLogger(__name__)


class UngroundedTriage(RuntimeError):
    """The agent cited a runbook section it was never given."""


class TriageUnavailable(RuntimeError):
    """Triage could not run: not configured, or the model call failed."""


class TriageService(Protocol):
    def triage(
        self,
        incident: Incident,
        recommendations: list[Recommendation],
        network: NetworkIntelligence,
    ) -> GeneratedTriage: ...


def verify_citations(report: TriageReport, allowed_ids: set[str]) -> list[str]:
    """
    Reject a report that cites a section the agent was not given.

    This is the guarantee behind the instruction. The prompt asks the agent to
    cite only what the runbook tool returned; this checks that it did. An
    engineer who follows a citation to a procedure that does not exist has been
    actively misled, which is worse than receiving no triage at all — so the
    whole report is discarded rather than shown with the bad citation removed.
    If one citation is invented, the prose around it cannot be trusted either.
    """
    cited = [section_id.strip() for section_id in report.cited_section_ids]
    invented = [section_id for section_id in cited if section_id not in allowed_ids]

    if invented:
        raise UngroundedTriage(
            f"The agent cited runbook sections it was not given: {invented}"
        )

    return cited


class GeminiTriageService:
    """Triage backed by Google Gemini through Pydantic AI."""

    def __init__(self, model_name: str, api_key: str) -> None:
        self._agent = build_agent(model_name, api_key)
        self._model_name = model_name

    def triage(
        self,
        incident: Incident,
        recommendations: list[Recommendation],
        network: NetworkIntelligence,
    ) -> GeneratedTriage:
        trace: list[str] = []
        deps = TriageDeps(
            incident=incident,
            recommendations=recommendations,
            network=network,
            trace=trace,
        )

        try:
            result = self._agent.run_sync(describe_incident(incident), deps=deps)
        except Exception as error:
            # Deliberately broad. Every failure mode of a remote model — auth,
            # rate limit, timeout, malformed output — has the same consequence
            # here: no triage. The board must keep working regardless.
            logger.exception("Triage agent run failed")

            raise TriageUnavailable(
                f"The triage agent could not complete: {error}"
            ) from error

        report = result.output
        allowed = {item.section.id for item in recommendations}

        return GeneratedTriage(
            verdict=report.verdict,
            summary=report.summary,
            evidence=report.evidence,
            first_actions=report.first_actions,
            cited_section_ids=verify_citations(report, allowed),
            gaps=report.gaps,
            model=self._model_name,
            trace=trace,
        )


class NullTriageService:
    """Used when no Gemini credentials are configured."""

    def triage(
        self,
        incident: Incident,
        recommendations: list[Recommendation],
        network: NetworkIntelligence,
    ) -> GeneratedTriage:
        raise TriageUnavailable(
            "The triage agent is not configured. Set GOOGLE_API_KEY (free from "
            "Google AI Studio) to enable it."
        )


def build_triage_service(*, api_key: str | None, model_name: str) -> TriageService:
    if not api_key:
        return NullTriageService()

    try:
        return GeminiTriageService(model_name, api_key)
    except Exception:
        # Runs at import. A triage agent that cannot be built is a missing
        # feature; raising here would take down the incident dashboard, which
        # is the part people rely on during an outage.
        logger.exception("Could not build the triage agent; triage disabled.")

        return NullTriageService()


def serialise(values: list[str]) -> str:
    return json.dumps(values)


def deserialise(raw: str) -> list[str]:
    loaded = json.loads(raw or "[]")

    return [str(item) for item in loaded] if isinstance(loaded, list) else []
