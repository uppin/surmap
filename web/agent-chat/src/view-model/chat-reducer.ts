import {
  ToolCallFinished_Status,
  type ToolCallFinished,
  type TurnEvent,
} from "@/gen/surmap/agent/v1/chat_pb";
import {
  ExecutionMode,
  JobStatus,
  OnTimeout,
  type ExecutionPolicy,
  type JobHandle,
} from "@/gen/surmap/agent/v1/execution_pb";
import type { ModelInfo } from "@/ports";
import type { JobState, JobView } from "./jobs";
import type {
  PolicyView,
  ToolImage,
  ToolStepStatus,
  TranscriptItem,
} from "./transcript";

/**
 * Where the conversation's turn is: `idle` (the composer starts a turn), `starting` (a turn was
 * sent and no event has arrived yet), `running` (events are arriving; the composer steers), and
 * `stopping` (Stop was pressed and the turn has not finished yet).
 */
export type TurnPhase = "idle" | "starting" | "running" | "stopping";

export interface ChatState {
  conversationId: string;
  /** The model the next turn names; `null` until models load and the user has not chosen. */
  modelId: string | null;
  models: ModelInfo[];
  phase: TurnPhase;
  /** The running turn; `null` while idle. */
  turnId: string | null;
  /** The highest event `seq` applied; events at or below it are already in the state. */
  lastSeq: bigint;
  transcript: TranscriptItem[];
  jobs: JobView[];
}

export type ChatAction =
  /** The user sent a message that starts a turn. */
  | { type: "turn_requested" }
  /** An event arrived on a `streamTurn` or `watch` stream, at client time `at` (ms). */
  | { type: "event"; event: TurnEvent; at: number }
  /** `getConversation` returned the conversation so far, at client time `at` (ms). */
  | { type: "history_loaded"; events: TurnEvent[]; at: number }
  /** The user pressed Stop. */
  | { type: "stop_requested" }
  /** The stream broke before the turn finished. */
  | { type: "stream_failed"; message: string }
  /** A request other than a turn failed; it is shown, and the turn is left as it was. */
  | { type: "request_failed"; message: string }
  | { type: "models_loaded"; models: ModelInfo[] }
  | { type: "model_selected"; modelId: string };

/**
 * A conversation with nothing in it yet; `modelId` is a preferred model, kept when the loaded
 * models list it.
 */
export function initialChatState(conversationId: string, modelId: string | null = null): ChatState {
  return {
    conversationId,
    modelId,
    models: [],
    phase: "idle",
    turnId: null,
    lastSeq: 0n,
    transcript: [],
    jobs: [],
  };
}

/** The whole client behaviour: the next state after `action`. Pure. */
export function chatReducer(state: ChatState, action: ChatAction): ChatState {
  switch (action.type) {
    case "turn_requested":
      return { ...state, phase: "starting", turnId: null };
    case "event":
      return receiveEvent(state, action.event, action.at);
    case "history_loaded": {
      const replayed = action.events.reduce(
        (next, event) => receiveEvent(next, event, action.at),
        state,
      );
      // A turn still running when the page loaded cannot be followed from here: the page is idle.
      return { ...replayed, phase: "idle", turnId: null };
    }
    case "stop_requested":
      return state.phase === "running" || state.phase === "starting"
        ? { ...state, phase: "stopping" }
        : state;
    case "stream_failed":
      return { ...withItem(state, clientError(state, action.message)), phase: "idle", turnId: null };
    case "request_failed":
      return withItem(state, clientError(state, action.message));
    case "models_loaded": {
      const kept = state.modelId !== null && action.models.some((model) => model.id === state.modelId);
      const fallback = action.models.find((model) => model.isDefault)?.id ?? null;
      return { ...state, models: action.models, modelId: kept ? state.modelId : fallback };
    }
    case "model_selected":
      return { ...state, modelId: action.modelId };
  }
}

/** Whether a turn is in flight, so the composer steers instead of starting one. */
export function isTurnActive(state: ChatState): boolean {
  return state.phase !== "idle";
}

/**
 * Whether the running turn has nothing to show yet: no answer text streaming and no tool step
 * showing its own progress, so the transcript shows a typing indicator.
 */
export function isAwaitingReply(state: ChatState): boolean {
  if (state.phase !== "starting" && state.phase !== "running") return false;
  const last = state.transcript.at(-1);
  if (last?.kind === "assistant" && last.turnId === state.turnId) return false;
  return !(last?.kind === "tool" && last.status === "running");
}

