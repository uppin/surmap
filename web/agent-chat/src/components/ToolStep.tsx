import { useId, useState, type ReactNode } from "react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { policyLabel, type ToolItem, type ToolStepStatus } from "@/view-model/transcript";
import { FrameImage } from "./FrameImage";
import { GeometryPreview } from "./GeometryPreview";

export interface ToolStepProps {
  step: ToolItem;
  /** The agent server, against which a relative `geometry_uri` resolves. */
  serverUrl: string;
}

const STATUS_LABEL: Record<ToolStepStatus, string> = {
  running: "Running",
  succeeded: "Done",
  failed: "Failed",
  detached: "Detached",
  cancelled: "Cancelled",
};

/**
 * One collapsible row per tool call: name, status, execution policy, duration; expanded, the
 * arguments and result. A frame result shows its image; a geometry result shows a 3D preview.
 */
export function ToolStep(props: ToolStepProps): ReactNode {
  const { step } = props;
  const [open, setOpen] = useState(false);
  const detailsId = useId();
  const geometry = geometryUriOf(step.resultJson);
  const geometryUrl = geometry === null ? null : new URL(geometry, props.serverUrl).toString();

  return (
    <div role="group" aria-label={`Tool call ${step.tool}`} className="flex flex-col gap-2 rounded-xl border p-3">
      <div className="flex flex-wrap items-center gap-2 text-sm">
        <Button
          type="button"
          variant="ghost"
          size="sm"
          aria-expanded={open}
          aria-controls={detailsId}
          onClick={() => setOpen((current) => !current)}
        >
          {step.tool}
        </Button>
        {step.policy !== null && <Badge variant="outline">{policyLabel(step.policy)}</Badge>}
        <Badge role="status" aria-label={STATUS_LABEL[step.status]} variant={statusVariant(step.status)}>
          {STATUS_LABEL[step.status]}
        </Badge>
        {step.finishedAt !== null && (
          <span className="text-muted-foreground">{formatSeconds(step.finishedAt - step.startedAt)}</span>
        )}
        {step.jobId !== null && <span className="font-mono text-xs">job {step.jobId}</span>}
      </div>
      {step.image !== null && <FrameImage image={step.image} alt={`${step.tool} result`} />}
      {geometryUrl !== null && <GeometryPreview url={geometryUrl} />}
      {open && (
        <div id={detailsId} className="flex flex-col gap-2 text-xs">
          <section aria-label="Arguments" className="flex flex-col gap-1">
            <h4 className="font-medium">Arguments</h4>
            <pre className="overflow-x-auto rounded-md bg-muted p-2">{prettyJson(step.argumentsJson)}</pre>
          </section>
          <section aria-label="Result" className="flex flex-col gap-1">
            <h4 className="font-medium">Result</h4>
            <pre className="overflow-x-auto rounded-md bg-muted p-2">
              {step.resultJson === null ? "No result yet" : prettyJson(step.resultJson)}
            </pre>
          </section>
        </div>
      )}
    </div>
  );
}

function statusVariant(status: ToolStepStatus): "default" | "secondary" | "destructive" | "outline" {
  switch (status) {
    case "succeeded":
      return "default";
    case "failed":
      return "destructive";
    case "running":
      return "secondary";
    default:
      return "outline";
  }
}

function formatSeconds(ms: number): string {
  return `${(ms / 1000).toFixed(1)} s`;
}

function prettyJson(json: string): string {
  return JSON.stringify(JSON.parse(json), null, 2);
}

/** The `geometry_uri` a geometry result names, or `null` when the result names none. */
function geometryUriOf(resultJson: string | null): string | null {
  if (resultJson === null) return null;
  const result: unknown = JSON.parse(resultJson);
  if (typeof result !== "object" || result === null || !("geometry_uri" in result)) return null;
  return typeof result.geometry_uri === "string" ? result.geometry_uri : null;
}
