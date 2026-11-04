import { expect, test } from "@playwright/test";
import { aConversation, jobHandle } from "../src/test-support/turn-events";
import { ChatPage } from "./chat-page";
import { pointsGlb, startStubChatServer, type StubChatOptions, type StubChatServer } from "./stub-chat-server";

const ONE_PIXEL_PNG = Buffer.from(
  "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  "base64",
);

let stub: StubChatServer | undefined;

async function stubServer(options: StubChatOptions): Promise<StubChatServer> {
  stub = await startStubChatServer(options);
  return stub;
}

test.afterEach(async () => {
  await stub?.close();
  stub = undefined;
});

test("sending a message streams the reply and shows the tool call as a step with its policy", async ({ page }) => {
  const server = await stubServer({
    turn: async function* () {
      yield* aConversation()
        .toolStarted("call-1", "list_demos", { argumentsJson: "{}" })
        .toolSucceeded("call-1", { resultJson: '{"demos":["euroc-v1-01-easy"]}' })
        .textDelta("One demo is ready: ")
        .textDelta("**euroc-v1-01-easy**.")
        .turnFinished("stop")
        .build();
    },
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);

  await chat.send("What demos are there?");

  await expect(chat.toolStep("list_demos")).toContainText("SYNC 30 s → DETACH");
  await expect(chat.conversation()).toContainText("One demo is ready: euroc-v1-01-easy.");
});

test("typing while the agent works steers the turn and moves the detached call to the jobs panel", async ({ page }) => {
  const server = await stubServer({
    turn: async function* ({ nextSteer }) {
      yield* aConversation().toolStarted("call-1", "run_demo").build();
      const guidance = await nextSteer();
      yield* aConversation()
        .steerApplied(guidance, ["call-1"])
        .toolDetached("call-1", { jobId: "job-7", tool: "run_demo" })
        .textDelta("Switching to the KITTI scene.")
        .turnFinished("stop")
        .build();
    },
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);
  await chat.send("Run the EuRoC demo");
  await expect(chat.toolStep("run_demo")).toContainText("Running");

  await chat.steer("Use the KITTI scene instead");

  await expect(chat.conversation()).toContainText("Steered: Use the KITTI scene instead");
  await expect(chat.job("job-7")).toContainText("run_demo");
});

test("a job-event turn on the watch stream shows a notice for the job and the agent's reply", async ({ page }) => {
  const server = await stubServer({});
  const chat = new ChatPage(page);
  await chat.open(server.url);
  await server.watching("e2e-1");

  server.pushWatchTurn(
    "e2e-1",
    aConversation()
      .jobUpdate({ jobId: "job-7", tool: "run_demo", status: "succeeded", detail: "run run-7 ended" })
      .textDelta("The demo finished with 3 boxes.")
      .turnFinished("stop")
      .build(),
  );

  await expect(chat.conversation()).toContainText("Job job-7 (run_demo) succeeded");
  await expect(chat.conversation()).toContainText("The demo finished with 3 boxes.");
});

test("Stop cancels the running turn", async ({ page }) => {
  const server = await stubServer({
    turn: async function* ({ cancelled }) {
      yield* aConversation().toolStarted("call-1", "run_demo").build();
      await cancelled;
      yield* aConversation().toolCancelled("call-1").turnFinished("cancelled").build();
    },
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);
  await chat.send("Run the EuRoC demo");
  await expect(chat.toolStep("run_demo")).toContainText("Running");

  await chat.stop();

  await expect(chat.toolStep("run_demo")).toContainText("Cancelled");
  expect(server.received.cancelTurns).toEqual(["e2e-1"]);
});

test("Cancel in the jobs panel cancels that job on the server, naming the conversation", async ({ page }) => {
  const server = await stubServer({
    turn: async function* () {
      yield* aConversation()
        .toolStarted("call-1", "run_demo")
        .toolSucceeded("call-1", { job: jobHandle({ jobId: "job-9", tool: "run_demo" }) })
        .turnFinished("stop")
        .build();
    },
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);
  await chat.send("Start the EuRoC demo in the background");

  await chat.job("job-9").getByRole("button", { name: "Cancel" }).click();

  await expect.poll(() => server.received.cancelJobs).toEqual([{ conversationId: "e2e-1", jobId: "job-9" }]);
});

test("a frame result shows its image and a geometry result shows a 3D preview", async ({ page }) => {
  const server = await stubServer({
    glb: { "/geometry/run-7/obj-3.glb": pointsGlb([[0, 0, 0], [1, 0, 0], [0, 1, 0], [0, 0, 1]]) },
    turn: async function* () {
      yield* aConversation()
        .toolStarted("call-1", "get_frame")
        .toolSucceeded("call-1", { image: ONE_PIXEL_PNG, mediaType: "image/png" })
        .toolStarted("call-2", "get_object_geometry")
        .toolSucceeded("call-2", {
          resultJson: '{"obj_text":"v 0 0 0","geometry_uri":"/geometry/run-7/obj-3.glb","decimated_from":4}',
        })
        .turnFinished("stop")
        .build();
    },
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);

  await chat.send("Show me the box");

  await expect(chat.frameImage("get_frame")).toHaveJSProperty("naturalWidth", 1);
  await expect(chat.geometryPreview().locator("canvas")).toBeVisible();
  expect(server.received.geometry).toEqual(["/geometry/run-7/obj-3.glb"]);
});

test("a simulation the agent creates shows in a right-side pane inside the chat", async ({ page }) => {
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
  const server = await stubServer({
    turn: async function* () {
      yield* aConversation()
        .toolStarted("call-1", "create_scenario")
        .toolSucceeded("call-1", { resultJson: created })
        .textDelta("Built it.")
        .turnFinished("stop")
        .build();
    },
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);

  await chat.send("Build a downtown blaze");

  await expect(chat.simulation()).toContainText("Downtown blaze");
  await expect(chat.simulationFrame("Downtown blaze")).toHaveAttribute(
    "src",
    `${server.url}/sim/?scenario=downtown-blaze`,
  );
  await expect(chat.conversation()).toContainText("Built it.");
});

test("the model picker lists the server's models and the turn names the chosen one", async ({ page }) => {
  const server = await stubServer({
    models: [
      { id: "meta:muse-spark", provider: "muse", displayName: "Muse Spark" },
      { id: "ollama:qwen3", provider: "ollama", displayName: "Qwen 3" },
    ],
    defaultModelId: "meta:muse-spark",
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);
  await chat.modelPicker().selectOption({ label: "ollama · Qwen 3" });

  await chat.send("Hello");

  await expect.poll(() => server.received.turns.map((turn) => turn.modelId)).toEqual(["ollama:qwen3"]);
});

test("a reloaded page redraws the conversation from the server", async ({ page }) => {
  const server = await stubServer({
    history: {
      "e2e-1": aConversation("e2e-1")
        .userMessage("What demos are there?")
        .textDelta("Three demos are ready.")
        .turnFinished("stop")
        .build(),
    },
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);

  await chat.reload();

  await expect(chat.conversation()).toContainText(/What demos are there\?.*Three demos are ready\./);
});

test("a reloaded page still receives job-event turns on its new watch stream", async ({ page }) => {
  const server = await stubServer({
    history: {
      "e2e-1": aConversation("e2e-1").userMessage("Run the demo").turnFinished("stop").build(),
    },
  });
  const chat = new ChatPage(page);
  await chat.open(server.url);
  await server.watching("e2e-1");
  await chat.reload();
  await expect(chat.conversation()).toContainText("Run the demo");

  server.pushWatchTurn(
    "e2e-1",
    aConversation().textDelta("The demo finished after the reload.").turnFinished("stop").build(),
  );

  await expect(chat.conversation()).toContainText("The demo finished after the reload.");
});

test("the header shows the SAM station off, Start brings it up and Stop takes it down", async ({ page }) => {
  const server = await stubServer({ station: { state: "off" } });
  const chat = new ChatPage(page);
  await chat.open(server.url);

  await expect(chat.station()).toHaveText("SAM · off");
  await chat.startStation();
  await expect(chat.station()).toHaveText("SAM · ready");
  await chat.stopStation();
  await expect(chat.station()).toHaveText("SAM · off");

  expect(server.received.station).toEqual(["start", "stop"]);
});

test("an agent with no SAM station shows no station in the header", async ({ page }) => {
  const server = await stubServer({});
  const chat = new ChatPage(page);
  await chat.open(server.url);

  await expect(page.getByRole("combobox", { name: "Model" })).toBeVisible();
  await expect(chat.station()).toHaveCount(0);
});
