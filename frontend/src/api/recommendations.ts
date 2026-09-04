import { API_BASE_URL } from "./incidents";
import {
  isRecommendation,
  type Recommendation,
} from "../types/recommendation";

function parseRecommendations(data: unknown): Recommendation[] {
  if (!Array.isArray(data) || !data.every(isRecommendation)) {
    throw new Error("The API returned an invalid recommendation payload");
  }

  return data;
}

export async function fetchRecommendations(
  incidentId: string,
  signal?: AbortSignal,
): Promise<Recommendation[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/incidents/${encodeURIComponent(incidentId)}/recommendations`,
    { signal },
  );

  if (!response.ok) {
    throw new Error(`Recommendation request failed with ${response.status}`);
  }

  return parseRecommendations(await response.json());
}

export async function requestRecommendations(
  incidentId: string,
  signal?: AbortSignal,
): Promise<Recommendation[]> {
  const response = await fetch(
    `${API_BASE_URL}/api/incidents/${encodeURIComponent(incidentId)}/recommendations`,
    { method: "POST", signal },
  );

  if (!response.ok) {
    throw new Error(`Could not retrieve runbook guidance (${response.status})`);
  }

  return parseRecommendations(await response.json());
}

export async function decideRecommendation(
  recommendationId: string,
  decision: {
    approved: boolean;
    decidedBy: string;
    note?: string;
    modifiedSteps?: string;
  },
): Promise<Recommendation> {
  const action = decision.approved ? "approve" : "reject";

  const response = await fetch(
    `${API_BASE_URL}/api/recommendations/${encodeURIComponent(recommendationId)}/${action}`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        decided_by: decision.decidedBy,
        note: decision.note || null,
        modified_steps: decision.modifiedSteps || null,
      }),
    },
  );

  if (!response.ok) {
    throw new Error(`Could not record the decision (${response.status})`);
  }

  const data: unknown = await response.json();

  if (!isRecommendation(data)) {
    throw new Error("The API returned an invalid recommendation payload");
  }

  return data;
}
