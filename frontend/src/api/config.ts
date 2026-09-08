/**
 * Render's `fromService … property: host` injects a bare hostname with no
 * scheme. Left alone, `fetch("signalops-api.onrender.com/api/incidents")` is
 * read as a *relative* path and quietly requests the wrong origin, which is a
 * miserable thing to debug on deploy day. Anything without a scheme is treated
 * as https, since that is the only thing a hosted API is served over.
 */
function normalizeBaseUrl(raw: string | undefined): string {
  const value = (raw ?? "").trim().replace(/\/+$/, "");

  if (!value) {
    return "http://localhost:8000";
  }

  return /^https?:\/\//.test(value) ? value : `https://${value}`;
}

export const API_BASE_URL = normalizeBaseUrl(import.meta.env.VITE_API_URL);

function resolveFeedUrl(baseUrl: string): string {
  const trimmed = baseUrl.replace(/\/+$/, "");
  // WHY: Browsers reject ws:// connections from secure https:// pages.
  // We explicitly upgrade to wss:// in production deployments.
  if (trimmed.startsWith("https://")) {
    return `${trimmed.replace(/^https:\/\//, "wss://")}/ws/incidents`;
  }
  if (trimmed.startsWith("http://")) {
    return `${trimmed.replace(/^http:\/\//, "ws://")}/ws/incidents`;
  }
  return `${trimmed}/ws/incidents`;
}

export const INCIDENT_FEED_URL = resolveFeedUrl(API_BASE_URL);
