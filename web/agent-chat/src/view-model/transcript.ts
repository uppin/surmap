import type { JobState } from "./jobs";

/** How a tool call stands, as its step shows it. */
export type ToolStepStatus = "running" | "succeeded" | "failed" | "detached" | "cancelled";

/** The execution a tool call ran with: the rpc default merged with the model's override. */
export interface PolicyView {
  mode: "SYNC" | "ASYNC";
  timeoutS: number;
  onTimeout: "FAIL" | "DETACH";
}

/** An image a tool returned, e.g. a frame. */
export interface ToolImage {
  bytes: Uint8Array;
  mediaType: string;
}

export interface UserItem {
  kind: "user";
  id: string;
  turnId: string;
  text: string;
}

/** The agent's answer text; consecutive `text_delta`s of a turn join into one item. */
export interface AssistantItem {
  kind: "assistant";
  id: string;
  turnId: string;
  text: string;
}

/** One tool call, from `tool_call_started` to `tool_call_finished`. Times are client clock ms. */
export interface ToolItem {
  kind: "tool";
  id: string;
  turnId: string;
  callId: string;
  tool: string;
  argumentsJson: string;
  /** `null` when the server sent no policy. */
  policy: PolicyView | null;
  status: ToolStepStatus;
  startedAt: number;
  finishedAt: number | null;
  /** The tool's response or error as JSON; `null` until it finishes. */
  resultJson: string | null;
  image: ToolImage | null;
  /** The job the call became, when it detached or ran ASYNC. */
  jobId: string | null;
}

/** A job-event turn's opening: the job whose end started the turn. */
export interface JobNoticeItem {
  kind: "job_notice";
  id: string;
  turnId: string;
  jobId: string;
  tool: string;
  status: JobState;
  detail: string;
}

/** Guidance the running turn took, and the calls it detached. */
export interface SteerItem {
  kind: "steer";
  id: string;
  turnId: string;
  text: string;
  detachedCallIds: string[];
}

export interface ErrorItem {
  kind: "error";
  id: string;
  /** `null` when the error came from the client (a broken stream), not from a turn. */
  turnId: string | null;
  message: string;
}

export type TranscriptItem =
  | UserItem
  | AssistantItem
  | ToolItem
  | JobNoticeItem
  | SteerItem
  | ErrorItem;

/** The policy as one label, e.g. `"SYNC 30 s → DETACH"` or `"ASYNC"`. */
export function policyLabel(policy: PolicyView): string {
  if (policy.mode === "ASYNC") return "ASYNC";
  return `SYNC ${policy.timeoutS} s → ${policy.onTimeout}`;
}
