import { afterEach, describe, expect, it } from "vitest";
import { DEFAULT_SERVER_URL } from "./connect-chat";
import { SESSION_KEY, defaultServerUrl, sessionInterceptor, sessionStatus, signIn, storedToken } from "./session";

const SERVER = "https://ginas-bb--surmap-agent-serve.us-east.modal.run";

/** A fetch that answers every request with `status` and `body`, recording what it was sent. */
function fakeFetch(status: number, body: unknown) {
  const sent: { url: string; init: RequestInit | undefined }[] = [];
  const fetchFn = async (url: string | URL | Request, init?: RequestInit) => {
    sent.push({ url: String(url), init });
    return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
  };
  return { sent, fetchFn: fetchFn as typeof fetch };
}

/** What an interceptor passes on, for a request with no headers yet. */
async function headersAfter(interceptor: ReturnType<typeof sessionInterceptor>): Promise<Headers> {
  let seen = new Headers();
  const next = async (request: { header: Headers }) => {
    seen = request.header;
    return {} as never;
  };
  await interceptor(next as never)({ header: new Headers() } as never);
  return seen;
}

describe("agent session", () => {
  afterEach(() => sessionStorage.clear());

  it("signs in by posting the pass code and keeps the token for this tab", async () => {
    const server = fakeFetch(200, { token: "1767225600.abc", expires_in: 43200 });

    await signIn(SERVER, "correct-horse", server.fetchFn);

    expect(server.sent).toHaveLength(1);
    expect(server.sent[0].url).toBe(`${SERVER}/auth/session`);
    expect(server.sent[0].init?.method).toBe("POST");
    expect(JSON.parse(String(server.sent[0].init?.body))).toEqual({ code: "correct-horse" });
    expect(storedToken()).toBe("1767225600.abc");
  });

  it("refuses a wrong pass code, keeping no token", async () => {
    const server = fakeFetch(401, {});

    await expect(signIn(SERVER, "guess", server.fetchFn)).rejects.toThrow("access code");
    expect(sessionStorage.getItem(SESSION_KEY)).toBeNull();
  });

  it("sends the session token as a bearer header on every call", async () => {
    const headers = await headersAfter(sessionInterceptor(() => "1767225600.abc"));

    expect(headers.get("authorization")).toBe("Bearer 1767225600.abc");
  });

  it("sends no authorization header before signing in", async () => {
    const headers = await headersAfter(sessionInterceptor(() => null));

    expect(headers.has("authorization")).toBe(false);
  });

  it("asks the agent whether the tab must sign in", async () => {
    const server = fakeFetch(200, { gated: true, signed_in: false });

    const status = await sessionStatus(SERVER, server.fetchFn);

    expect(status).toEqual({ gated: true, signedIn: false });
    expect(server.sent[0].url).toBe(`${SERVER}/auth/session`);
  });

  it("asks with the tab's session token once it has one", async () => {
    sessionStorage.setItem(SESSION_KEY, "1767225600.abc");
    const server = fakeFetch(200, { gated: true, signed_in: true });

    await sessionStatus(SERVER, server.fetchFn);

    expect(new Headers(server.sent[0].init?.headers).get("authorization")).toBe("Bearer 1767225600.abc");
  });

  it("takes an agent that cannot say as one with no gate", async () => {
    const server = fakeFetch(404, {});

    const status = await sessionStatus(SERVER, server.fetchFn);

    expect(status).toEqual({ gated: false, signedIn: true });
  });

  it("takes an agent it cannot reach as one with no gate", async () => {
    const unreachable = (async () => {
      throw new TypeError("Failed to fetch");
    }) as typeof fetch;

    const status = await sessionStatus(SERVER, unreachable);

    expect(status).toEqual({ gated: false, signedIn: true });
  });

  it("talks to the page's own origin when the agent serves the page", () => {
    expect(defaultServerUrl({ origin: SERVER }, false)).toBe(SERVER);
  });

  it("talks to the local agent under the Vite dev server", () => {
    expect(defaultServerUrl({ origin: "http://localhost:5173" }, true)).toBe(DEFAULT_SERVER_URL);
  });
});
