import type { ReactNode } from "react";
import type { StationView } from "@/ports";

export interface StationIndicatorProps {
  /** The station's status; `null` when the agent runs without one, which shows nothing. */
  status: StationView | null;
  onStart(): void;
  onStop(): void;
}

const DOT: Record<StationView["state"], string> = {
  off: "bg-muted-foreground/40",
  queued: "bg-amber-500",
  starting: "bg-amber-500",
  ready: "bg-emerald-500",
  stopping: "bg-amber-500",
  error: "bg-destructive",
};

/** The SAM station in the header: its state, and Start or Stop for its GPU. */
export function StationIndicator(props: StationIndicatorProps): ReactNode {
  const { status } = props;
  if (status === null) return null;
  const canStart = status.state === "off" || status.state === "error";
  return (
    <div className="flex items-center gap-2 text-sm">
      <span
        role="status"
        aria-label="SAM station"
        title={hint(status)}
        className="flex items-center gap-1.5 rounded-md border px-2 py-1"
      >
        <span aria-hidden className={`size-2 rounded-full ${DOT[status.state]}`} />
        {`SAM · ${status.state}`}
      </span>
      {canStart ? (
        <button type="button" className="rounded-md border px-2 py-1" onClick={props.onStart}>
          Start SAM
        </button>
      ) : (
        <button
          type="button"
          className="rounded-md border px-2 py-1 disabled:opacity-50"
          disabled={status.state === "stopping"}
          onClick={props.onStop}
        >
          Stop SAM
        </button>
      )}
    </div>
  );
}

function hint(status: StationView): string {
  if (status.detail) return status.detail;
  if (status.state === "ready") return `idle ${clock(status.idleForS)} of ${clock(status.idleTimeoutS)}`;
  return status.backend;
}

function clock(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  return `${Math.floor(whole / 60)}:${String(whole % 60).padStart(2, "0")}`;
}
