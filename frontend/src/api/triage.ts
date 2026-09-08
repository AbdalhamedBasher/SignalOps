import { getAuthHeader } from "./auth";
import { API_BASE_URL } from "./config";
import { isStoredTriage, type StoredTriage } from "../types/recommendation";

export async function fetchTriage(
  incidentId: string,
  signal?: AbortSignal,
): Promise<StoredTriage | null> {
  const response = await fetch(
    `${API_BASE_URL}/api/incidents/${encodeURIComponent(incidentId)}/triage`,
    {
      headers: {
        ...getAuthHeader(),
      },
      signal,
    },
  );

  if (!response.ok) {
    throw new Error(`Triage request failed with status ${response.status}`);
  }

  const data: unknown = await response.json();

  // WHY: Null indicates no triage report has been generated yet for this incident,
  // which is an expected initial state rather than a network or parsing failure.
  if (data === null) {
    return null;
  }

  if (!isStoredTriage(data)) {
    throw new Error("The API returned an invalid triage payload");
  }

  return data;
}

export async function requestTriage(incidentId: string): Promise<StoredTriage> {
  const response = await fetch(
    `${API_BASE_URL}/api/incidents/${encodeURIComponent(incidentId)}/triage`,
    {
      method: "POST",
      headers: {
        ...getAuthHeader(),
      },
    },
  );

  if (!response.ok) {
    // WHY: The backend explicitly differentiates 503 (Gemini key not configured or API down)
    // from 502 (ungrounded citation refused by the guardrail). Surfacing this exact detail
    // tells the operator whether it's an infrastructure setup or a model compliance issue.
    const detail: unknown = await response.json().catch(() => null);
    const message =
      typeof detail === "object" && detail !== null && "detail" in detail
        ? String((detail as { detail: unknown }).detail)
        : `Triage generation failed with status ${response.status}`;

    throw new Error(message);
  }

  const data: unknown = await response.json();

  if (!isStoredTriage(data)) {
    throw new Error("The API returned an invalid triage report format");
  }

  return data;
}
