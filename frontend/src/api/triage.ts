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

/**
 * Run a triage and report each step as the agent takes it.
 *
 * A live run takes about half a minute, most of it real round-trips to Nokia.
 * Delivered as one silent wait it looks broken; delivered as a running list of
 * the network calls the agent chose to make, the wait becomes the part worth
 * watching.
 *
 * Newline-delimited JSON over `fetch`, not EventSource — EventSource cannot
 * send an Authorization header, and every endpoint here is authenticated.
 */
export async function streamTriage(
  incidentId: string,
  onStep: (step: string) => void,
  signal?: AbortSignal,
): Promise<StoredTriage> {
  const response = await fetch(
    `${API_BASE_URL}/api/incidents/${encodeURIComponent(incidentId)}/triage/stream`,
    { method: "POST", headers: { ...getAuthHeader() }, signal },
  );

  if (!response.ok || !response.body) {
    throw new Error(`Triage stream failed with status ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffered = "";
  let report: StoredTriage | null = null;

  for (;;) {
    const { done, value } = await reader.read();

    if (done) {
      break;
    }

    buffered += decoder.decode(value, { stream: true });

    // A chunk can split a line in half, so the trailing fragment is kept back
    // until the newline that completes it arrives.
    const lines = buffered.split("\n");
    buffered = lines.pop() ?? "";

    for (const line of lines) {
      if (!line.trim()) {
        continue;
      }

      const event: unknown = JSON.parse(line);

      if (typeof event !== "object" || event === null || !("type" in event)) {
        continue;
      }

      const typed = event as { type: string; text?: string; detail?: string; report?: unknown };

      if (typed.type === "step" && typed.text) {
        onStep(typed.text);
      } else if (typed.type === "error") {
        throw new Error(typed.detail ?? "The triage agent could not complete.");
      } else if (typed.type === "report") {
        if (!isStoredTriage(typed.report)) {
          throw new Error("The API returned an invalid triage report format");
        }

        report = typed.report;
      }
    }
  }

  if (!report) {
    throw new Error("The triage stream ended without returning a report.");
  }

  return report;
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
