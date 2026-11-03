/** Where a job is, as the jobs panel shows it. */
export type JobState = "running" | "succeeded" | "failed" | "cancelled";

/** One job in the jobs panel. Times are client clock milliseconds. */
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

/** Milliseconds the job has run: up to `now` while running, up to its last change once ended. */
export function jobElapsedMs(job: JobView, now: number): number {
  void job;
  void now;
  throw new Error("TODO(pr-9): implement");
}
