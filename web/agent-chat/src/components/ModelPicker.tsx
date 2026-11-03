import type { ReactNode } from "react";
import type { ModelInfo } from "@/ports";

export interface ModelPickerProps {
  models: ModelInfo[];
  /** The chosen model id; `null` before models load. */
  value: string | null;
  onChange(modelId: string): void;
}

/** The server's models from `ListModels`; unavailable ones are shown but cannot be chosen. */
export function ModelPicker(props: ModelPickerProps): ReactNode {
  void props;
  // TODO(pr-9): implement
  return null;
}
