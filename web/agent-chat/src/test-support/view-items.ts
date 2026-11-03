import type { ModelInfo } from "@/ports";
import type { JobView } from "@/view-model/jobs";
import type { ToolItem } from "@/view-model/transcript";
import { SYNC_30_THEN_DETACH } from "./turn-events";
import { T0 } from "./chat-driver";

/** The agent server address component tests render against. */
export const SERVER_URL = "http://127.0.0.1:8780";

/** A finished `list_demos` call that ran 2 s under the usual SYNC 30 s → DETACH policy. */
export function aToolStep(overrides: Partial<ToolItem> = {}): ToolItem {
  return {
    kind: "tool",
    id: "tool:call-1",
    turnId: "turn-1",
    callId: "call-1",
    tool: "list_demos",
    argumentsJson: '{"dataset":"euroc-v1-01-easy"}',
    policy: SYNC_30_THEN_DETACH,
    status: "succeeded",
    startedAt: T0,
    finishedAt: T0 + 2_000,
    resultJson: '{"demos":["euroc-v1-01-easy"]}',
    image: null,
    jobId: null,
    ...overrides,
  };
}

/** A `run_demo` job started at `T0`, still running. */
export function aJob(overrides: Partial<JobView> = {}): JobView {
  return {
    jobId: "job-7",
    tool: "run_demo",
    status: "running",
    detail: "",
    callId: "call-1",
    startedAt: T0,
    updatedAt: T0,
    ...overrides,
  };
}

export function aModel(overrides: Partial<ModelInfo> = {}): ModelInfo {
  return {
    id: "meta:muse-spark",
    provider: "muse",
    displayName: "Muse Spark",
    available: true,
    detail: "",
    isDefault: false,
    ...overrides,
  };
}

/** A 1×1 PNG, the smallest image a frame result can carry. */
export const ONE_PIXEL_PNG = Uint8Array.from(
  atob(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mNk+M9QDwADhgGAWjR9awAAAABJRU5ErkJggg==",
  ),
  (char) => char.charCodeAt(0),
);
