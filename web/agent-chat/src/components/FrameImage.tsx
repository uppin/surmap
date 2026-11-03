import { useMemo, type ReactNode } from "react";
import type { ToolImage } from "@/view-model/transcript";

export interface FrameImageProps {
  image: ToolImage;
  alt: string;
}

/** An image a tool returned, inline in its step. */
export function FrameImage(props: FrameImageProps): ReactNode {
  const src = useMemo(() => dataUrlOf(props.image), [props.image]);
  return <img src={src} alt={props.alt} className="max-h-72 w-auto self-start rounded-md border" />;
}

/** The image as a `data:` URL, so it needs no object URL to be revoked. */
function dataUrlOf(image: ToolImage): string {
  let binary = "";
  for (const byte of image.bytes) binary += String.fromCharCode(byte);
  return `data:${image.mediaType};base64,${btoa(binary)}`;
}
