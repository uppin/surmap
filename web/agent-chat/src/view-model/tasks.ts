/** Where a job is, as the tasks panel shows it. */
export type JobState = "running" | "succeeded" | "failed" | "cancelled";

/** One job in the tasks panel. Times are client clock milliseconds. */
export interface JobView {
  jobId: string;
  /** The tool the job runs, e.g. `"run_demo"`. */
  tool: string;
  status: JobState;
  /** The server's latest note on the job; empty when it gave none. */
  detail: string;
  /** The tool call the job came from; `null` for a job first seen in a `job_update`. */
  callId: string | null;
  /** When the client first saw the job. */
  startedAt: number;
  /** When the client last saw it change. */
  updatedAt: number;
}

/** One subagent in the tasks panel, as its latest `subagent_status` left it. */
export interface SubagentView {
  /** E.g. `"sa-1"`. */
  subagentId: string;
  /** The label it was started with, e.g. `"scene-builder"`. */
  name: string;
  /** The job its latest turn runs as; cancelling it stops the subagent. */
  jobId: string;
  /** Where its latest turn is. */
  status: JobState;
  /** What it last reported doing; empty until it reports. */
  detail: string;
  /** The `seq` of the status applied; an older one arriving late is ignored. */
  seq: bigint;
  /** When the client first saw its latest turn. */
  startedAt: number;
  /** When the client last saw it change. */
  updatedAt: number;
}

/** Milliseconds a task has run: up to `now` while running, up to its last change once ended. */
export function jobElapsedMs(
  task: Pick<JobView | SubagentView, "status" | "startedAt" | "updatedAt">,
  now: number,
): number {
  const end = task.status === "running" ? now : task.updatedAt;
  return Math.max(0, end - task.startedAt);
}

/** The tool name a subagent's turn runs as; the panel shows the subagent, not that job. */
export function isSubagentTurn(job: JobView): boolean {
  return job.tool.startsWith("subagent:");
}
