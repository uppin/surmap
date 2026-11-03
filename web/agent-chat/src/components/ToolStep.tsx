import type { ReactNode } from "react";
import type { ToolItem } from "@/view-model/transcript";

export interface ToolStepProps {
  step: ToolItem;
  /** The agent server, against which a relative `geometry_uri` resolves. */
  serverUrl: string;
}

/**
 * One collapsible row per tool call: name, status, execution policy, duration; expanded, the
 * arguments and result. A frame result shows its image; a geometry result shows a 3D preview.
 */
export function ToolStep(props: ToolStepProps): ReactNode {
  void props;
  // TODO(pr-9): implement
  return null;
}
