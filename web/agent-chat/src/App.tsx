import { useEffect, useMemo, useState, type ReactNode } from "react";
import { ChatPage } from "./ChatPage";
import { createAgentTransport, createConnectChatPort, DEFAULT_SERVER_URL } from "./adapters/connect-chat";
import type { ChatPort } from "./ports";

export interface AppProps {
  /** The port to chat through; by default, a Connect port to the `?server=` agent server. */
  port?: ChatPort;
}

/**
 * The chat page. `?server=` names the agent server (default `http://127.0.0.1:8780`),
 * `?conversation=` the conversation and `?model=` the model its turns use. The page writes the
 * conversation (a new one when the URL names none) and the model in use back into the URL, so a
 * reload reopens the same chat on the same model.
 */
export default function App(props: AppProps): ReactNode {
  const [params] = useState(() => new URLSearchParams(window.location.search));
  const serverUrl = params.get("server") ?? DEFAULT_SERVER_URL;
  const [conversationId] = useState(() => params.get("conversation") ?? crypto.randomUUID());
  useEffect(() => setUrlParam("conversation", conversationId), [conversationId]);
  const port = useMemo(
    () => props.port ?? createConnectChatPort(createAgentTransport(serverUrl)),
    [props.port, serverUrl],
  );
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
