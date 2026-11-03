import type { ReactNode } from "react";
import type { JobView } from "@/view-model/jobs";

export interface JobsPanelProps {
  jobs: JobView[];
  /** Client clock ms, for the elapsed time of running jobs. */
  now: number;
  onCancel(jobId: string): void;
}

/** Running and finished jobs with tool, status, elapsed time, and Cancel on running ones. */
export function JobsPanel(props: JobsPanelProps): ReactNode {
  void props;
  // TODO(pr-9): implement
  return null;
}
