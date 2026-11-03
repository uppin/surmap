import type { ReactNode } from "react";
import type { TranscriptItem } from "@/view-model/transcript";

export interface TranscriptProps {
  items: TranscriptItem[];
  /** The agent server, against which relative `geometry_uri`s resolve. */
  serverUrl: string;
}

/** The conversation: user and assistant messages (Markdown), tool steps, steer markers, job notices, errors. */
export function Transcript(props: TranscriptProps): ReactNode {
  void props;
  // TODO(pr-9): implement
  return null;
}
