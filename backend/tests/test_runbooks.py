"""Tests for runbook parsing and the retrieval that sits on top of it."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.catalog import alarm_definition
from app.correlation import attach_alarm, open_incident
from app.models import Alarm
from app.retrieval import retrieve_for_incident
from app.runbook_repository import RunbookRepository
from app.runbooks import parse_runbook, slugify

FAULT_START = datetime(2026, 8, 30, 10, 0, tzinfo=UTC)

SAMPLE = """\
# Transport faults

## Confirm the fault
Applies to: BACKHAUL_DOWN, s1_link_failure

1. Check the far end.
2. Read optical power.

## General escalation guidance

Escalate anything unresolved after fifteen minutes.
"""


def make_alarm(code: str, *, at: datetime = FAULT_START, alarm_id: str = "ALM-TEST") -> Alarm:
    return Alarm(
        id=alarm_id,
        site_id="RUH-104",
        code=code,
        message=f"{code} raised during a test",
        severity=alarm_definition(code).severity,
        occurred_at=at,
    )


def test_a_runbook_is_split_into_sections_with_their_alarm_codes() -> None:
    parsed = parse_runbook(SAMPLE)

    assert parsed.title == "Transport faults"
    assert len(parsed.sections) == 2

    first = parsed.sections[0]
    assert first.heading == "Confirm the fault"
    assert first.anchor == "confirm-the-fault"
    # Codes are normalised, so a runbook author writing lower case still works.
    assert first.applies_to == ["BACKHAUL_DOWN", "S1_LINK_FAILURE"]
    assert "Read optical power." in first.body
    # The `Applies to:` line is metadata, not guidance an engineer should read.
    assert "Applies to" not in first.body


def test_a_section_without_alarm_codes_is_kept_as_general_guidance() -> None:
    parsed = parse_runbook(SAMPLE)
    general = parsed.sections[1]

    assert general.applies_to == []
    assert "fifteen minutes" in general.body


def test_hard_wrapped_steps_are_folded_back_into_one_line() -> None:
    """
    The file is wrapped at eighty columns; the rendered panel is not.

    Without this the dashboard shows steps broken mid-sentence, which reads as
    a formatting bug to the engineer trying to follow them.
    """
    wrapped = """\
# Wrapped

## A step that runs long
Applies to: BACKHAUL_DOWN

1. A reset destroys the diagnostic state that explains the fault. Capture logs
   and counters first.
2. A second step.
"""

    section = parse_runbook(wrapped).sections[0]

    assert "Capture logs and counters first." in section.body
    assert section.body.splitlines() == [
        "1. A reset destroys the diagnostic state that explains the fault. "
        "Capture logs and counters first.",
        "2. A second step.",
    ]


def test_slugify_produces_a_usable_anchor() -> None:
    assert slugify("Never reset equipment blind") == "never-reset-equipment-blind"
    assert slugify("Fail over to the protection path!") == (
        "fail-over-to-the-protection-path"
    )


def test_the_shipped_runbooks_all_load(session: Session) -> None:
    sections = RunbookRepository(session).list_sections()

    assert len(sections) >= 8

    # Every citation must be traceable back to a reviewed file.
    for section in sections:
        assert section.source_name.endswith(".md")
        assert section.runbook_title


def test_loading_runbooks_twice_does_not_duplicate_them(session: Session) -> None:
    repository = RunbookRepository(session)
    before = len(repository.list_sections())

    assert repository.load_from_disk() == 0
    assert len(repository.list_sections()) == before


def test_retrieval_only_returns_sections_that_match_an_alarm(
    session: Session,
) -> None:
    sections = RunbookRepository(session).list_sections()
    incident = open_incident("INC-9001", make_alarm("BACKHAUL_DOWN"))

    retrieved = retrieve_for_incident(incident, sections)

    assert retrieved, "a backhaul incident should match the transport runbook"

    for item in retrieved:
        assert "BACKHAUL_DOWN" in item.section.applies_to
        assert item.matched_codes == ["BACKHAUL_DOWN"]

    # Nothing about site cooling belongs on a backhaul incident.
    headings = {item.section.heading for item in retrieved}
    assert "Respond to a cooling failure" not in headings


def test_a_section_covering_more_of_the_incident_ranks_higher(
    session: Session,
) -> None:
    sections = RunbookRepository(session).list_sections()

    incident = open_incident("INC-9001", make_alarm("BACKHAUL_DOWN", alarm_id="ALM-1"))
    attach_alarm(incident, make_alarm("S1_LINK_FAILURE", alarm_id="ALM-2"))

    retrieved = retrieve_for_incident(incident, sections)
    match_counts = [len(item.matched_codes) for item in retrieved]

    assert match_counts == sorted(match_counts, reverse=True)
    assert match_counts[0] == 2


def test_an_incident_with_no_catalogued_alarms_gets_nothing(
    session: Session,
) -> None:
    """
    Retrieval stays silent rather than guessing.

    Showing an engineer a procedure that does not apply is worse than showing
    them nothing, because it costs time they do not have during an outage.
    """
    sections = RunbookRepository(session).list_sections()
    incident = open_incident("INC-9001", make_alarm("SOMETHING_UNCATALOGUED"))

    assert retrieve_for_incident(incident, sections) == []


def test_every_retrieved_section_explains_why_it_was_chosen(
    session: Session,
) -> None:
    sections = RunbookRepository(session).list_sections()
    incident = open_incident("INC-9001", make_alarm("POWER_UNSTABLE"))

    for item in retrieve_for_incident(incident, sections):
        assert "INC-9001" in item.rationale
        assert "POWER_UNSTABLE" in item.rationale
