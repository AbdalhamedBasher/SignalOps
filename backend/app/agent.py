"""
The incident triage agent.

This is the AI agent layer: it treats CAMARA network APIs as tools it decides
when to call, not as buttons a user presses. Given an incident, it works out
what it needs to know — is this fault real, who is actually affected, does the
network corroborate the alarms — calls the network for those answers, reads the
approved runbooks, and returns a triage verdict citing everything it used.

Built with Pydantic AI on Google Gemini. Two guarantees survive from the
deterministic layers underneath:

- The agent may only cite runbook sections that retrieval actually gave it, and
  every citation is verified afterwards.
- Nothing it produces touches the network. Its output is a recommendation an
  engineer approves or rejects, and the approval gate is unchanged.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import StrEnum

from pydantic import BaseModel, Field
from pydantic_ai import Agent, RunContext
from pydantic_ai.models.google import GoogleModel
from pydantic_ai.providers.google import GoogleProvider

from app.models import Incident, Recommendation
from app.network_intelligence import NetworkIntelligence

logger = logging.getLogger(__name__)


class ImpactVerdict(StrEnum):
    """What the agent concluded about the incident's real customer impact."""

    CONFIRMED = "confirmed"
    PARTIAL = "partial"
    NOT_CONFIRMED = "not_confirmed"
    UNKNOWN = "unknown"


class TriageReport(BaseModel):
    """The structured answer the agent is constrained to produce."""

    verdict: ImpactVerdict = Field(
        description="confirmed when network signals show subscribers are really "
        "affected; partial when some are; not_confirmed when the network "
        "contradicts the alarms; unknown when the signals were unavailable."
    )
    summary: str = Field(
        description="Two or three sentences: what happened, what the network "
        "signals showed, and what that means for the engineer."
    )
    evidence: list[str] = Field(
        default_factory=list,
        description="Each network reading you relied on, stated plainly, "
        "including which API it came from.",
    )
    first_actions: list[str] = Field(
        default_factory=list,
        description="Up to four next steps, each taken from a runbook section "
        "you were given. Empty if the runbooks do not support any.",
    )
    cited_section_ids: list[str] = Field(
        default_factory=list,
        description="Exact ids of runbook sections used, e.g. RBS-0003. Only "
        "ids that appeared in the runbook tool's output.",
    )
    gaps: str | None = Field(
        default=None,
        description="What you could not establish, or null if nothing.",
    )


@dataclass
class TriageDeps:
    """Everything the agent's tools are allowed to reach."""

    incident: Incident
    recommendations: list[Recommendation]
    network: NetworkIntelligence
    # Tool calls are recorded as they happen so the reasoning trace can be
    # shown on screen. Judges want to see the agent think, and an operator
    # needs to know which signals were actually consulted.
    trace: list[str]


INSTRUCTIONS = """\
You are the triage agent for a telecom network operations centre. An incident \
has just been correlated from raw alarms, and an engineer needs to know within \
seconds whether it is real, who it is hitting, and what to do first.

You have three tools:

- `check_device_reachability` asks the operator network whether devices at the \
site can still be reached. This is the strongest evidence of real customer \
impact — an alarm says equipment is unhappy, this says subscribers are cut off.
- `get_congestion_insight` asks the network how congested the site is. Use it \
to corroborate or contradict alarms that claim degradation rather than outage.
- `get_runbook_guidance` returns the approved procedures already matched to \
this incident.

How to work:

1. Call the network tools before concluding anything about impact. Do not \
infer impact from the alarms alone — the alarms are what you are checking.
2. Call `get_runbook_guidance` before recommending any action.
3. If a tool returns nothing useful, report the verdict as unknown rather than \
guessing. An honest "I could not establish this" is worth more at 3am than a \
confident answer that is wrong.

Choosing the verdict — apply this to the reachability reading and nothing else:

- Every known device at the site unreachable -> `confirmed`.
- Some unreachable, some still reachable -> `partial`.
- NONE unreachable, every device still answering -> `not_confirmed`.
- Reachability could not be read at all -> `unknown`.

The verdict describes whether *subscribers are cut off*, which is what \
reachability measures. Congestion is context, never the deciding factor: a \
congested site whose devices all still answer is `not_confirmed`, because \
nobody has lost service. Equipment can alarm loudly while subscribers stay \
connected, and saying so plainly is one of the most useful things you can tell \
an engineer — it stops a callout that did not need to happen. Never report \
`confirmed` while your own evidence says no device is unreachable.

Hard rules:

- Recommend ONLY steps that appear in the runbook sections the tool returned. \
Never add procedures from your own knowledge, however standard.
- Cite runbook sections by their exact id, and only ids the tool gave you.
- Never instruct anyone to reset, restart or reconfigure anything unless a \
returned section says to, and repeat any precondition it attaches.
- Be brief. This is read during an outage.\
"""


