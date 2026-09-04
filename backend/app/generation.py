"""
Generated incident briefings.

This is the first place an LLM appears in SignalOps, and it deliberately sits
*on top of* retrieval rather than in place of it. Deterministic matching still
decides which approved procedures are relevant; the model only writes the short
orientation an engineer reads before opening them.

Two things keep that honest:

1. The model is given the retrieved sections and told it may use nothing else.
2. Every section id it cites is checked against the ones it was actually given.
   A citation to anything else is a fabrication, and the briefing is discarded
   rather than shown.

The second is the one that matters. A prompt is a request; the check is a
guarantee.
"""

from __future__ import annotations

import json
import logging
from typing import Protocol

from pydantic import BaseModel, Field

from app.models import GeneratedBriefing, Incident, Recommendation

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """\
You are assisting a telecom network operations engineer during a live incident.

You will be given one incident and a numbered list of sections from runbooks \
that the operator's own engineering team has written and approved. Your job is \
to write a short orientation that helps the engineer decide what to look at \
first. You are not the decision maker and you never act on the network.

Rules you must follow exactly:

- Use ONLY the runbook sections provided. Do not add steps, checks, thresholds, \
or escalation paths from your own knowledge, however standard they seem. If the \
sections do not cover something, say so plainly.
- Cite the sections you drew on by their exact id (for example RBS-0003). Only \
cite ids that appear in the input.
- Prefer the procedure that addresses the earliest alarm, because it is usually \
closest to the root cause. Say when a later alarm looks like a symptom of an \
earlier one.
- Never instruct the engineer to reset, restart, or reconfigure anything unless \
a provided section explicitly says to, and repeat any precondition that section \
attaches to it.
- Be brief. An engineer reads this while an outage is running.
- If the provided sections do not give enough to say anything useful, say that \
instead of filling the space.\
"""


class BriefingDraft(BaseModel):
    """The shape the model is constrained to return."""

    summary: str = Field(
        description="Two or three sentences orienting the engineer: what appears "
        "to have happened and which alarm looks like the root cause."
    )
    first_actions: list[str] = Field(
        description="Up to four concrete next steps, each drawn from a provided "
        "runbook section. Empty if the sections do not support any."
    )
    cited_section_ids: list[str] = Field(
        description="Exact ids of the runbook sections used, e.g. RBS-0003."
    )
    gaps: str | None = Field(
        default=None,
        description="What the provided runbooks do not cover for this incident, "
        "or null if they cover it adequately.",
    )


class UngroundedBriefing(RuntimeError):
    """The model cited a runbook section it was not given."""


class BriefingUnavailable(RuntimeError):
    """Generation could not run — not configured, or the API call failed."""


class BriefingGenerator(Protocol):
    def generate(
        self, incident: Incident, recommendations: list[Recommendation]
    ) -> GeneratedBriefing: ...


def build_prompt(incident: Incident, recommendations: list[Recommendation]) -> str:
    alarms = "\n".join(
        f"- {alarm.occurred_at.isoformat()} {alarm.code} ({alarm.severity}): "
        f"{alarm.message}"
        for alarm in sorted(incident.alarms, key=lambda alarm: alarm.occurred_at)
    )

    sections = "\n\n".join(
        f"[{recommendation.section.id}] "
        f"{recommendation.section.runbook_title} — {recommendation.section.heading}\n"
        f"(applies to: {', '.join(recommendation.section.applies_to)})\n"
        f"{recommendation.section.body}"
        for recommendation in recommendations
    )

    return (
        f"INCIDENT {incident.id} at site {incident.site_id}\n"
        f"Severity: {incident.severity}. Status: {incident.status}.\n"
        f"Subscribers affected: {incident.affected_subscribers}.\n"
        f"Recorded probable cause: {incident.probable_cause}\n\n"
        f"ALARMS, oldest first:\n{alarms}\n\n"
        f"APPROVED RUNBOOK SECTIONS — the only material you may use:\n\n"
        f"{sections}"
    )


