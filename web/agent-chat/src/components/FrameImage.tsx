import type { ReactNode } from "react";
import type { ToolImage } from "@/view-model/transcript";

export interface FrameImageProps {
  image: ToolImage;
  alt: string;
}

/** An image a tool returned, inline in its step. */
export function FrameImage(props: FrameImageProps): ReactNode {
  void props;
  // TODO(pr-9): implement
  return null;
}
