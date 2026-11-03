import type { TurnEvent } from "@/gen/surmap/agent/v1/chat_pb";
import type { ModelInfo } from "@/ports";
import type { JobView } from "./jobs";
import type { TranscriptItem } from "./transcript";

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
  | { type: "models_loaded"; models: ModelInfo[] }
  | { type: "model_selected"; modelId: string };

/** A conversation with nothing in it yet. */
export function initialChatState(conversationId: string): ChatState {
  return {
    conversationId,
    modelId: null,
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
  void state;
  void action;
  throw new Error("TODO(pr-9): implement");
}

/** Whether a turn is in flight, so the composer steers instead of starting one. */
export function isTurnActive(state: ChatState): boolean {
  void state;
  throw new Error("TODO(pr-9): implement");
}
