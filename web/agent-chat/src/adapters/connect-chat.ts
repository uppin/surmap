import type { Transport } from "@connectrpc/connect";
import type { ChatPort } from "@/ports";

/** The header `AgentJobs` calls name their conversation in; each conversation has its own jobs. */
export const CONVERSATION_HEADER = "surmap-conversation-id";

/** The agent server's default address. */
export const DEFAULT_SERVER_URL = "http://127.0.0.1:8780";

/** A Connect transport to the agent server at `baseUrl`. */
export function createAgentTransport(baseUrl: string): Transport {
  void baseUrl;
  throw new Error("TODO(pr-9): implement");
}

/** The `ChatPort` over the generated `ChatService` and `AgentJobs` clients. */
export function createConnectChatPort(transport: Transport): ChatPort {
  void transport;
  throw new Error("TODO(pr-9): implement");
}
