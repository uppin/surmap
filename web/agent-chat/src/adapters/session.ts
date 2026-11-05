import type { Interceptor } from "@connectrpc/connect";
import { DEFAULT_SERVER_URL } from "./connect-chat";

/** Where the tab keeps the agent's session token (cleared when the tab closes). */
export const SESSION_KEY = "surmap-agent-session";

/**
 * Trades the agent's pass code for a session token and keeps it for this tab. The agent also
 * sets the token as an HttpOnly cookie, which `<img>` and the 3D preview's requests carry.
 */
export async function signIn(serverUrl: string, code: string, fetchFn: typeof fetch = fetch): Promise<void> {
  const response = await fetchFn(`${serverUrl.replace(/\/$/, "")}/auth/session`, {
    method: "POST",
    headers: { "content-type": "application/json" },
    credentials: "include",
    body: JSON.stringify({ code }),
  });
  if (!response.ok) throw new Error(`the agent refused the access code (${response.status})`);
  const body = (await response.json()) as { token: string };
  sessionStorage.setItem(SESSION_KEY, body.token);
}

/** Whether the agent has a pass code, and whether this tab may call it. */
export interface SessionStatus {
  gated: boolean;
  signedIn: boolean;
}

const NO_GATE: SessionStatus = { gated: false, signedIn: true };

/**
 * Asks the agent (`GET /auth/session`) whether this tab must sign in, with the tab's token when it
 * has one; the cookie rides along on the page's own origin. An agent that cannot say (unreachable,
 * or older than the route) is taken as one with no gate, so the page behaves as it did before.
 */
export async function sessionStatus(
  serverUrl: string,
  fetchFn: typeof fetch = fetch,
  token: () => string | null = storedToken,
): Promise<SessionStatus> {
  const current = token();
  try {
    const response = await fetchFn(`${serverUrl.replace(/\/$/, "")}/auth/session`, {
      headers: current ? { authorization: `Bearer ${current}` } : {},
    });
    if (!response.ok) return NO_GATE;
    const body = (await response.json()) as { gated: boolean; signed_in: boolean };
    return { gated: body.gated, signedIn: body.signed_in };
  } catch {
    return NO_GATE;
  }
}

/** The tab's session token, or `null` before signing in. */
export function storedToken(): string | null {
  try {
    return sessionStorage.getItem(SESSION_KEY);
  } catch {
    return null;
  }
}

/** Adds `Authorization: Bearer <token>` to every Connect call once the tab has a token. */
export function sessionInterceptor(token: () => string | null = storedToken): Interceptor {
  return (next) => async (request) => {
    const current = token();
    if (current) request.header.set("authorization", `Bearer ${current}`);
    return next(request);
  };
}

/** The agent to talk to when `?server=` names none: the local one under Vite, else this page's own origin. */
export function defaultServerUrl(location: Pick<Location, "origin">, dev: boolean): string {
  return dev ? DEFAULT_SERVER_URL : location.origin;
}
