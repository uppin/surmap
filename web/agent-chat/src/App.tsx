import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChatPage } from "./ChatPage";
import { LandingPage } from "./LandingPage";
import { createAgentTransport, createConnectChatPort } from "./adapters/connect-chat";
import {
  defaultServerUrl,
  sessionInterceptor,
  sessionStatus as askSessionStatus,
  signIn as signInWithCode,
  storedToken,
  type SessionStatus,
} from "./adapters/session";
import type { ChatPort } from "./ports";

export interface AppProps {
  /** The port to chat through; by default, a Connect port to the `?server=` agent server. */
  port?: ChatPort;
  /** Trades a pass code for a session; by default, `POST /auth/session` on the agent server. */
  signIn?: (code: string) => Promise<void>;
  /** Whether this tab must sign in; by default, `GET /auth/session` on the agent server. */
  sessionStatus?: () => Promise<SessionStatus>;
  /**
   * The agent's stereo bridge the simulation preview streams to; by default, the build's
   * `VITE_SURMAP_BRIDGE_URL`. Never read from the page URL: a link naming a bridge would stream
   * the drone's camera to whatever socket it names.
   */
  bridgeUrl?: string;
}

/** Which screen the app shows: nothing while it asks the agent, the landing page, or the chat. */
type View = { kind: "checking" } | { kind: "landing"; needsCode: boolean; error: string | null } | { kind: "chat" };

/**
 * The chat app. It opens on the landing page (`LandingPage`: the repository and the way in) unless
 * the URL names a conversation. On a gated agent, a tab that is not signed in always gets the
 * landing page, which asks for the pass code, and then opens the chat it was on.
 *
 * `?server=` names the agent server (default: this page's origin, or `http://127.0.0.1:8780`
 * under the Vite dev server). `?code=` is the agent's access code: it is traded for a session
 * token once and dropped from the URL; the chat opens when the agent takes it, the landing page
 * with the refusal when it does not. `?conversation=` names the conversation and `?model=` the
 * model its turns use. The stereo bridge the simulation preview streams to is configuration
 * (`VITE_SURMAP_BRIDGE_URL`), never a URL parameter. Once the chat opens, the page writes the
 * conversation (a new one when the URL names none) and the model in use back into the URL, so a
 * reload reopens the same chat on the same model.
 */
export default function App(props: AppProps): ReactNode {
  const [params] = useState(() => new URLSearchParams(window.location.search));
  const serverUrl = params.get("server") ?? defaultServerUrl(window.location, import.meta.env.DEV);
  const bridgeUrl = props.bridgeUrl ?? (import.meta.env.VITE_SURMAP_BRIDGE_URL as string | undefined);
  const [conversationId] = useState(() => params.get("conversation") ?? crypto.randomUUID());
  const [view, setView] = useState<View>({ kind: "checking" });
  const code = params.get("code");
  const signIn = useMemo(
    () => props.signIn ?? ((value: string) => signInWithCode(serverUrl, value)),
    [props.signIn, serverUrl],
  );
  const status = useMemo(
    () => props.sessionStatus ?? (() => askSessionStatus(serverUrl)),
    [props.sessionStatus, serverUrl],
  );
  useEffect(() => {
    let live = true;
    const show = (next: View) => {
      if (live) setView(next);
    };
    if (code !== null) {
      // Taken or refused, the code leaves the URL.
      signIn(code)
        .then(() => show({ kind: "chat" }))
        .catch((refused: unknown) =>
          show({ kind: "landing", needsCode: true, error: refused instanceof Error ? refused.message : String(refused) }),
        )
        .finally(() => dropUrlParam("code"));
    } else {
      void status().then(({ gated, signedIn }) => {
        const needsCode = gated && !signedIn;
        show(!needsCode && params.has("conversation") ? { kind: "chat" } : { kind: "landing", needsCode, error: null });
      });
    }
    return () => {
      live = false;
    };
  }, [code, signIn, status, params]);
  useEffect(() => {
    if (view.kind === "chat") setUrlParam("conversation", conversationId);
  }, [view.kind, conversationId]);
  const port = useMemo(
    () =>
      props.port ??
      createConnectChatPort(createAgentTransport(serverUrl, [sessionInterceptor()]), serverUrl, storedToken),
    [props.port, serverUrl],
  );
  if (view.kind === "checking") return null;
  if (view.kind === "landing") {
    return (
      <LandingPage
        needsCode={view.needsCode}
        signIn={signIn}
        initialError={view.error}
        onEnter={() => setView({ kind: "chat" })}
      />
    );
  }
  return (
    <ChatPage
      port={port}
      serverUrl={serverUrl}
      bridgeUrl={bridgeUrl}
      conversationId={conversationId}
      initialModelId={params.get("model")}
      onModelChange={setUrlModel}
    />
  );
}

function setUrlModel(modelId: string): void {
  setUrlParam("model", modelId);
}

/** Sets one query parameter in place, without a history entry. */
function setUrlParam(name: string, value: string): void {
  const url = new URL(window.location.href);
  if (url.searchParams.get(name) === value) return;
  url.searchParams.set(name, value);
  window.history.replaceState(window.history.state, "", url);
}

function dropUrlParam(name: string): void {
  const url = new URL(window.location.href);
  if (!url.searchParams.has(name)) return;
  url.searchParams.delete(name);
  window.history.replaceState(window.history.state, "", url);
}
