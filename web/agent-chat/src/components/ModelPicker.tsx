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
  return (
    <div className="flex items-center gap-2 text-sm">
      <span className="text-muted-foreground">Model</span>
      <select
        aria-label="Model"
        className="h-9 rounded-md border border-input bg-transparent px-2 shadow-xs outline-none focus-visible:ring-[3px] focus-visible:ring-ring/50"
        value={props.value ?? ""}
        onChange={(event) => props.onChange(event.target.value)}
      >
        {props.models.map((model) => (
          <option key={model.id} value={model.id} disabled={!model.available}>
            {optionLabel(model)}
          </option>
        ))}
      </select>
    </div>
  );
}

function optionLabel(model: ModelInfo): string {
  const name = `${model.provider} · ${model.displayName}`;
  if (model.available) return name;
  return `${name} (${model.detail || "unavailable"})`;
}