def verify_citations(draft: BriefingDraft, allowed_ids: set[str]) -> list[str]:
    """
    Reject a briefing that cites a section it was never given.

    Fabricated citations are the specific failure this feature must not have:
    an engineer who follows a citation to a procedure that does not exist has
    been actively misled, which is worse than having no briefing at all. So the
    whole briefing is discarded rather than shown with the bad citation removed
    — if one citation is invented, the prose around it cannot be trusted either.
    """
    cited = [section_id.strip() for section_id in draft.cited_section_ids]
    invented = [section_id for section_id in cited if section_id not in allowed_ids]

    if invented:
        raise UngroundedBriefing(
            f"The model cited runbook sections it was not given: {invented}"
        )

    return cited


class AnthropicBriefingGenerator:
    def __init__(self, model: str) -> None:
        # Imported lazily so the application runs without the SDK installed
        # when generated briefings are switched off.
        import anthropic

        self._anthropic = anthropic
        self._client = anthropic.Anthropic()
        self._model = model

    def generate(
        self, incident: Incident, recommendations: list[Recommendation]
    ) -> GeneratedBriefing:
        if not recommendations:
            raise BriefingUnavailable(
                "There are no retrieved runbook sections to summarise."
            )

        try:
            response = self._client.messages.parse(
                model=self._model,
                max_tokens=16000,
                system=SYSTEM_PROMPT,
                messages=[
                    {"role": "user", "content": build_prompt(incident, recommendations)}
                ],
                output_format=BriefingDraft,
            )
        except self._anthropic.AuthenticationError as error:
            raise BriefingUnavailable(
                "Claude API credentials were rejected."
            ) from error
        except self._anthropic.RateLimitError as error:
            raise BriefingUnavailable(
                "Claude API rate limit reached; try again shortly."
            ) from error
        except self._anthropic.APIConnectionError as error:
            raise BriefingUnavailable("Could not reach the Claude API.") from error
        except self._anthropic.APIStatusError as error:
            raise BriefingUnavailable(
                f"Claude API returned {error.status_code}."
            ) from error

        if response.stop_reason == "refusal":
            raise BriefingUnavailable("The model declined to answer this request.")

        draft = response.parsed_output

        if draft is None:
            raise BriefingUnavailable("The model returned no structured output.")

        allowed = {
            recommendation.section.id for recommendation in recommendations
        }
        cited = verify_citations(draft, allowed)

        return GeneratedBriefing(
            summary=draft.summary,
            first_actions=draft.first_actions,
            cited_section_ids=cited,
            gaps=draft.gaps,
            model=response.model,
        )


class NullBriefingGenerator:
    """Used when generated briefings are switched off."""

    def generate(
        self, incident: Incident, recommendations: list[Recommendation]
    ) -> GeneratedBriefing:
        raise BriefingUnavailable(
            "Generated briefings are disabled. Set ENABLE_BRIEFINGS=true and "
            "provide Claude API credentials to enable them."
        )


def build_generator(*, enabled: bool, model: str) -> BriefingGenerator:
    if not enabled:
        return NullBriefingGenerator()

    try:
        return AnthropicBriefingGenerator(model)
    except ImportError:
        logger.warning("The anthropic package is not installed; briefings disabled.")
        return NullBriefingGenerator()
    except Exception:
        # Runs at import time. A briefing generator that cannot be built is a
        # missing feature; an exception here would instead take down the
        # incident dashboard, which is the part people are relying on during an
        # outage. Degrade, log loudly, and keep serving incidents.
        logger.exception("Could not build the briefing generator; briefings disabled.")
        return NullBriefingGenerator()


def serialise_actions(actions: list[str]) -> str:
    return json.dumps(actions)


def deserialise_actions(raw: str) -> list[str]:
    loaded = json.loads(raw)

    return [str(item) for item in loaded] if isinstance(loaded, list) else []
