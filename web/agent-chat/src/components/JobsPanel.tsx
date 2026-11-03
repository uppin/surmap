import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { jobElapsedMs, type JobState, type JobView } from "@/view-model/jobs";

export interface JobsPanelProps {
  jobs: JobView[];
  /** Client clock ms, for the elapsed time of running jobs. */
  now: number;
  onCancel(jobId: string): void;
}

const STATE_LABEL: Record<JobState, string> = {
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

/** Running and finished jobs with tool, status, elapsed time, and Cancel on running ones. */
export function JobsPanel(props: JobsPanelProps): ReactNode {
  return (
    <section aria-label="Jobs" className="flex flex-col gap-3 rounded-xl border p-4">
      <h2 className="text-sm font-semibold">Jobs</h2>
      {props.jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No jobs yet</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {props.jobs.map((job) => (
            <li
              key={job.jobId}
              aria-label={`Job ${job.jobId}`}
              className="flex flex-col gap-1 rounded-md border p-3 text-sm"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-mono text-xs">{job.jobId}</span>
                <span className="font-medium">{job.tool}</span>
                <Badge variant={job.status === "failed" ? "destructive" : "secondary"}>
                  {STATE_LABEL[job.status]}
                </Badge>
              </div>
              <span className="text-xs text-muted-foreground">
                {formatElapsed(jobElapsedMs(job, props.now))}
              </span>
              {job.detail !== "" && <p className="text-muted-foreground">{job.detail}</p>}
              {job.status === "running" && (
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  className="self-start"
                  onClick={() => props.onCancel(job.jobId)}
                >
                  Cancel
                </Button>
              )}
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** `m:ss`, or `h:mm:ss` from an hour on. */
function formatElapsed(ms: number): string {
  const total = Math.floor(ms / 1000);
  const hours = Math.floor(total / 3600);
  const minutes = Math.floor((total % 3600) / 60);
  const seconds = String(total % 60).padStart(2, "0");
  if (hours > 0) return `${hours}:${String(minutes).padStart(2, "0")}:${seconds}`;
  return `${minutes}:${seconds}`;
}
