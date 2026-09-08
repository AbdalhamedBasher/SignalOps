import { getAuthHeader } from "./auth";
import { API_BASE_URL } from "./config";
import {
  isBriefing,
  isRecommendation,
  type Briefing,
  type Recommendation,
} from "../types/recommendation";

// Legacy briefing endpoints kept for backward compatibility if called
export async function fetchBriefing(
  incidentId: string,
  signal?: AbortSignal,
): Promise<Briefing | null> {
  const response = await fetch(
    `${API_BASE_URL}/api/incidents/${encodeURIComponent(incidentId)}/briefing`,
    {
      headers: { ...getAuthHeader() },
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(`Briefing request failed with ${response.status}`);
  }

  const data: unknown = await response.json();

  if (data === null) {
    return null;
  }

  if (!isBriefing(data)) {
    throw new Error("The API returned an invalid briefing payload");
  }

  return data;
}

export async function requestBriefing(incidentId: string): Promise<Briefing> {
  const response = await fetch(
    `${API_BASE_URL}/api/incidents/${encodeURIComponent(incidentId)}/briefing`,
    {
      method: "POST",
      headers: { ...getAuthHeader() },
    },
  );

  if (!response.ok) {
    const detail: unknown = await response.json().catch(() => null);
    const message =
      typeof detail === "object" && detail !== null && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `Briefing generation failed with ${response.status}`;

    throw new Error(message);
  }

  const data: unknown = await response.json();

  if (!isBriefing(data)) {
    throw new Error("The API returned an invalid briefing payload");
  }

  return data;
}

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
    {
      headers: { ...getAuthHeader() },
      signal,
    },
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
    {
      method: "POST",
      headers: { ...getAuthHeader() },
      signal,
    },
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
    note?: string;
    modifiedSteps?: string;
  },
): Promise<Recommendation> {
  const action = decision.approved ? "approve" : "reject";

  const response = await fetch(
    `${API_BASE_URL}/api/recommendations/${encodeURIComponent(recommendationId)}/${action}`,
    {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        ...getAuthHeader(),
      },
      // WHY: The actor identity is extracted exclusively from the JWT bearer token,
      // never the request body, preventing identity spoofing across role boundaries.
      body: JSON.stringify({
        note: decision.note || null,
        modified_steps: decision.modifiedSteps || null,
      }),
    },
  );

  if (!response.ok) {
    const detail: unknown = await response.json().catch(() => null);
    const message =
      typeof detail === "object" && detail !== null && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `Could not record the decision (${response.status})`;

    throw new Error(message);
  }

  const data: unknown = await response.json();

  if (!isRecommendation(data)) {
    throw new Error("The API returned an invalid recommendation payload");
  }

  return data;
}
