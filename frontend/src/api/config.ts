/**
 * Render's `fromService … property: host` injects a bare hostname with no
 * scheme. Left alone, `fetch("signalops-api.onrender.com/api/incidents")` is
 * read as a *relative* path and quietly requests the wrong origin, which is a
 * miserable thing to debug on deploy day. Anything without a scheme is treated
 * as https, since that is the only thing a hosted API is served over.
 */
const LOCAL_API_URL = "http://localhost:8000";

function isLocalHost(hostname: string): boolean {
  return hostname === "localhost" || hostname === "127.0.0.1" || hostname === "[::1]";
}

/**
 * Vite inlines `import.meta.env.VITE_*` at BUILD time. On Render the value
 * arrives from `fromService … property: host`, so a dashboard built before the
 * API service exists compiles an empty string and can never recover — not on
 * restart, not on cache clear, only on a rebuild.
 *
 * Falling back to localhost there is the worst possible failure: the browser
 * blocks it as mixed content and reports only "Failed to fetch", which reads
 * like the API is down when the real fault is a build that lost its binding.
 * So localhost is a fallback only when the page is itself served from
 * localhost. Anywhere else, say plainly what is missing.
 */
function normalizeBaseUrl(raw: string | undefined): string {
  const value = (raw ?? "").trim().replace(/\/+$/, "");

  if (value) {
    return /^https?:\/\//.test(value) ? value : `https://${value}`;
  }

  if (typeof window !== "undefined" && !isLocalHost(window.location.hostname)) {
    // render.yaml names both services, so the API host is derivable rather than
    // guessed: signalops-dashboard.onrender.com -> signalops-api.onrender.com.
    const { protocol, hostname } = window.location;
    const derived = `${protocol}//${hostname.replace(/^signalops-dashboard\b/, "signalops-api")}`;

    console.error(
      `VITE_API_URL was empty when this dashboard was built, so no API address ` +
        `was compiled in. Falling back to ${derived}. Rebuild the static site ` +
        `once the API service exists to bind it properly.`,
    );

    return derived;
  }

  return LOCAL_API_URL;
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
