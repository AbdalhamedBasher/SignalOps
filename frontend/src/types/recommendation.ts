export const recommendationStatuses = [
  "proposed",
  "approved",
  "rejected",
] as const;

export type RecommendationStatus = (typeof recommendationStatuses)[number];

export type RunbookSection = {
  id: string;
  runbook_title: string;
  source_name: string;
  heading: string;
  anchor: string;
  body: string;
  applies_to: string[];
  // WHY: Certain runbook procedures (e.g. destructive resets) require supervisor
  // authorization declared in the runbook markdown itself (Requires: supervisor).
  requires_supervisor?: boolean;
};

export type Recommendation = {
  id: string;
  incident_id: string;
  section: RunbookSection;
  rationale: string;
  matched_codes: string[];
  status: RecommendationStatus;
  decided_by: string | null;
  decision_note: string | null;
  modified_steps: string | null;
};

export const impactVerdicts = [
  "confirmed",
  "partial",
  "not_confirmed",
  "unknown",
] as const;

export type ImpactVerdict = (typeof impactVerdicts)[number];

export type StoredTriage = {
  id: string;
  incident_id: string;
  verdict: ImpactVerdict;
  summary: string;
  evidence: string[];
  first_actions: string[];
  cited_section_ids: string[];
  gaps: string | null;
  model: string;
  trace: string[];
  generated_at: string;
};

export function isStoredTriage(value: unknown): value is StoredTriage {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.incident_id === "string" &&
    typeof value.verdict === "string" &&
    impactVerdicts.includes(value.verdict as ImpactVerdict) &&
    typeof value.summary === "string" &&
    isStringArray(value.evidence) &&
    isStringArray(value.first_actions) &&
    // WHY: Citations are what make agent-generated triage verifiable against
    // approved runbooks; an invalid citation list indicates a compromised response.
    isStringArray(value.cited_section_ids) &&
    isNullableString(value.gaps) &&
    typeof value.model === "string" &&
    isStringArray(value.trace) &&
    typeof value.generated_at === "string"
  );
}

// Deprecated legacy Briefing type preserved for backwards compatibility.
export type Briefing = {
  id: string;
  incident_id: string;
  summary: string;
  first_actions: string[];
  cited_section_ids: string[];
  gaps: string | null;
  model: string;
  generated_at: string;
};

export function isBriefing(value: unknown): value is Briefing {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.incident_id === "string" &&
    typeof value.summary === "string" &&
    isStringArray(value.first_actions) &&
    isStringArray(value.cited_section_ids) &&
    isNullableString(value.gaps) &&
    typeof value.model === "string" &&
    typeof value.generated_at === "string"
  );
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null;
}

function isStringArray(value: unknown): value is string[] {
  return Array.isArray(value) && value.every((item) => typeof item === "string");
}

function isNullableString(value: unknown): value is string | null {
  return value === null || typeof value === "string";
}

function isRunbookSection(value: unknown): value is RunbookSection {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.runbook_title === "string" &&
    typeof value.source_name === "string" &&
    typeof value.heading === "string" &&
    typeof value.anchor === "string" &&
    typeof value.body === "string" &&
    isStringArray(value.applies_to) &&
    (value.requires_supervisor === undefined ||
      typeof value.requires_supervisor === "boolean")
  );
}

export function isRecommendation(value: unknown): value is Recommendation {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.incident_id === "string" &&
    isRunbookSection(value.section) &&
    typeof value.rationale === "string" &&
    isStringArray(value.matched_codes) &&
    typeof value.status === "string" &&
    recommendationStatuses.includes(value.status as RecommendationStatus) &&
    isNullableString(value.decided_by) &&
    isNullableString(value.decision_note) &&
    isNullableString(value.modified_steps)
  );
}
