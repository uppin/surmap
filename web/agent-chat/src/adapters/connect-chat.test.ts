import { createRouterTransport } from "@connectrpc/connect";
import { describe, expect, it } from "vitest";
import { ChatService, type TurnEvent } from "@/gen/surmap/agent/v1/chat_pb";
import { AgentJobs } from "@/gen/surmap/agent/v1/jobs_pb";
import { jobHandle, aConversation } from "@/test-support/turn-events";
import type { ChatPort } from "@/ports";
import { CONVERSATION_HEADER, createConnectChatPort } from "./connect-chat";

interface FakeServerOptions {
  turn?: TurnEvent[];
  history?: TurnEvent[];
  steerAccepted?: boolean;
}

/** A ChatPort over an in-memory Connect server that records what the port sent it. */
function portOverFakeServer(options: FakeServerOptions = {}) {
  const received = {
    streamTurn: [] as { conversationId: string; text: string; modelId: string | undefined }[],
    steer: [] as { conversationId: string; text: string }[],
    cancelTurn: [] as string[],
    cancelJob: [] as { jobId: string; conversationHeader: string | null }[],
  };
  const transport = createRouterTransport(({ service }) => {
    service(ChatService, {
      async *streamTurn(request) {
        received.streamTurn.push({
          conversationId: request.conversationId,
          text: request.text,
          modelId: request.modelId,
        });
        yield* options.turn ?? [];
      },
      async *watchConversation() {},
      steer(request) {
        received.steer.push({ conversationId: request.conversationId, text: request.text });
        return { accepted: options.steerAccepted ?? true };
      },
      cancelTurn(request) {
        received.cancelTurn.push(request.conversationId);
        return { cancelled: true };
      },
      listModels() {
        return {
          defaultModelId: "ollama:qwen3",
          models: [
            { id: "meta:muse-spark", provider: "muse", displayName: "Muse Spark", available: true },
            { id: "ollama:qwen3", provider: "ollama", displayName: "Qwen 3", available: true },
          ],
        };
      },
      getConversation(request) {
        return { conversationId: request.conversationId, events: options.history ?? [] };
      },
    });
    service(AgentJobs, {
      cancelJob(request, context) {
        received.cancelJob.push({
          jobId: request.jobId,
          conversationHeader: context.requestHeader.get(CONVERSATION_HEADER),
        });
        return { job: jobHandle({ jobId: request.jobId, tool: "run_demo", status: "cancelled" }) };
      },
    });
  });
  return { port: createConnectChatPort(transport), received };
}

async function collect(stream: AsyncIterable<TurnEvent>): Promise<TurnEvent[]> {
  const events: TurnEvent[] = [];
  for await (const event of stream) events.push(event);
  return events;
}

function streamTurnOf(port: ChatPort, modelId: string | null) {
  return collect(
    port.streamTurn(
      { conversationId: "conv-1", modelId, text: "Survey the warehouse" },
      new AbortController().signal,
    ),
  );
}

describe("Connect ChatPort", () => {
  it("starts a turn with the conversation, the message and the chosen model", async () => {
    const server = portOverFakeServer();

    await streamTurnOf(server.port, "ollama:qwen3");

    expect(server.received.streamTurn).toEqual([
      { conversationId: "conv-1", text: "Survey the warehouse", modelId: "ollama:qwen3" },
    ]);
  });

  it("leaves the model to the server when none is chosen", async () => {
    const server = portOverFakeServer();

    await streamTurnOf(server.port, null);

    expect(server.received.streamTurn[0]?.modelId).toBeUndefined();
  });

  it("yields the turn's events in the order the server streamed them", async () => {
    const turn = aConversation().userMessage("Survey the warehouse").textDelta("On it.").turnFinished().build();
    const server = portOverFakeServer({ turn });

    const events = await streamTurnOf(server.port, null);

    expect(events.map((event) => [event.seq, event.event.case])).toEqual([
      [1n, "userMessage"],
      [2n, "textDelta"],
      [3n, "turnFinished"],
    ]);
  });

  it("reports a steer the server had no running turn for as not accepted", async () => {
    const server = portOverFakeServer({ steerAccepted: false });

    const outcome = await server.port.steer("conv-1", "Use the KITTI scene");

    expect({ outcome, sent: server.received.steer }).toEqual({
      outcome: { accepted: false },
      sent: [{ conversationId: "conv-1", text: "Use the KITTI scene" }],
    });
  });

  it("cancels the conversation's running turn", async () => {
    const server = portOverFakeServer();

    await server.port.cancelTurn("conv-1");

    expect(server.received.cancelTurn).toEqual(["conv-1"]);
  });

  it("names the conversation in the surmap-conversation-id header when it cancels a job", async () => {
    const server = portOverFakeServer();

    await server.port.cancelJob("conv-1", "job-7");

    expect(server.received.cancelJob).toEqual([{ jobId: "job-7", conversationHeader: "conv-1" }]);
  });

  it("lists the server's models with its default marked", async () => {
    const server = portOverFakeServer();

    const models = await server.port.listModels();

    expect(models.map((model) => [model.id, model.isDefault])).toEqual([
      ["meta:muse-spark", false],
      ["ollama:qwen3", true],
    ]);
  });

  it("returns a conversation's recorded events for redrawing it", async () => {
    const history = aConversation().userMessage("Hello").textDelta("Hi.").build();
    const server = portOverFakeServer({ history });

    const events = await server.port.getConversation("conv-1");

    expect(events.map((event) => event.seq)).toEqual([1n, 2n]);
  });
});
