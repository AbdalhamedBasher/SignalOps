"""
Deterministic alarm-to-incident correlation.

This module is the heart of the product claim: many raw alarms, one incident an
engineer can act on. It is deliberately free of FastAPI, storage, and clocks —
every function takes what it needs and returns a decision, so the rules can be
tested directly instead of through HTTP.

The rule, in one sentence: an alarm joins an open incident at the same site
whose activity it lands close to in time, and otherwise starts a new one.
"""

from collections.abc import Iterable, Sequence
from datetime import timedelta

from app.catalog import alarm_definition, subscribers_at
from app.models import (
    SEVERITY_RANK,
    Alarm,
    Incident,
    IncidentSeverity,
    IncidentStatus,
)

# How far apart two alarms at one site can be and still be treated as the same
# fault. The window slides along the incident's most recent alarm rather than
# being fixed at its opening time, so a long outage keeps absorbing its cascade
# instead of splitting into two incidents halfway through.
CORRELATION_WINDOW = timedelta(minutes=15)


def worst_severity(severities: Iterable[IncidentSeverity]) -> IncidentSeverity:
    """An incident is as bad as the worst thing happening inside it."""
    return min(severities, key=lambda severity: SEVERITY_RANK[severity])


def is_open(incident: Incident) -> bool:
    return incident.status is not IncidentStatus.RESOLVED


def find_correlated_incident(
    incidents: Sequence[Incident],
    alarm: Alarm,
    window: timedelta = CORRELATION_WINDOW,
) -> Incident | None:
    """
    Return the incident this alarm belongs to, or None if it starts a new one.

    The distance is measured with abs() on purpose: collectors deliver alarms
    out of order, so an alarm can legitimately arrive carrying a timestamp
    *earlier* than the incident it belongs to.
    """
    candidates = [
        incident
        for incident in incidents
        if incident.site_id == alarm.site_id
        and is_open(incident)
        and abs(alarm.occurred_at - incident.latest_alarm_at()) <= window
    ]

    if not candidates:
        return None

    # If several incidents at the site qualify, the most recently active one is
    # the better match for a still-unfolding fault.
    return max(candidates, key=lambda incident: incident.latest_alarm_at())


def restate_from_root_alarm(incident: Incident) -> Incident:
    """
    Re-derive the incident's story from its earliest alarm.

    The first signal is what explains the fault, so it names the incident. This
    has to be recomputed rather than set once, because an out-of-order delivery
    can introduce an alarm that predates everything already recorded — which
    means the incident's real beginning, and its explanation, just changed.
    """
    root_alarm = min(incident.alarms, key=lambda alarm: alarm.occurred_at)
    definition = alarm_definition(root_alarm.code)

    incident.title = definition.incident_title
    incident.probable_cause = definition.probable_cause
    incident.opened_at = root_alarm.occurred_at

    return incident


def open_incident(incident_id: str, alarm: Alarm) -> Incident:
    definition = alarm_definition(alarm.code)

    return Incident(
        id=incident_id,
        site_id=alarm.site_id,
        title=definition.incident_title,
        severity=alarm.severity,
        status=IncidentStatus.ACTIVE,
        affected_subscribers=subscribers_at(alarm.site_id),
        probable_cause=definition.probable_cause,
        opened_at=alarm.occurred_at,
        alarms=[alarm],
    )


def attach_alarm(incident: Incident, alarm: Alarm) -> Incident:
    incident.alarms.append(alarm)
    incident.severity = worst_severity(
        [existing.severity for existing in incident.alarms]
    )

    return restate_from_root_alarm(incident)
