"""
Choosing which runbook sections apply to an incident.

Deliberately deterministic. An engineer acting at three in the morning needs to
know *why* a procedure was put in front of them, and "your incident raised
BACKHAUL_DOWN, and this section says it covers BACKHAUL_DOWN" is an answer they
can check in a second. This is the layer an LLM would later sit on top of —
ranking and summarising what is retrieved here — never replacing it.
"""

from collections.abc import Sequence
from dataclasses import dataclass

from app.models import Incident, RunbookSection


@dataclass(frozen=True)
class RetrievedSection:
    section: RunbookSection
    matched_codes: list[str]
    rationale: str


def _describe(matched_codes: Sequence[str], incident: Incident) -> str:
    if len(matched_codes) == 1:
        return (
            f"{incident.id} raised {matched_codes[0]}, which this procedure covers."
        )

    listed = ", ".join(matched_codes)

    return (
        f"{incident.id} raised {len(matched_codes)} alarms this procedure "
        f"covers: {listed}."
    )


def retrieve_for_incident(
    incident: Incident, sections: Sequence[RunbookSection]
) -> list[RetrievedSection]:
    """
    Rank the sections that apply to an incident, most relevant first.

    Relevance is how many of the incident's distinct alarm codes a section
    covers: a procedure written for the exact combination in front of you is
    more use than one matching a single symptom. Ties are broken by the section
    id so the order is total and a regenerated set does not reshuffle.
    """
    incident_codes = {alarm.code for alarm in incident.alarms}
    retrieved: list[RetrievedSection] = []

    for section in sections:
        matched = sorted(incident_codes.intersection(section.applies_to))

        if not matched:
            continue

        retrieved.append(
            RetrievedSection(
                section=section,
                matched_codes=matched,
                rationale=_describe(matched, incident),
            )
        )

    retrieved.sort(key=lambda item: (-len(item.matched_codes), item.section.id))

    return retrieved
