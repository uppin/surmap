import { Code, ConnectError } from "@connectrpc/connect";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { TurnEvent } from "@/gen/surmap/agent/v1/chat_pb";
import { aModel } from "@/test-support/view-items";
import { aConversation } from "@/test-support/turn-events";
import type { ChatPort, ModelInfo, StreamTurnInput } from "@/ports";
import App from "./App";

interface FakePortOptions {
  models?: ModelInfo[];
  /** The conversation's history, or `null` when the server has never seen it (`NOT_FOUND`). */
  history?: TurnEvent[] | null;
  /** The events the next turn streams. */
  turn?: TurnEvent[];
}

/** A stream with no events that ends when `signal` aborts, as a watch stream does with no job ending. */
function openUntilAborted(signal: AbortSignal): AsyncIterable<TurnEvent> {
  return {
    [Symbol.asyncIterator]: () => ({
      next: () =>
        new Promise<IteratorResult<TurnEvent>>((resolve) => {
          signal.addEventListener("abort", () => resolve({ done: true, value: undefined }));
        }),
    }),
  };
}

/** A ChatPort that records what the page asked of it. */
function fakePort(options: FakePortOptions = {}) {
  const asked = {
    streamTurn: [] as StreamTurnInput[],
    watch: [] as string[],
    getConversation: [] as string[],
  };
  const port: ChatPort = {
    async *streamTurn(input) {
      asked.streamTurn.push(input);
      yield* options.turn ?? [];
    },
    watch(conversationId, signal) {
      asked.watch.push(conversationId);
      return openUntilAborted(signal);
    },
    async steer() {
      return { accepted: false };
    },
    async cancelTurn() {},
    async cancelJob() {},
    async listModels() {
      return options.models ?? [aModel({ id: "meta:muse-spark", isDefault: true })];
    },
    async getConversation(conversationId) {
      asked.getConversation.push(conversationId);
      if (options.history === null) throw new ConnectError(`no conversation ${conversationId}`, Code.NotFound);
      return options.history ?? [];
    },
    async getMapScene() {
      return {
        sceneId: "default",
        revision: 0,
        camera: { centre: { lon: 8.5417, lat: 47.3769, altM: null }, zoom: 16, pitchDeg: 55, bearingDeg: -20 },
        objects: [],
        routes: [],
        layers: [],
      };
    },
  };
  return { port, asked };
}

describe("chat page", () => {
  beforeEach(() => {
    window.history.replaceState({}, "", "/?conversation=conv-9");
  });

  afterEach(() => {
    window.history.replaceState({}, "", "/");
    window.sessionStorage.clear();
  });

  it("lists the server's models and starts on the default one", async () => {
    const { port } = fakePort({
      models: [
        aModel({ id: "meta:muse-spark", isDefault: false }),
        aModel({ id: "ollama:qwen3", provider: "ollama", displayName: "Qwen 3", isDefault: true }),
      ],
    });

    render(<App port={port} />);

    expect(await screen.findByRole("combobox", { name: "Model" })).toHaveValue("ollama:qwen3");
  });

  it("sends the message through the port and shows the streamed reply", async () => {
    const { port, asked } = fakePort({
      turn: aConversation("conv-9").userMessage("Hello").textDelta("Hi there.").turnFinished("stop").build(),
    });
    render(<App port={port} />);
    const user = userEvent.setup();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Hi there.")).toBeInTheDocument();
    expect(asked.streamTurn).toEqual([{ conversationId: "conv-9", modelId: "meta:muse-spark", text: "Hello" }]);
  });

  it("opens the watch stream only once the server knows the conversation", async () => {
    const { port, asked } = fakePort({ history: null, turn: aConversation("conv-9").turnFinished().build() });
    render(<App port={port} />);
    const user = userEvent.setup();
    await screen.findByRole("combobox", { name: "Model" });
    expect(asked.watch).toEqual([]);

    await user.type(screen.getByRole("textbox", { name: "Message" }), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));

    await waitFor(() => expect(asked.watch).toEqual(["conv-9"]));
  });

  it("keeps one conversation per tab when the URL names none", async () => {
    window.history.replaceState({}, "", "/");
    const first = fakePort({ turn: aConversation().turnFinished().build() });
    const firstRender = render(<App port={first.port} />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Message" }), "One");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(first.asked.streamTurn).toHaveLength(1));
    firstRender.unmount();

    const second = fakePort({ turn: aConversation().turnFinished().build() });
    render(<App port={second.port} />);
    await screen.findByRole("combobox", { name: "Model" });
    await user.type(screen.getByRole("textbox", { name: "Message" }), "Two");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(second.asked.streamTurn).toHaveLength(1));

    expect(second.asked.streamTurn[0]?.conversationId).toBe(first.asked.streamTurn[0]?.conversationId);
  });
});
