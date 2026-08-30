from datetime import UTC, datetime
from enum import StrEnum

from pydantic import BaseModel, Field, field_validator


class IncidentSeverity(StrEnum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentStatus(StrEnum):
    ACTIVE = "active"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


# Ordered worst-first so incident severity can be reduced from its alarms.
SEVERITY_RANK: dict[IncidentSeverity, int] = {
    IncidentSeverity.CRITICAL: 0,
    IncidentSeverity.HIGH: 1,
    IncidentSeverity.MEDIUM: 2,
    IncidentSeverity.LOW: 3,
}


def require_timezone(value: datetime) -> datetime:
    """
    Reject timestamps that carry no UTC offset.

    A naive timestamp is ambiguous, and this system exists to establish the
    order in which network events happened. Silently assuming UTC could place
    an alarm hours away from its true position in a cascade and invert the
    apparent cause. Better to refuse the input than to reorder reality.
    """
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(
            "timestamp must include a UTC offset, for example 2026-07-21T08:14:03Z"
        )

    return value.astimezone(UTC)


class Alarm(BaseModel):
    id: str
    # An alarm is raised by a network element at a site. The incident inherits
    # its site from its alarms, not the other way round.
    site_id: str
    code: str
    message: str
    severity: IncidentSeverity
    occurred_at: datetime
    # Identifier supplied by the sending system, used only to drop duplicate
    # deliveries. It is not the alarm's identity inside SignalOps.
    external_id: str | None = None

    _normalize_occurred_at = field_validator("occurred_at")(require_timezone)


class Incident(BaseModel):
    id: str
    site_id: str
    title: str
    severity: IncidentSeverity
    status: IncidentStatus
    affected_subscribers: int = Field(ge=0)
    probable_cause: str
    opened_at: datetime
    alarms: list[Alarm]

    _normalize_opened_at = field_validator("opened_at")(require_timezone)

    def latest_alarm_at(self) -> datetime:
        """When this incident last showed signs of life."""
        return max((alarm.occurred_at for alarm in self.alarms), default=self.opened_at)


class AlarmSubmission(BaseModel):
    """An alarm as it arrives from a network element or collector."""

    site_id: str
    code: str
    message: str
    occurred_at: datetime
    external_id: str | None = None

    _normalize_occurred_at = field_validator("occurred_at")(require_timezone)


class AlarmIngestResult(BaseModel):
    incident: Incident
    # True when this alarm opened a new incident rather than joining one.
    incident_created: bool
    # True when this alarm was recognised as an already-ingested delivery.
    duplicate: bool


class IncidentEventType(StrEnum):
    OPENED = "incident.opened"
    UPDATED = "incident.updated"


class IncidentEvent(BaseModel):
    """
    What a connected dashboard receives when something changes.

    The whole incident travels rather than a patch. The payloads are small, and
    a self-contained object cannot leave a client half-updated if a message is
    dropped — the next one it receives is still complete and correct.
    """

    type: IncidentEventType
    incident: Incident
