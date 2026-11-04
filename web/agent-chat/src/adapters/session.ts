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
