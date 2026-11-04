import { useEffect, useRef, type ReactNode } from "react";
import { Bot } from "lucide-react";
import Markdown from "react-markdown";
import type { TranscriptItem } from "@/view-model/transcript";
import { ToolStep } from "./ToolStep";

export interface TranscriptProps {
  items: TranscriptItem[];
  /** The agent server, against which relative `geometry_uri`s resolve. */
  serverUrl: string;
  /** The running turn has nothing to show yet; a typing indicator follows the last item. */
  awaitingReply?: boolean;
}

/**
 * The conversation: user and assistant messages (Markdown), tool steps, steer markers, job notices,
 * subagent messages, errors, and a typing indicator while the agent's reply is awaited.
 */
export function Transcript(props: TranscriptProps): ReactNode {
  const logRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const log = logRef.current;
    if (log) log.scrollTop = log.scrollHeight;
  }, [props.items, props.awaitingReply]);

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
      {props.awaitingReply === true && <TypingIndicator />}
    </div>
  );
}

/** Three dots pulsing in turn. */
function TypingIndicator(): ReactNode {
  return (
    <div role="status" aria-label="Agent is thinking" className="flex items-center gap-1 py-2">
      {["0ms", "150ms", "300ms"].map((delay) => (
        <span
          key={delay}
          aria-hidden="true"
          className="size-2 animate-bounce rounded-full bg-muted-foreground/60"
          style={{ animationDelay: delay }}
        />
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
    case "subagent_message":
      return (
        <div
          role="note"
          aria-label={`Message from subagent ${item.subagentId}`}
          className="max-w-[85%] rounded-lg border border-dashed bg-muted/40 px-3 py-2 text-sm"
        >
          <p className="mb-1 flex items-center gap-1.5 text-xs font-medium text-muted-foreground">
            <Bot aria-hidden="true" className="size-3.5" />
            Subagent {item.subagentId} · {item.name}
          </p>
          <div className="leading-relaxed [&_p]:my-1">
            <Markdown>{item.text}</Markdown>
          </div>
        </div>
      );
    case "error":
      return (
        <p role="alert" className="text-sm text-destructive">
          {item.message}
        </p>
      );
  }
}
