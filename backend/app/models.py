from datetime import datetime
from enum import Enum

from pydantic import BaseModel, Field


class IncidentSeverity(str, Enum):
    CRITICAL = "critical"
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class IncidentStatus(str, Enum):
    ACTIVE = "active"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"


class Alarm(BaseModel):
    id: str
    code: str
    message: str
    occurred_at: datetime


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
