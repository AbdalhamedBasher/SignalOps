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
    // Citations are what make generated text checkable, so a briefing whose
    // citation list is the wrong shape is refused rather than displayed.
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
    isStringArray(value.applies_to)
  );
}

export function isRecommendation(value: unknown): value is Recommendation {
  if (!isRecord(value)) {
    return false;
  }

  return (
    typeof value.id === "string" &&
    typeof value.incident_id === "string" &&
    // A recommendation without a valid citation is refused outright rather
    // than rendered with a missing source. Unattributed guidance is exactly
    // what this slice exists to prevent.
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
