export const incidentSeverities = [
  "critical",
  "high",
  "medium",
  "low",
] as const;

export const incidentStatuses = [
  "active",
  "investigating",
  "resolved",
] as const;

export type IncidentSeverity = (typeof incidentSeverities)[number];
export type IncidentStatus = (typeof incidentStatuses)[number];

/**
 * Only the fields the dashboard actually consumes. The API sends more (a
 * per-alarm `site_id`, the collector's `external_id`); we deliberately do not
 * declare or validate those, because the incident already carries the site and
 * nothing here should start depending on delivery metadata.
 */
export type Alarm = {
  id: string;
  code: string;
  message: string;
  severity: IncidentSeverity;
  occurred_at: string;
};

export type Incident = {
  id: string;
  site_id: string;
  title: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  affected_subscribers: number;
  probable_cause: string;
  opened_at: string;
  alarms: Alarm[];
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

/**
 * A timestamp arrives as a string, but `string` says nothing about whether it
 * is a *date*. We check that it actually parses, so every consumer downstream
 * can sort and format it without defending against `Invalid Date`.
 */
function isTimestamp(value: unknown): value is string {
  return typeof value === "string" && !Number.isNaN(Date.parse(value));
}

function isIncidentSeverity(value: unknown): value is IncidentSeverity {
  return (
    typeof value === "string" &&
    incidentSeverities.includes(value as IncidentSeverity)
  );
}

function isIncidentStatus(value: unknown): value is IncidentStatus {
  return (
    typeof value === "string" &&
    incidentStatuses.includes(value as IncidentStatus)
  );
}

export function isAlarm(value: unknown): value is Alarm {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.code === "string" &&
    typeof value.message === "string" &&
    isIncidentSeverity(value.severity) &&
    isTimestamp(value.occurred_at)
  );
}

export const incidentEventTypes = [
  "incident.opened",
  "incident.updated",
] as const;

export type IncidentEventType = (typeof incidentEventTypes)[number];

export type IncidentEvent = {
  type: IncidentEventType;
  incident: Incident;
};

export function isIncidentEvent(value: unknown): value is IncidentEvent {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.type === "string" &&
    incidentEventTypes.includes(value.type as IncidentEventType) &&
    isIncident(value.incident)
  );
}

export function isIncident(value: unknown): value is Incident {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.site_id === "string" &&
    typeof value.title === "string" &&
    isIncidentSeverity(value.severity) &&
    isIncidentStatus(value.status) &&
    typeof value.affected_subscribers === "number" &&
    value.affected_subscribers >= 0 &&
    typeof value.probable_cause === "string" &&
    isTimestamp(value.opened_at) &&
    Array.isArray(value.alarms) &&
    value.alarms.every(isAlarm)
  );
}
