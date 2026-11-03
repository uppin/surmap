import { createClient, type Transport } from "@connectrpc/connect";
import { createConnectTransport } from "@connectrpc/connect-web";
import { ChatService } from "@/gen/surmap/agent/v1/chat_pb";
import { AgentJobs } from "@/gen/surmap/agent/v1/jobs_pb";
import type { ChatPort } from "@/ports";

/** The header `AgentJobs` calls name their conversation in; each conversation has its own jobs. */
export const CONVERSATION_HEADER = "surmap-conversation-id";

/** The agent server's default address. */
export const DEFAULT_SERVER_URL = "http://127.0.0.1:8780";

/** A Connect transport to the agent server at `baseUrl`. */
export function createAgentTransport(baseUrl: string): Transport {
  return createConnectTransport({ baseUrl });
}

/** The `ChatPort` over the generated `ChatService` and `AgentJobs` clients. */
export function createConnectChatPort(transport: Transport): ChatPort {
  const chat = createClient(ChatService, transport);
  const jobs = createClient(AgentJobs, transport);
  return {
    streamTurn: (input, signal) =>
      chat.streamTurn(
        {
          conversationId: input.conversationId,
          text: input.text,
          modelId: input.modelId ?? undefined,
        },
        { signal },
      ),
    watch: (conversationId, signal) => chat.watchConversation({ conversationId }, { signal }),
    async steer(conversationId, text) {
      const response = await chat.steer({ conversationId, text });
      return { accepted: response.accepted };
    },
    async cancelTurn(conversationId) {
      await chat.cancelTurn({ conversationId });
    },
    async cancelJob(conversationId, jobId) {
      await jobs.cancelJob(
        { jobId },
        { headers: { [CONVERSATION_HEADER]: conversationId } },
      );
    },
    async listModels() {
      const response = await chat.listModels({});
      return response.models.map((model) => ({
        id: model.id,
        provider: model.provider,
        displayName: model.displayName,
        available: model.available,
        detail: model.detail,
        isDefault: model.id === response.defaultModelId,
      }));
    },
    async getConversation(conversationId) {
      const response = await chat.getConversation({ conversationId });
      return response.events;
    },
  };
}
