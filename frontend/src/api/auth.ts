import { API_BASE_URL } from "./config";
import { DEMO_OPERATORS, type AccessToken } from "../types/auth";

const STORAGE_KEY = "signalops_auth";

// WHY: LocalStorage persistence ensures operator credentials and selected role
// survive browser refreshes during hackathon demonstration runs.
export function getStoredAuth(): AccessToken | null {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    return JSON.parse(raw) as AccessToken;
  } catch {
    return null;
  }
}

export function setStoredAuth(token: AccessToken | null): void {
  try {
    if (token) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(token));
    } else {
      localStorage.removeItem(STORAGE_KEY);
    }
  } catch {
    // Ignore storage quota or access errors in restricted iframe environments
  }
}

export function getAuthHeader(): Record<string, string> {
  const auth = getStoredAuth();
  if (!auth?.access_token) return {};
  return { Authorization: `Bearer ${auth.access_token}` };
}

export async function login(
  username: string,
  password: string,
): Promise<AccessToken> {
  const response = await fetch(`${API_BASE_URL}/api/auth/login`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });

  if (!response.ok) {
    throw new Error(`Login failed with status ${response.status}`);
  }

  const data = (await response.json()) as AccessToken;
  setStoredAuth(data);
  return data;
}

/**
 * Confirm a stored token is still one the API will accept.
 *
 * A token can be stored and useless: it expires after eight hours, and it stops
 * verifying whenever the API restarts without a fixed JWT_SECRET, because the
 * signing secret is regenerated. Both are silent — the token still looks like a
 * token.
 */
async function isTokenStillValid(token: string): Promise<boolean> {
  try {
    const response = await fetch(`${API_BASE_URL}/api/auth/me`, {
      headers: { Authorization: `Bearer ${token}` },
    });

    return response.ok;
  } catch {
    // The API being unreachable is not the same as the token being bad, so
    // keep it rather than throwing away a session over a network blip.
    return true;
  }
}

// WHY: Ensures the prototype is always functional immediately upon opening the page
// by automatically logging in as Nadia Karim (Engineer) if no session exists.
export async function ensureAuthenticated(): Promise<AccessToken> {
  const existing = getStoredAuth();

  // Verified rather than trusted. Trusting it meant that restarting the API
  // left the dashboard permanently signed in with a token nothing accepts —
  // every request 401, the live feed rejected 403, and no way back except
  // clearing site data by hand.
  if (existing?.access_token && (await isTokenStillValid(existing.access_token))) {
    return existing;
  }

  setStoredAuth(null);

  const defaultOperator = DEMO_OPERATORS[0];
  return login(defaultOperator.username, defaultOperator.password);
}

export async function switchOperator(username: string): Promise<AccessToken> {
  const operator = DEMO_OPERATORS.find((op) => op.username === username);
  if (!operator) {
    throw new Error(`Unknown demo operator: ${username}`);
  }

  return login(operator.username, operator.password);
}
