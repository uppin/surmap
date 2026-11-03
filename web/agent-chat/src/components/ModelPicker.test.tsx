import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ModelInfo } from "@/ports";
import { aModel } from "@/test-support/view-items";
import { ModelPicker } from "./ModelPicker";

const MUSE = aModel({ id: "meta:muse-spark", displayName: "Muse Spark", isDefault: true });
const QWEN = aModel({ id: "ollama:qwen3", provider: "ollama", displayName: "Qwen 3" });
const OFFLINE = aModel({
  id: "ollama:llama4",
  provider: "ollama",
  displayName: "Llama 4",
  available: false,
  detail: "Ollama is not running",
});

function renderPicker(models: ModelInfo[], value: string | null) {
  const chosen: string[] = [];
  render(<ModelPicker models={models} value={value} onChange={(id) => chosen.push(id)} />);
  const user = userEvent.setup();
  const picker = () => screen.getByRole("combobox", { name: "Model" });
  return { chosen, picker, choose: (label: string) => user.selectOptions(picker(), label) };
}

describe("ModelPicker", () => {
  it("lists every model the server offers, by provider and name", () => {
    renderPicker([MUSE, QWEN], MUSE.id);

    expect(screen.getAllByRole("option").map((option) => option.textContent)).toEqual([
      "muse · Muse Spark",
      "ollama · Qwen 3",
    ]);
  });

  it("shows the chosen model as selected", () => {
    const picker = renderPicker([MUSE, QWEN], QWEN.id);

    expect(picker.picker()).toHaveValue("ollama:qwen3");
  });

  it("reports the model the user picks", async () => {
    const picker = renderPicker([MUSE, QWEN], MUSE.id);

    await picker.choose("ollama · Qwen 3");

    expect(picker.chosen).toEqual(["ollama:qwen3"]);
  });

  it("shows an unreachable model, with why, but does not let it be picked", () => {
    renderPicker([MUSE, OFFLINE], MUSE.id);

    expect(screen.getByRole("option", { name: /Llama 4/ })).toBeDisabled();
  });
});
