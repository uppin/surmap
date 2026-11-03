import { useMemo, useState, type ReactNode } from "react";
import { ChatPage } from "./ChatPage";
import { createAgentTransport, createConnectChatPort, DEFAULT_SERVER_URL } from "./adapters/connect-chat";
import type { ChatPort } from "./ports";

const TAB_CONVERSATION_KEY = "surmap-agent-chat.conversation";

export interface AppProps {
  /** The port to chat through; by default, a Connect port to the `?server=` agent server. */
  port?: ChatPort;
}

/**
 * The chat page. `?server=` names the agent server (default `http://127.0.0.1:8780`) and
 * `?conversation=` the conversation; without it each tab keeps one conversation of its own.
 */
export default function App(props: AppProps): ReactNode {
  const [params] = useState(() => new URLSearchParams(window.location.search));
  const serverUrl = params.get("server") ?? DEFAULT_SERVER_URL;
  const [conversationId] = useState(() => params.get("conversation") ?? tabConversationId());
  const port = useMemo(
    () => props.port ?? createConnectChatPort(createAgentTransport(serverUrl)),
    [props.port, serverUrl],
  );
  return <ChatPage port={port} serverUrl={serverUrl} conversationId={conversationId} />;
}

function tabConversationId(): string {
  const stored = window.sessionStorage.getItem(TAB_CONVERSATION_KEY);
  if (stored !== null) return stored;
  const created = crypto.randomUUID();
  window.sessionStorage.setItem(TAB_CONVERSATION_KEY, created);
  return created;
}
