import { getAuthHeader } from "./auth";
import { API_BASE_URL, INCIDENT_FEED_URL } from "./config";
import { isIncident, type Incident } from "../types/incident";

// Re-export for existing callers
export { API_BASE_URL, INCIDENT_FEED_URL };

export async function fetchIncidents(
  signal?: AbortSignal,
): Promise<Incident[]> {
  const response = await fetch(`${API_BASE_URL}/api/incidents`, {
    headers: {
      ...getAuthHeader(),
    },
    signal,
  });

  if (!response.ok) {
    throw new Error(`Incident request failed with status ${response.status}`);
  }

  const data: unknown = await response.json();

  if (!Array.isArray(data) || !data.every(isIncident)) {
    throw new Error("The API returned an invalid incident payload");
  }

  return data;
}
