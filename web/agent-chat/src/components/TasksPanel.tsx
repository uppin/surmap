import type { ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  isSubagentTurn,
  jobElapsedMs,
  type JobState,
  type JobView,
  type SubagentView,
} from "@/view-model/tasks";

export interface TasksPanelProps {
  jobs: JobView[];
  subagents: SubagentView[];
  /** Client clock ms, for the elapsed time of running tasks. */
  now: number;
  /** Cancels a job: a job's own, or the one a subagent's turn runs as. */
  onCancel(jobId: string): void;
}

const STATE_LABEL: Record<JobState, string> = {
  running: "Running",
  succeeded: "Succeeded",
  failed: "Failed",
  cancelled: "Cancelled",
};

/**
 * The conversation's tasks: its subagents, with what each last reported doing, and its other
 * jobs, each with status, elapsed time, and Cancel while running. A subagent's turns are jobs too,
 * shown as the subagent rather than again as jobs.
 */
export function TasksPanel(props: TasksPanelProps): ReactNode {
  const jobs = props.jobs.filter((job) => !isSubagentTurn(job));
  return (
    <section aria-label="Tasks" className="flex flex-col gap-3 rounded-xl border p-4">
      <h2 className="text-sm font-semibold">Tasks</h2>
      {props.subagents.length === 0 && jobs.length === 0 ? (
        <p className="text-sm text-muted-foreground">No tasks yet</p>
      ) : (
        <ul className="flex flex-col gap-2">
          {props.subagents.map((subagent) => (
            <TaskRow
              key={`subagent:${subagent.subagentId}`}
              label={`Subagent ${subagent.subagentId}`}
              id={subagent.subagentId}
              title={subagent.name}
              kind="Subagent"
              status={subagent.status}
              elapsedMs={jobElapsedMs(subagent, props.now)}
              detail={subagent.detail}
              onCancel={() => props.onCancel(subagent.jobId)}
            />
          ))}
          {jobs.map((job) => (
            <TaskRow
              key={job.jobId}
              label={`Job ${job.jobId}`}
              id={job.jobId}
              title={job.tool}
              status={job.status}
              elapsedMs={jobElapsedMs(job, props.now)}
              detail={job.detail}
              onCancel={() => props.onCancel(job.jobId)}
            />
          ))}
        </ul>
      )}
    </section>
  );
}

interface TaskRowProps {
  label: string;
  id: string;
  title: string;
  /** A tag beside the title, e.g. `"Subagent"`; none for a plain job. */
  kind?: string;
  status: JobState;
  elapsedMs: number;
  detail: string;
  onCancel(): void;
}

function TaskRow(props: TaskRowProps): ReactNode {
  return (
    <li aria-label={props.label} className="flex flex-col gap-1 rounded-md border p-3 text-sm">
      <div className="flex flex-wrap items-center gap-2">
        <span className="font-mono text-xs">{props.id}</span>
        <span className="font-medium">{props.title}</span>
        {props.kind !== undefined && <Badge variant="outline">{props.kind}</Badge>}
        <Badge variant={props.status === "failed" ? "destructive" : "secondary"}>
          {STATE_LABEL[props.status]}
        </Badge>
      </div>
      <span className="text-xs text-muted-foreground">{formatElapsed(props.elapsedMs)}</span>
      {props.detail !== "" && <p className="text-muted-foreground">{props.detail}</p>}
      {props.status === "running" && (
        <Button type="button" variant="outline" size="sm" className="self-start" onClick={props.onCancel}>
          Cancel
        </Button>
      )}
    </li>
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
