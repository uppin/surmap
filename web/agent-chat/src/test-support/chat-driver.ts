import type { TurnEvent } from "@/gen/surmap/agent/v1/chat_pb";
import {
  chatReducer,
  initialChatState,
  type ChatAction,
  type ChatState,
} from "@/view-model/chat-reducer";
import type { JobView } from "@/view-model/jobs";
import type { ToolItem, TranscriptItem } from "@/view-model/transcript";

/** The client clock when a test's first event arrives, ms. */
export const T0 = 1_700_000_000_000;
/** Client time between consecutive events in a replay, ms. */
export const TICK_MS = 500;

/** The client time the `index`-th replayed event arrives at. */
export function arrivalOf(index: number): number {
  return T0 + index * TICK_MS;
}

/** A fresh conversation `conv-1`, optionally with actions already applied. */
export function aChatState(...actions: ChatAction[]): ChatState {
  return dispatch(initialChatState("conv-1"), ...actions);
}

export function dispatch(state: ChatState, ...actions: ChatAction[]): ChatState {
  return actions.reduce(chatReducer, state);
}

/** Applies `events` as they would arrive on a stream, one `TICK_MS` apart from `T0`. */
export function receive(state: ChatState, events: TurnEvent[]): ChatState {
  return dispatch(
    state,
    ...events.map((event, index): ChatAction => ({ type: "event", event, at: arrivalOf(index) })),
  );
}

export function kindsOf(state: ChatState): TranscriptItem["kind"][] {
  return state.transcript.map((item) => item.kind);
}

export function toolStepOf(state: ChatState, callId: string): ToolItem | undefined {
  return state.transcript.find(
    (item): item is ToolItem => item.kind === "tool" && item.callId === callId,
  );
}

export function jobOf(state: ChatState, jobId: string): JobView | undefined {
  return state.jobs.find((job) => job.jobId === jobId);
}
