import { isIncident, type Incident } from "../types/incident";

const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export async function fetchIncidents(
  signal?: AbortSignal,
): Promise<Incident[]> {
  const response = await fetch(`${API_BASE_URL}/api/incidents`, { signal });

  if (!response.ok) {
    throw new Error(`Incident request failed with status ${response.status}`);
  }

  const data: unknown = await response.json();

  if (!Array.isArray(data) || !data.every(isIncident)) {
    throw new Error("The API returned an invalid incident payload");
  }

  return data;
}
