import type { TurnEvent } from "@/gen/surmap/agent/v1/chat_pb";

/** What a turn is started with. */
export interface StreamTurnInput {
  /** The conversation to continue; the server starts it when it does not exist. */
  conversationId: string;
  /** A `ChatModel` id; `null` lets the server use its default model. */
  modelId: string | null;
  /** The user's message. */
  text: string;
}

/** How the server took a steer. */
export interface SteerOutcome {
  /** `false` when no turn was running to take the guidance; the client starts a turn instead. */
  accepted: boolean;
}

/** A model a conversation can run on, as the picker shows it. */
export interface ModelInfo {
  id: string;
  /** Who serves it, e.g. `"muse"` or `"ollama"`. */
  provider: string;
  displayName: string;
  /** Whether the server can reach it now. */
  available: boolean;
  /** Why it cannot be reached; empty when it can. */
  detail: string;
  /** Whether a turn uses it when no model is named. */
  isDefault: boolean;
}

/**
 * Everything the chat UI asks of the agent server. Components and the view model never reach the
 * network except through this port; the Connect adapter implements it and tests fake it.
 */
export interface ChatPort {
  /** Sends the user's message and streams the turn it starts, until the turn finishes. */
  streamTurn(input: StreamTurnInput, signal: AbortSignal): AsyncIterable<TurnEvent>;
  /** Streams turns that start while no `streamTurn` is open (job-event turns). */
  watch(conversationId: string, signal: AbortSignal): AsyncIterable<TurnEvent>;
  /** Adds guidance to the running turn. */
  steer(conversationId: string, text: string): Promise<SteerOutcome>;
  /** Cancels the running turn and its blocking tool calls. */
  cancelTurn(conversationId: string): Promise<void>;
  /** Cancels one of the conversation's jobs. */
  cancelJob(conversationId: string, jobId: string): Promise<void>;
  /** The models the server is configured with, the default one marked. */
  listModels(): Promise<ModelInfo[]>;
  /** Every event of the conversation so far, in order, for redrawing it after a reload. */
  getConversation(conversationId: string): Promise<TurnEvent[]>;
}