def build_agent(model_name: str, api_key: str) -> Agent[TriageDeps, TriageReport]:
    model = GoogleModel(model_name, provider=GoogleProvider(api_key=api_key))

    agent = Agent(
        model,
        deps_type=TriageDeps,
        output_type=TriageReport,
        instructions=INSTRUCTIONS,
        # A tool that fails should be retried a couple of times, not abandoned.
        retries=2,
    )

    @agent.tool
    def check_device_reachability(context: RunContext[TriageDeps]) -> str:
        """
        Ask the network whether known devices at this incident's site can be
        reached. Use this to establish whether subscribers are genuinely
        affected rather than trusting the alarm.
        """
        site_id = context.deps.incident.site_id
        reading = context.deps.network.device_reachability(site_id)

        context.deps.trace.append(
            f"Called CAMARA Device Reachability Status for {site_id} "
            f"({reading.source})"
        )

        if not reading.devices:
            return (
                f"No devices are registered at {site_id}, so reachability cannot "
                f"establish impact either way."
            )

        lines = [
            f"{device.device_id}: {device.status}" for device in reading.devices
        ]

        return (
            f"Device reachability at {site_id} (source: {reading.source}).\n"
            f"{reading.summary}\n" + "\n".join(lines)
        )

    @agent.tool
    def get_congestion_insight(context: RunContext[TriageDeps]) -> str:
        """
        Ask the network how congested this incident's site is. Use this to
        corroborate or contradict alarms reporting degradation.
        """
        site_id = context.deps.incident.site_id
        insight = context.deps.network.congestion(site_id)

        context.deps.trace.append(
            f"Called CAMARA Congestion Insights for {site_id} ({insight.source})"
        )

        return (
            f"Congestion at {site_id}: {insight.level} (source: {insight.source}). "
            f"{insight.detail}"
        )

    @agent.tool
    def get_runbook_guidance(context: RunContext[TriageDeps]) -> str:
        """
        Return the approved runbook sections already matched to this incident.
        These are the only procedures you may recommend or cite.
        """
        recommendations = context.deps.recommendations

        context.deps.trace.append(
            f"Read {len(recommendations)} matched runbook section(s)"
        )

        if not recommendations:
            return (
                "No approved runbook section matches this incident's alarms. "
                "Recommend no procedure."
            )

        return "\n\n".join(
            f"[{item.section.id}] {item.section.runbook_title} — "
            f"{item.section.heading}\n"
            f"(applies to: {', '.join(item.section.applies_to)}"
            + (
                "; requires supervisor approval)"
                if item.section.requires_supervisor
                else ")"
            )
            + f"\n{item.section.body}"
            for item in recommendations
        )

    return agent


def describe_incident(incident: Incident) -> str:
    alarms = "\n".join(
        f"- {alarm.occurred_at.isoformat()} {alarm.code} ({alarm.severity}): "
        f"{alarm.message}"
        for alarm in sorted(incident.alarms, key=lambda alarm: alarm.occurred_at)
    )

    return (
        f"Triage incident {incident.id}.\n"
        f"Site: {incident.site_id}. Severity: {incident.severity}. "
        f"Status: {incident.status}.\n"
        f"Recorded probable cause: {incident.probable_cause}\n"
        f"Subscribers believed affected: {incident.affected_subscribers} "
        f"(from static inventory — verify this against the network).\n\n"
        f"Alarms, oldest first:\n{alarms}"
    )
