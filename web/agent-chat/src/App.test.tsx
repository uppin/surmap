import { Code, ConnectError } from "@connectrpc/connect";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it } from "vitest";
import type { TurnEvent } from "@/gen/surmap/agent/v1/chat_pb";
import { aModel, aStation } from "@/test-support/view-items";
import { aConversation } from "@/test-support/turn-events";
import type { ChatPort, ModelInfo, StationView, StreamTurnInput } from "@/ports";
import App from "./App";

interface FakePortOptions {
  models?: ModelInfo[];
  /** The conversation's history, or `null` when the server has never seen it (`NOT_FOUND`). */
  history?: TurnEvent[] | null;
  /** The events the next turn streams. */
  turn?: TurnEvent[];
  datasets?: import("@/ports").DatasetView[];
  /** The SAM station's status, or `null` when the server has none (the default). */
  station?: StationView | null;
  /** What importing a simulation bundle answers; rejects with this message when a string. */
  imported?: import("@/view-model/simulation").SimulationView | string;
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

/** A turn in which the agent creates the scenario `id` at version 1. */
function aSimulationCreated(id: string, name: string): TurnEvent[] {
  const created = JSON.stringify({ scenario: { id, name, version: 1, credits: [], url: `/sim/?scenario=${id}` } });
  return aConversation("conv-9")
    .userMessage("Build it")
    .toolStarted("call-1", "create_scenario")
    .toolSucceeded("call-1", { resultJson: created })
    .textDelta("Built it.")
    .turnFinished("stop")
    .build();
}

function aBundle(name: string): File {
  return new File([new Uint8Array([0x50, 0x4b, 0x03, 0x04])], name, { type: "application/zip" });
}

/** A ChatPort that records what the page asked of it. */
function fakePort(options: FakePortOptions = {}) {
  const asked = {
    streamTurn: [] as StreamTurnInput[],
    watch: [] as string[],
    getConversation: [] as string[],
    station: [] as string[],
    importSimulation: [] as { name: string; into: string | null }[],
  };
  let station = options.station ?? null;
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
    async listDatasets() {
      return options.datasets ?? [];
    },
    async getStationStatus() {
      return station;
    },
    async startStation() {
      asked.station.push("start");
      station = aStation({ state: "ready", containers: 1 });
      return station;
    },
    async stopStation() {
      asked.station.push("stop");
      station = aStation({ state: "off" });
      return station;
    },
    async importSimulation(bundle, into) {
      asked.importSimulation.push({ name: bundle.name, into });
      if (typeof options.imported === "string") throw new Error(options.imported);
      if (options.imported === undefined) throw new Error("no import expected");
      return options.imported;
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
  });

  it("exchanges a ?code= for a session and drops the code from the URL", async () => {
    window.history.replaceState({}, "", "/?conversation=conv-9&code=correct-horse");
    const { port } = fakePort();
    const signedIn: string[] = [];

    render(<App port={port} signIn={async (code) => void signedIn.push(code)} />);

    await screen.findByRole("combobox", { name: "Model" });
    expect(signedIn).toEqual(["correct-horse"]);
    expect(new URLSearchParams(window.location.search).has("code")).toBe(false);
    expect(new URLSearchParams(window.location.search).get("conversation")).toBe("conv-9");
  });

