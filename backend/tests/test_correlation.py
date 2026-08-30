"""
Tests for the correlation rules themselves, with no HTTP and no storage.

These are the tests that describe the product's actual behaviour: which alarms
are considered one fault and which are not.
"""

from datetime import UTC, datetime, timedelta

from app.catalog import alarm_definition
from app.correlation import (
    CORRELATION_WINDOW,
    attach_alarm,
    find_correlated_incident,
    open_incident,
)
from app.models import Alarm, IncidentSeverity, IncidentStatus

FAULT_START = datetime(2026, 8, 30, 10, 0, 0, tzinfo=UTC)


def make_alarm(
    code: str,
    *,
    site_id: str = "RUH-104",
    at: datetime = FAULT_START,
    alarm_id: str = "ALM-TEST",
) -> Alarm:
    return Alarm(
        id=alarm_id,
        site_id=site_id,
        code=code,
        message=f"{code} raised during a test",
        severity=alarm_definition(code).severity,
        occurred_at=at,
    )


def test_an_alarm_at_the_same_site_inside_the_window_joins_the_incident() -> None:
    incident = open_incident("INC-9001", make_alarm("BACKHAUL_DOWN"))
    follow_up = make_alarm("CELL_OUT_OF_SERVICE", at=FAULT_START + timedelta(minutes=2))

    assert find_correlated_incident([incident], follow_up) is incident


def test_an_alarm_after_the_window_starts_a_new_incident() -> None:
    incident = open_incident("INC-9001", make_alarm("BACKHAUL_DOWN"))
    much_later = make_alarm(
        "CELL_OUT_OF_SERVICE", at=FAULT_START + CORRELATION_WINDOW + timedelta(minutes=1)
    )

    assert find_correlated_incident([incident], much_later) is None


# TODO(you): pin down the boundary.
# `find_correlated_incident` compares with `<=`, so an alarm landing exactly
# CORRELATION_WINDOW after the incident's latest alarm still joins it. Nothing
# currently proves that, which means someone could change `<=` to `<` and every
# test would stay green. Write `test_an_alarm_exactly_on_the_window_boundary_
# still_joins_the_incident`.
# Hint: model it on the two tests either side of this comment, and use
# `at=FAULT_START + CORRELATION_WINDOW` with no extra seconds.


def test_an_alarm_at_another_site_starts_a_new_incident() -> None:
    incident = open_incident("INC-9001", make_alarm("BACKHAUL_DOWN"))
    elsewhere = make_alarm("BACKHAUL_DOWN", site_id="JED-118")

    assert find_correlated_incident([incident], elsewhere) is None


def test_resolved_incidents_do_not_absorb_new_alarms() -> None:
    incident = open_incident("INC-9001", make_alarm("BACKHAUL_DOWN"))
    incident.status = IncidentStatus.RESOLVED

    fresh_alarm = make_alarm("BACKHAUL_DOWN", at=FAULT_START + timedelta(minutes=1))

    assert find_correlated_incident([incident], fresh_alarm) is None


def test_the_window_slides_along_the_most_recent_alarm() -> None:
    """
    A fault lasting longer than one window is still one incident.

    This is the difference between measuring from the incident's opening time
    and measuring from its latest activity. Three alarms ten minutes apart span
    thirty minutes, which is twice the window, yet they belong together.
    """
    incident = open_incident("INC-9001", make_alarm("BACKHAUL_DOWN"))

    for minutes in (10, 20, 30):
        next_alarm = make_alarm(
            "CELL_OUT_OF_SERVICE", at=FAULT_START + timedelta(minutes=minutes)
        )

        assert find_correlated_incident([incident], next_alarm) is incident
        attach_alarm(incident, next_alarm)

    assert len(incident.alarms) == 4


def test_incident_severity_follows_its_worst_alarm() -> None:
    incident = open_incident("INC-9001", make_alarm("MW_SNR_DEGRADED"))
    assert incident.severity is IncidentSeverity.MEDIUM

    attach_alarm(
        incident, make_alarm("BACKHAUL_DOWN", at=FAULT_START + timedelta(minutes=1))
    )
    assert incident.severity is IncidentSeverity.CRITICAL

    # A milder alarm arriving later must not talk the incident down.
    attach_alarm(
        incident, make_alarm("MW_SNR_DEGRADED", at=FAULT_START + timedelta(minutes=2))
    )
    assert incident.severity is IncidentSeverity.CRITICAL


def test_a_late_delivered_earlier_alarm_restates_the_incident() -> None:
    """
    Out-of-order delivery can change what the incident is *about*.

    If the true first signal arrives second, the incident's beginning and its
    explanation both have to move, or the dashboard tells the engineer the
    wrong causal story.
    """
    incident = open_incident("INC-9001", make_alarm("VOLTE_REG_FAILURE"))
    assert incident.title == "VoLTE service degradation"

    root_cause = make_alarm("BACKHAUL_DOWN", at=FAULT_START - timedelta(minutes=2))
    attach_alarm(incident, root_cause)

    assert incident.title == "Backhaul connectivity loss"
    assert incident.probable_cause == "Fiber backhaul interruption"
    assert incident.opened_at == root_cause.occurred_at


def test_an_uncatalogued_alarm_is_kept_rather_than_dropped() -> None:
    incident = open_incident("INC-9001", make_alarm("SOMETHING_WE_HAVE_NOT_SEEN"))

    assert incident.severity is IncidentSeverity.MEDIUM
    assert incident.title == "Unclassified site alarm"
    assert len(incident.alarms) == 1


def test_an_unknown_site_reports_zero_rather_than_guessing_impact() -> None:
    incident = open_incident("INC-9001", make_alarm("BACKHAUL_DOWN", site_id="XXX-999"))

    assert incident.affected_subscribers == 0