/** Applies one event of a turn, unless its `seq` is one the state already holds. */
function receiveEvent(state: ChatState, event: TurnEvent, at: number): ChatState {
  if (event.seq <= state.lastSeq) return state;
  const next: ChatState = { ...state, lastSeq: event.seq, ...turnPositionAfter(state, event) };
  const body = event.event;
  switch (body.case) {
    case "userMessage":
      return withItem(next, {
        kind: "user",
        id: `user:${event.seq}`,
        turnId: event.turnId,
        text: body.value.text,
      });
    case "textDelta":
      return withText(next, event, body.value);
    case "toolCallStarted":
      return withItem(next, {
        kind: "tool",
        id: `tool:${body.value.callId}`,
        turnId: event.turnId,
        callId: body.value.callId,
        tool: body.value.tool,
        argumentsJson: body.value.argumentsJson,
        policy: policyOf(body.value.execution),
        status: "running",
        startedAt: at,
        finishedAt: null,
        resultJson: null,
        image: null,
        jobId: null,
      });
    case "toolCallFinished":
      return finishTool(next, body.value, at);
    case "jobUpdate": {
      const withJob = { ...next, jobs: upsertJob(next.jobs, body.value, at, null) };
      // A job that ends while no turn runs opens a turn of its own, so its notice goes in the transcript.
      return state.phase === "idle"
        ? withItem(withJob, {
            kind: "job_notice",
            id: `notice:${event.seq}`,
            turnId: event.turnId,
            jobId: body.value.jobId,
            tool: body.value.tool,
            status: jobStateOf(body.value.status),
            detail: body.value.detail,
          })
        : withJob;
    }
    case "steerApplied":
      return withItem(next, {
        kind: "steer",
        id: `steer:${event.seq}`,
        turnId: event.turnId,
        text: body.value.text,
        detachedCallIds: [...body.value.detachedCallIds],
      });
    case "turnFinished":
      return next;
    case "error":
      return withItem(next, {
        kind: "error",
        id: `error:${event.seq}`,
        turnId: event.turnId,
        message: body.value.message,
      });
    default:
      return next;
  }
}

/** The turn phase and id after `event`: an event from idle or starting opens its turn. */
function turnPositionAfter(
  state: ChatState,
  event: TurnEvent,
): Pick<ChatState, "phase" | "turnId"> {
  if (event.event.case === "turnFinished") return { phase: "idle", turnId: null };
  if (state.phase === "idle" || state.phase === "starting") {
    return { phase: "running", turnId: event.turnId };
  }
  return { phase: state.phase, turnId: state.turnId ?? event.turnId };
}

/** Consecutive text deltas of one turn join into one assistant message. */
function withText(state: ChatState, event: TurnEvent, delta: string): ChatState {
  const last = state.transcript.at(-1);
  if (last?.kind === "assistant" && last.turnId === event.turnId) {
    return replaceLast(state, { ...last, text: last.text + delta });
  }
  return withItem(state, {
    kind: "assistant",
    id: `assistant:${event.seq}`,
    turnId: event.turnId,
    text: delta,
  });
}

function finishTool(state: ChatState, finished: ToolCallFinished, at: number): ChatState {
  const jobs = finished.job ? upsertJob(state.jobs, finished.job, at, finished.callId) : state.jobs;
  const image: ToolImage | null =
    finished.image === undefined
      ? null
      : { bytes: finished.image, mediaType: finished.mediaType ?? "application/octet-stream" };
  const transcript = state.transcript.map((item): TranscriptItem => {
    if (item.kind !== "tool" || item.callId !== finished.callId) return item;
    return {
      ...item,
      status: toolStatusOf(finished.status),
      finishedAt: at,
      resultJson: finished.resultJson,
      image: image ?? item.image,
      jobId: finished.job?.jobId ?? item.jobId,
    };
  });
  return { ...state, transcript, jobs };
}

/** Adds the job a handle names, or moves a known job to the handle's state. */
function upsertJob(jobs: JobView[], handle: JobHandle, at: number, callId: string | null): JobView[] {
  const status = jobStateOf(handle.status);
  if (!jobs.some((job) => job.jobId === handle.jobId)) {
    return [
      ...jobs,
      {
        jobId: handle.jobId,
        tool: handle.tool,
        status,
        detail: handle.detail,
        callId,
        startedAt: at,
        updatedAt: at,
      },
    ];
  }
  return jobs.map((job) =>
    job.jobId === handle.jobId ? { ...job, status, detail: handle.detail, updatedAt: at } : job,
  );
}

function policyOf(execution: ExecutionPolicy | undefined): PolicyView | null {
  if (execution === undefined) return null;
  return {
    mode: execution.mode === ExecutionMode.ASYNC ? "ASYNC" : "SYNC",
    timeoutS: execution.timeoutS,
    onTimeout: execution.onTimeout === OnTimeout.FAIL ? "FAIL" : "DETACH",
  };
}

function toolStatusOf(status: ToolCallFinished_Status): ToolStepStatus {
  switch (status) {
    case ToolCallFinished_Status.SUCCEEDED:
      return "succeeded";
    case ToolCallFinished_Status.DETACHED:
      return "detached";
    case ToolCallFinished_Status.CANCELLED:
      return "cancelled";
    default:
      return "failed";
  }
}

function jobStateOf(status: JobStatus): JobState {
  switch (status) {
    case JobStatus.SUCCEEDED:
      return "succeeded";
    case JobStatus.FAILED:
      return "failed";
    case JobStatus.CANCELLED:
      return "cancelled";
    default:
      return "running";
  }
}

function clientError(state: ChatState, message: string): TranscriptItem {
  return { kind: "error", id: `client:${state.transcript.length}`, turnId: null, message };
}

function withItem(state: ChatState, item: TranscriptItem): ChatState {
  return { ...state, transcript: [...state.transcript, item] };
}

function replaceLast(state: ChatState, item: TranscriptItem): ChatState {
  return { ...state, transcript: [...state.transcript.slice(0, -1), item] };
}
