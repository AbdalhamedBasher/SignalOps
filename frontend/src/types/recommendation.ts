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
