import { useEffect, useRef, type ReactNode } from "react";
import Markdown from "react-markdown";
import type { TranscriptItem } from "@/view-model/transcript";
import { ToolStep } from "./ToolStep";

export interface TranscriptProps {
  items: TranscriptItem[];
  /** The agent server, against which relative `geometry_uri`s resolve. */
  serverUrl: string;
}

/** The conversation: user and assistant messages (Markdown), tool steps, steer markers, job notices, errors. */
export function Transcript(props: TranscriptProps): ReactNode {
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [props.items]);

  return (
    <div
      ref={logRef}
      role="log"
      aria-label="Conversation"
      className="flex max-h-[65vh] min-h-64 flex-col gap-3 overflow-y-auto rounded-xl border p-4"
    >
      {props.items.map((item) => (
        <TranscriptEntry key={item.id} item={item} serverUrl={props.serverUrl} />
      ))}
    </div>
  );
}

function TranscriptEntry({ item, serverUrl }: { item: TranscriptItem; serverUrl: string }): ReactNode {
  switch (item.kind) {
    case "user":
      return (
        <div className="max-w-[85%] self-end whitespace-pre-wrap rounded-xl bg-primary px-3 py-2 text-primary-foreground">
          {item.text}
        </div>
      );
    case "assistant":
      return (
        <div className="max-w-[85%] text-sm leading-relaxed [&_p]:my-1 [&_pre]:overflow-x-auto">
          <Markdown>{item.text}</Markdown>
        </div>
      );
    case "tool":
      return <ToolStep step={item} serverUrl={serverUrl} />;
    case "job_notice":
      return (
        <p className="text-sm text-muted-foreground">
          Job {item.jobId} ({item.tool}) {item.status}
          {item.detail !== "" && `: ${item.detail}`}
        </p>
      );
    case "steer":
      return <p className="text-sm italic text-muted-foreground">Steered: {item.text}</p>;
    case "error":
      return (
        <p role="alert" className="text-sm text-destructive">
          {item.message}
        </p>
      );
  }
}
