import type { ReactNode } from "react";

export interface GeometryPreviewProps {
  /** Absolute URL of the object's GLB. */
  url: string;
}

/** A three.js view of an object's GLB (`GLTFLoader`), loaded lazily so the chat bundle stays small. */
export function GeometryPreview(props: GeometryPreviewProps): ReactNode {
  void props;
  // TODO(pr-9): implement
  return null;
}