  it("does not sign in when the URL carries no code", async () => {
    const { port } = fakePort();
    const signedIn: string[] = [];

    render(<App port={port} signIn={async (code) => void signedIn.push(code)} />);

    await screen.findByRole("combobox", { name: "Model" });
    expect(signedIn).toEqual([]);
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

  it("shows the SAM station's state in the header", async () => {
    const { port } = fakePort({ station: aStation({ state: "off" }) });

    render(<App port={port} />);

    expect(await screen.findByRole("status", { name: "SAM station" })).toHaveTextContent("SAM · off");
  });

  it("shows no SAM station when the server has none", async () => {
    const { port } = fakePort({ station: null });

    render(<App port={port} />);

    await screen.findByRole("combobox", { name: "Model" });
    expect(screen.queryByRole("status", { name: "SAM station" })).toBeNull();
  });

  it("starts the SAM station from the header and shows it come up", async () => {
    const { port, asked } = fakePort({ station: aStation({ state: "off" }) });
    render(<App port={port} />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Start SAM" }));

    expect(asked.station).toEqual(["start"]);
    expect(await screen.findByRole("status", { name: "SAM station" })).toHaveTextContent("SAM · ready");
  });

  it("stops the SAM station from the header", async () => {
    const { port, asked } = fakePort({ station: aStation({ state: "ready", containers: 1 }) });
    render(<App port={port} />);
    const user = userEvent.setup();

    await user.click(await screen.findByRole("button", { name: "Stop SAM" }));

    expect(asked.station).toEqual(["stop"]);
    expect(await screen.findByRole("status", { name: "SAM station" })).toHaveTextContent("SAM · off");
  });

  it("opens the dataset gallery as its own searchable screen", async () => {
    const { port } = fakePort({
      datasets: [
        {
          id: "kitti-2011_09_26_drive_0001",
          title: "KITTI 2011-09-26 drive 0001",
          description: "Karlsruhe drive.",
          provider: "KITTI",
          licenseName: "CC BY-NC-SA 3.0",
          licenseUrl: "https://creativecommons.org/licenses/by-nc-sa/3.0/",
          attribution: "KITTI, CC BY-NC-SA 3.0",
          modality: "grey",
          officialUrl: "https://www.cvlibs.net/datasets/kitti/raw_data.php",
          defaultPrompt: "car",
          prepared: false,
          frameCount: 0,
          thumbnailAvailable: false,
          thumbnailUrl: "https://example.invalid/thumb.jpg",
          locationLabel: "Karlsruhe area, Germany (approx.)",
          gpsCentre: { lon: 8.4059, lat: 49.0069 },
          gpsTrack: [],
          runs: [],
        },
      ],
    });
    render(<App port={port} />);
    const user = userEvent.setup();

    // The chat screen has no gallery cards
    await screen.findByRole("combobox", { name: "Model" });
    expect(screen.queryByText(/KITTI 2011-09-26 drive 0001/)).not.toBeInTheDocument();

    // The gallery is its own screen, searchable
    await user.click(screen.getByRole("button", { name: "Dataset gallery" }));
    expect(await screen.findByText(/KITTI 2011-09-26 drive 0001/)).toBeInTheDocument();
    expect(screen.getByLabelText("Search datasets")).toBeInTheDocument();
    expect(window.location.search).toContain("screen=gallery");

    // And back to chat
    await user.click(screen.getByRole("button", { name: "Chat" }));
    expect(screen.getByRole("textbox", { name: "Message" })).toBeInTheDocument();
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

  it("shows a simulation the agent creates in a right-side pane inside the chat", async () => {
    const created = JSON.stringify({
      scenario: {
        id: "downtown-blaze",
        name: "Downtown blaze",
        version: 1,
        manifest_json: "{}",
        credits: [],
        url: "/sim/?scenario=downtown-blaze",
        updated_at: "2026-11-04T10:00:00Z",
      },
    });
    const { port } = fakePort({
      turn: aConversation("conv-9")
        .userMessage("Build a downtown blaze")
        .toolStarted("call-1", "create_scenario")
        .toolSucceeded("call-1", { resultJson: created })
        .textDelta("Built it.")
        .turnFinished("stop")
        .build(),
    });
    render(<App port={port} />);
    const user = userEvent.setup();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "Build a downtown blaze");
    await user.click(screen.getByRole("button", { name: "Send" }));

    const pane = await screen.findByRole("region", { name: "Simulation" });
    expect(pane).toHaveTextContent("Downtown blaze");
    expect(screen.getByTitle("Simulation: Downtown blaze")).toHaveAttribute(
      "src",
      "http://127.0.0.1:8780/sim/?scenario=downtown-blaze",
    );
    // The chat stays beside the pane: transcript, composer and jobs are all still there.
    expect(screen.getByRole("log", { name: "Conversation" })).toHaveTextContent("Built it.");
    expect(screen.getByRole("textbox", { name: "Message" })).toBeInTheDocument();
    expect(screen.getByRole("region", { name: "Jobs" })).toBeInTheDocument();
  });

  it("imports a bundle into the pane's simulation and shows the version it became", async () => {
    const { port, asked } = fakePort({
      turn: aSimulationCreated("downtown-blaze", "Downtown blaze"),
      imported: { id: "downtown-blaze", name: "Downtown blaze", version: 2, url: "/sim/?scenario=downtown-blaze", credits: [] },
    });
    render(<App port={port} />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Message" }), "Build a downtown blaze");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const pane = await screen.findByRole("region", { name: "Simulation" });

    await user.upload(screen.getByLabelText("Import simulation"), aBundle("flooded.surmap-sim.zip"));

    await waitFor(() => expect(pane).toHaveTextContent("v2"));
    expect(asked.importSimulation).toEqual([{ name: "flooded.surmap-sim.zip", into: "downtown-blaze" }]);
  });

  it("says why an import was refused and keeps the simulation it had", async () => {
    const { port } = fakePort({
      turn: aSimulationCreated("downtown-blaze", "Downtown blaze"),
      imported: "not a SurMap scenario bundle",
    });
    render(<App port={port} />);
    const user = userEvent.setup();
    await user.type(screen.getByRole("textbox", { name: "Message" }), "Build a downtown blaze");
    await user.click(screen.getByRole("button", { name: "Send" }));
    const pane = await screen.findByRole("region", { name: "Simulation" });

    await user.upload(screen.getByLabelText("Import simulation"), aBundle("notes.txt"));

    expect(await screen.findByRole("alert")).toHaveTextContent("not a SurMap scenario bundle");
    expect(pane).toHaveTextContent("v1");
  });

  it("shows no simulation pane when the agent created no simulation", async () => {
    const { port } = fakePort({
      turn: aConversation("conv-9").userMessage("Hello").textDelta("Hi there.").turnFinished("stop").build(),
    });
    render(<App port={port} />);
    const user = userEvent.setup();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));

    expect(await screen.findByText("Hi there.")).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Simulation" })).not.toBeInTheDocument();
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

  it("names a new conversation in the URL when the URL names none", async () => {
    window.history.replaceState({}, "", "/?server=http://agent.test");
    const { port, asked } = fakePort({ turn: aConversation().turnFinished().build() });
    render(<App port={port} />);
    const user = userEvent.setup();

    await user.type(screen.getByRole("textbox", { name: "Message" }), "Hello");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(asked.streamTurn).toHaveLength(1));

    expect({ conversation: urlParam("conversation"), server: urlParam("server") }).toEqual({
      conversation: asked.streamTurn[0]?.conversationId,
      server: "http://agent.test",
    });
  });

  it("names the model in use in the URL", async () => {
    const { port } = fakePort({ models: TWO_MODELS });
    render(<App port={port} />);
    const user = userEvent.setup();
    await screen.findByRole("combobox", { name: "Model" });
    await waitFor(() => expect(urlParam("model")).toBe("meta:muse-spark"));

    await user.selectOptions(screen.getByRole("combobox", { name: "Model" }), "fireworks:kimi-k3");

    expect(urlParam("model")).toBe("fireworks:kimi-k3");
  });

  it("keeps the conversation and its chosen model across a reload", async () => {
    window.history.replaceState({}, "", "/");
    const before = fakePort({ models: TWO_MODELS });
    const beforeReload = render(<App port={before.port} />);
    const user = userEvent.setup();
    await screen.findByRole("option", { name: /Kimi K3/ });
    await user.selectOptions(screen.getByRole("combobox", { name: "Model" }), "fireworks:kimi-k3");
    const conversationId = urlParam("conversation");
    beforeReload.unmount();

    const after = fakePort({ models: TWO_MODELS, turn: aConversation().turnFinished().build() });
    render(<App port={after.port} />);
    await screen.findByRole("option", { name: /Kimi K3/ });
    await user.type(screen.getByRole("textbox", { name: "Message" }), "Still there?");
    await user.click(screen.getByRole("button", { name: "Send" }));
    await waitFor(() => expect(after.asked.streamTurn).toHaveLength(1));

    expect(after.asked.streamTurn[0]).toMatchObject({ conversationId, modelId: "fireworks:kimi-k3" });
  });

  it("falls back to the default model when the URL names one the server does not list", async () => {
    window.history.replaceState({}, "", "/?conversation=conv-9&model=ollama:gone");
    const { port } = fakePort({ models: TWO_MODELS });

    render(<App port={port} />);

    await waitFor(() => expect(screen.getByRole("combobox", { name: "Model" })).toHaveValue("meta:muse-spark"));
    expect(urlParam("model")).toBe("meta:muse-spark");
  });
});

const TWO_MODELS: ModelInfo[] = [
  aModel({ id: "meta:muse-spark", isDefault: true }),
  aModel({ id: "fireworks:kimi-k3", provider: "fireworks", displayName: "Kimi K3" }),
];

function urlParam(name: string): string | null {
  return new URLSearchParams(window.location.search).get(name);
}
