import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChatPage } from "./ChatPage";
import { createAgentTransport, createConnectChatPort } from "./adapters/connect-chat";
import { defaultServerUrl, sessionInterceptor, signIn as signInWithCode } from "./adapters/session";
import type { ChatPort } from "./ports";

export interface AppProps {
  /** The port to chat through; by default, a Connect port to the `?server=` agent server. */
  port?: ChatPort;
  /** Trades a `?code=` for a session; by default, `POST /auth/session` on the agent server. */
  signIn?: (code: string) => Promise<void>;
}

/**
 * The chat page. `?server=` names the agent server (default: this page's origin, or
 * `http://127.0.0.1:8780` under the Vite dev server). `?code=` is the agent's access code: it is
 * traded for a session token once and dropped from the URL. `?server=` aside,
 * `?conversation=` the conversation and `?model=` the model its turns use. The page writes the
 * conversation (a new one when the URL names none) and the model in use back into the URL, so a
 * reload reopens the same chat on the same model.
 */
export default function App(props: AppProps): ReactNode {
  const [params] = useState(() => new URLSearchParams(window.location.search));
  const serverUrl = params.get("server") ?? defaultServerUrl(window.location, import.meta.env.DEV);
  const [conversationId] = useState(() => params.get("conversation") ?? crypto.randomUUID());
  useEffect(() => setUrlParam("conversation", conversationId), [conversationId]);
  const code = params.get("code");
  const [signedIn, setSignedIn] = useState(code === null);
  const signIn = props.signIn;
  useEffect(() => {
    if (code === null) return;
    const exchange = signIn ?? ((value: string) => signInWithCode(serverUrl, value));
    // Signed in or refused, the code leaves the URL; a refused page shows the agent's error.
    exchange(code).finally(() => {
      dropUrlParam("code");
      setSignedIn(true);
    });
  }, [code, signIn, serverUrl]);
  const port = useMemo(
    () =>
      props.port ??
      createConnectChatPort(createAgentTransport(serverUrl, [sessionInterceptor()]), serverUrl),
    [props.port, serverUrl],
  );
  if (!signedIn) return null;
  return (
    <ChatPage
      port={port}
      serverUrl={serverUrl}
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
