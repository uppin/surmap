import { describe, expect, it } from "vitest";
import {
  T0,
  TICK_MS,
  aChatState,
  arrivalOf,
  dispatch,
  jobOf,
  kindsOf,
  receive,
  subagentOf,
  toolStepOf,
} from "@/test-support/chat-driver";
import {
  ASYNC_JOB,
  SYNC_30_THEN_DETACH,
  aConversation,
  jobHandle,
} from "@/test-support/turn-events";
import { aModel, ONE_PIXEL_PNG } from "@/test-support/view-items";
import { isAwaitingReply, isTurnActive } from "./chat-reducer";

describe("chatReducer", () => {
  it("records the user's message from the turn's user_message event", () => {
    const turn = aConversation().userMessage("Survey the warehouse").build();

    const state = receive(aChatState(), turn);

    expect(state.transcript).toMatchObject([
      { kind: "user", turnId: "turn-1", text: "Survey the warehouse" },
    ]);
  });

  it("joins a turn's streamed text deltas into one assistant message", () => {
    const turn = aConversation()
      .userMessage("What demos are there?")
      .textDelta("Three demos ")
      .textDelta("are ready.")
      .build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect(state.transcript.at(-1)).toMatchObject({
      kind: "assistant",
      turnId: "turn-1",
      text: "Three demos are ready.",
    });
  });

  it("starts a new assistant message for text that follows a tool call", () => {
    const turn = aConversation()
      .userMessage("Run the EuRoC demo")
      .textDelta("Starting it.")
      .toolStarted("call-1", "run_demo")
      .toolSucceeded("call-1")
      .textDelta("It finished.")
      .build();

    const state = receive(aChatState(), turn);

    expect(kindsOf(state)).toEqual(["user", "assistant", "tool", "assistant"]);
  });

  it("adds a running tool step carrying the call's resolved execution policy", () => {
    const turn = aConversation()
      .userMessage("Run the EuRoC demo")
      .toolStarted("call-1", "run_demo", {
        argumentsJson: '{"dataset":"euroc-v1-01-easy"}',
        policy: SYNC_30_THEN_DETACH,
      })
      .build();

    const state = receive(aChatState(), turn);

    expect(toolStepOf(state, "call-1")).toMatchObject({
      tool: "run_demo",
      argumentsJson: '{"dataset":"euroc-v1-01-easy"}',
      policy: { mode: "SYNC", timeoutS: 30, onTimeout: "DETACH" },
      status: "running",
      startedAt: arrivalOf(1),
      finishedAt: null,
    });
  });

  it("keeps a step without a policy when the server sent none", () => {
    const turn = aConversation().toolStarted("call-1", "list_demos", { policy: null }).build();

    const state = receive(aChatState(), turn);

    expect(toolStepOf(state, "call-1")).toMatchObject({ policy: null, status: "running" });
  });

  it("marks a succeeded call done with its result and the time it finished", () => {
    const turn = aConversation()
      .toolStarted("call-1", "list_demos")
      .toolSucceeded("call-1", { resultJson: '{"demos":["euroc-v1-01-easy"]}' })
      .build();

    const state = receive(aChatState(), turn);

    expect(toolStepOf(state, "call-1")).toMatchObject({
      status: "succeeded",
      resultJson: '{"demos":["euroc-v1-01-easy"]}',
      startedAt: T0,
      finishedAt: T0 + TICK_MS,
    });
  });

  it("marks a failed call failed with the error the tool returned", () => {
    const turn = aConversation()
      .toolStarted("call-1", "get_object")
      .toolFailed("call-1", '{"error":"no object obj-9 in run run-7"}')
      .build();

    const state = receive(aChatState(), turn);

    expect(toolStepOf(state, "call-1")).toMatchObject({
      status: "failed",
      resultJson: '{"error":"no object obj-9 in run run-7"}',
    });
  });

  it("keeps the image a frame result carries, with its media type", () => {
    const turn = aConversation()
      .toolStarted("call-1", "get_frame")
      .toolSucceeded("call-1", { image: ONE_PIXEL_PNG, mediaType: "image/png" })
      .build();

    const state = receive(aChatState(), turn);

    expect(toolStepOf(state, "call-1")?.image).toEqual({
      bytes: ONE_PIXEL_PNG,
      mediaType: "image/png",
    });
  });

  it("marks a detached call detached and moves its job into the tasks panel", () => {
    const turn = aConversation()
      .toolStarted("call-1", "run_demo")
      .toolDetached("call-1", { jobId: "job-7", tool: "run_demo" })
      .build();

    const state = receive(aChatState(), turn);

    expect({ step: toolStepOf(state, "call-1"), job: jobOf(state, "job-7") }).toMatchObject({
      step: { status: "detached", jobId: "job-7" },
      job: { tool: "run_demo", status: "running", callId: "call-1", startedAt: T0 + TICK_MS },
    });
  });

  it("puts the job of an ASYNC call that returned its handle into the tasks panel", () => {
    const turn = aConversation()
      .toolStarted("call-1", "run_demo", { policy: ASYNC_JOB })
      .toolSucceeded("call-1", { job: jobHandle({ jobId: "job-8", tool: "run_demo" }) })
      .build();

    const state = receive(aChatState(), turn);

    expect(jobOf(state, "job-8")).toMatchObject({ tool: "run_demo", status: "running" });
  });

  it("adds a steer marker naming the calls the guidance detached", () => {
    const turn = aConversation()
      .userMessage("Run the EuRoC demo")
      .toolStarted("call-1", "run_demo")
      .steerApplied("Use the KITTI scene instead", ["call-1"])
      .build();

    const state = receive(aChatState(), turn);

    expect(state.transcript.at(-1)).toMatchObject({
      kind: "steer",
      text: "Use the KITTI scene instead",
      detachedCallIds: ["call-1"],
    });
  });

  it("shows a subagent's message inside a running turn", () => {
    const turn = aConversation()
      .userMessage("Build me a wildfire scene")
      .toolStarted("call-1", "start_subagent")
      .toolSucceeded("call-1")
      .subagentMessage("sa-1", "scene-builder", "Which side should the fire start on?")
      .build();

    const state = receive(aChatState(), turn);

    expect(state.transcript.at(-1)).toMatchObject({
      kind: "subagent_message",
      turnId: "turn-1",
      subagentId: "sa-1",
      name: "scene-builder",
      text: "Which side should the fire start on?",
    });
  });

  it("opens a turn with the subagent's message that started it", () => {
    const subagentTurn = aConversation("conv-1", 5n)
      .inTurn("turn-2")
      .subagentMessage("sa-1", "scene-builder", "Which side should the fire start on?")
      .textDelta("The builder asks where the fire starts.")
      .build();

    const state = receive(aChatState(), subagentTurn);

    expect(kindsOf(state)).toEqual(["subagent_message", "assistant"]);
  });

  it("renders a job_update that opens a turn as a notice for the job that ended", () => {
    const jobTurn = aConversation("conv-1", 5n)
      .inTurn("turn-2")
      .jobUpdate({ jobId: "job-7", tool: "run_demo", status: "succeeded", detail: "run run-7 ended" })
      .textDelta("The demo finished.")
      .build();

    const state = receive(aChatState(), jobTurn);

    expect(state.transcript[0]).toMatchObject({
      kind: "job_notice",
      turnId: "turn-2",
      jobId: "job-7",
      tool: "run_demo",
      status: "succeeded",
      detail: "run run-7 ended",
    });
  });

  it("updates the tasks panel, without a notice, for a job_update inside a running turn", () => {
    const turn = aConversation()
      .userMessage("Run the EuRoC demo")
      .toolStarted("call-1", "run_demo")
      .toolDetached("call-1", { jobId: "job-7", tool: "run_demo" })
      .jobUpdate({ jobId: "job-7", tool: "run_demo", status: "failed", detail: "SAM unreachable" })
      .build();

    const state = receive(aChatState(), turn);

    expect({ kinds: kindsOf(state), job: jobOf(state, "job-7") }).toMatchObject({
      kinds: ["user", "tool"],
      job: { status: "failed", detail: "SAM unreachable", updatedAt: arrivalOf(3) },
    });
  });

  it("adds a started subagent to the tasks panel, running as its turn's job", () => {
    const turn = aConversation()
      .userMessage("A tree and a house")
      .toolStarted("call-1", "start_subagent")
      .subagentStatus({ subagentId: "sa-1", name: "scene-builder", jobId: "job-4", status: "running" })
      .build();

    const state = receive(aChatState(), turn);

    expect(subagentOf(state, "sa-1")).toMatchObject({
      name: "scene-builder",
      jobId: "job-4",
      status: "running",
      detail: "",
      startedAt: arrivalOf(2),
    });
  });

  it("shows what a subagent last reported doing", () => {
    const statuses = aConversation()
      .subagentStatus({ subagentId: "sa-1", name: "scene-builder", jobId: "job-4", status: "running" })
      .subagentStatus({
        subagentId: "sa-1",
        name: "scene-builder",
        jobId: "job-4",
        status: "running",
        detail: "Placing the house",
      })
      .build();

    const state = receive(aChatState(), statuses);

    expect(subagentOf(state, "sa-1")).toMatchObject({
      detail: "Placing the house",
      startedAt: arrivalOf(0),
      updatedAt: arrivalOf(1),
    });
  });

  it("ignores a subagent status older than the one it already shows", () => {
    const [placing, started] = [
      aConversation("conv-1", 6n).subagentStatus({
        subagentId: "sa-1",
        name: "scene-builder",
        jobId: "job-4",
        status: "running",
        detail: "Placing the house",
      }),
      aConversation("conv-1", 5n).subagentStatus({
        subagentId: "sa-1",
        name: "scene-builder",
        jobId: "job-4",
        status: "running",
      }),
    ].map((script) => script.build());

    const state = receive(aChatState(), [...placing, ...started]);

    expect(subagentOf(state, "sa-1")?.detail).toBe("Placing the house");
  });

  it("restarts a subagent's clock when a follow-up turn runs it as a new job", () => {
    const statuses = aConversation()
      .subagentStatus({ subagentId: "sa-1", name: "scene-builder", jobId: "job-4", status: "succeeded" })
      .subagentStatus({ subagentId: "sa-1", name: "scene-builder", jobId: "job-6", status: "running" })
      .build();

    const state = receive(aChatState(), statuses);

    expect(subagentOf(state, "sa-1")).toMatchObject({ jobId: "job-6", status: "running", startedAt: arrivalOf(1) });
  });

  it("keeps the conversation idle, with nothing in the transcript, for a subagent status between turns", () => {
    const status = aConversation("conv-1", 9n)
      .subagentStatus({
        subagentId: "sa-1",
        name: "scene-builder",
        jobId: "job-4",
        status: "running",
        detail: "Placing the house",
      })
      .build();

    const state = receive(aChatState(), status);

    expect({ active: isTurnActive(state), kinds: kindsOf(state) }).toEqual({ active: false, kinds: [] });
  });

  it("keeps a running turn's events after a subagent status that arrived first with a later seq", () => {
    const turn = aConversation().userMessage("A tree and a house").build();
    const status = aConversation("conv-1", 3n)
      .subagentStatus({ subagentId: "sa-1", name: "scene-builder", jobId: "job-4", status: "running" })
      .build();
    const reply = aConversation("conv-1", 2n).textDelta("Started the builder.").build();

    const state = receive(aChatState(), [...turn, ...status, ...reply]);

    expect(kindsOf(state)).toEqual(["user", "assistant"]);
  });

  it("is busy from the moment a turn is requested", () => {
    const state = aChatState({ type: "turn_requested" });

    expect(isTurnActive(state)).toBe(true);
  });

  it("is running the turn whose events are arriving", () => {
    const turn = aConversation().inTurn("turn-3").userMessage("Find the boxes").build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect({ phase: state.phase, turnId: state.turnId }).toEqual({
      phase: "running",
      turnId: "turn-3",
    });
  });

  it("goes back to idle when the turn finishes", () => {
    const turn = aConversation().userMessage("Hello").textDelta("Hi.").turnFinished("stop").build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect({ phase: state.phase, turnId: state.turnId, busy: isTurnActive(state) }).toEqual({
      phase: "idle",
      turnId: null,
      busy: false,
    });
  });

  it("awaits a reply from the moment a turn is requested", () => {
    const state = aChatState({ type: "turn_requested" });

    expect(isAwaitingReply(state)).toBe(true);
  });

  it("awaits a reply after the user's message until the agent answers", () => {
    const turn = aConversation().userMessage("Find the boxes").build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect(isAwaitingReply(state)).toBe(true);
  });

  it("no longer awaits a reply while the agent's text is streaming", () => {
    const turn = aConversation().userMessage("Hello").textDelta("Hi").build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect(isAwaitingReply(state)).toBe(false);
  });

  it("does not await a reply while a tool step shows its own progress", () => {
    const turn = aConversation().userMessage("Run the EuRoC demo").toolStarted("call-1", "run_demo").build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect(isAwaitingReply(state)).toBe(false);
  });

  it("awaits a reply again once a tool call finishes", () => {
    const turn = aConversation()
      .userMessage("Run the EuRoC demo")
      .toolStarted("call-1", "run_demo")
      .toolSucceeded("call-1")
      .build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect(isAwaitingReply(state)).toBe(true);
  });

  it("does not await a reply once the turn finishes", () => {
    const turn = aConversation().userMessage("Hello").turnFinished("stop").build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect(isAwaitingReply(state)).toBe(false);
  });

  it("is stopping, and still busy, after Stop until the turn finishes", () => {
    const turn = aConversation().userMessage("Run the EuRoC demo").build();
    const running = receive(aChatState({ type: "turn_requested" }), turn);

    const state = dispatch(running, { type: "stop_requested" });

    expect({ phase: state.phase, busy: isTurnActive(state) }).toEqual({
      phase: "stopping",
      busy: true,
    });
  });

  it("marks the calls a cancelled turn cancelled and returns to idle", () => {
    const turn = aConversation()
      .userMessage("Run the EuRoC demo")
      .toolStarted("call-1", "run_demo")
      .toolCancelled("call-1")
      .turnFinished("cancelled")
      .build();

    const state = receive(dispatch(aChatState({ type: "turn_requested" }), { type: "stop_requested" }), turn);

    expect({ phase: state.phase, step: toolStepOf(state, "call-1")?.status }).toEqual({
      phase: "idle",
      step: "cancelled",
    });
  });

  it("shows a turn's error event in the transcript", () => {
    const turn = aConversation()
      .userMessage("Hello")
      .error("Muse is unreachable")
      .turnFinished("error")
      .build();

    const state = receive(aChatState({ type: "turn_requested" }), turn);

    expect(state.transcript.at(-1)).toMatchObject({
      kind: "error",
      turnId: "turn-1",
      message: "Muse is unreachable",
    });
  });

  it("shows a broken stream as an error and returns to idle", () => {
    const state = aChatState(
      { type: "turn_requested" },
      { type: "stream_failed", message: "the agent server closed the stream" },
    );

    expect({ phase: state.phase, last: state.transcript.at(-1) }).toMatchObject({
      phase: "idle",
      last: { kind: "error", turnId: null, message: "the agent server closed the stream" },
    });
  });

  it("ignores an event it has already applied, by seq", () => {
    const turn = aConversation().userMessage("Hello").textDelta("Hi.").build();
    const seen = receive(aChatState(), turn);

    const state = receive(seen, turn.slice(1));

    expect(state.transcript).toMatchObject([
      { kind: "user", text: "Hello" },
      { kind: "assistant", text: "Hi." },
    ]);
  });

  it("redraws a loaded conversation the same as streaming it, and stays idle", () => {
    const history = aConversation()
      .userMessage("Run the EuRoC demo")
      .toolStarted("call-1", "run_demo")
      .toolSucceeded("call-1")
      .textDelta("Done.")
      .turnFinished("stop")
      .build();

    const state = aChatState({ type: "history_loaded", events: history, at: T0 });

    expect({ kinds: kindsOf(state), phase: state.phase, lastSeq: state.lastSeq }).toEqual({
      kinds: ["user", "tool", "assistant"],
      phase: "idle",
      lastSeq: 5n,
    });
  });

  it("picks the server's default model when models load and none is chosen", () => {
    const models = [
      aModel({ id: "meta:muse-spark" }),
      aModel({ id: "ollama:qwen3", provider: "ollama", isDefault: true }),
    ];

    const state = aChatState({ type: "models_loaded", models });

    expect({ modelId: state.modelId, count: state.models.length }).toEqual({
      modelId: "ollama:qwen3",
      count: 2,
    });
  });

  it("keeps the user's chosen model when models load again", () => {
    const models = [aModel({ id: "meta:muse-spark", isDefault: true }), aModel({ id: "ollama:qwen3" })];

    const state = aChatState(
      { type: "models_loaded", models },
      { type: "model_selected", modelId: "ollama:qwen3" },
      { type: "models_loaded", models },
    );

    expect(state.modelId).toBe("ollama:qwen3");
  });
});
