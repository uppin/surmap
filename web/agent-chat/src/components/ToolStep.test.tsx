import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { ToolItem, ToolStepStatus } from "@/view-model/transcript";
import { ASYNC_JOB, SYNC_10_THEN_FAIL } from "@/test-support/turn-events";
import { ONE_PIXEL_PNG, SERVER_URL, aToolStep } from "@/test-support/view-items";
import { ToolStep } from "./ToolStep";

function renderStep(overrides: Partial<ToolItem> = {}) {
  const step = aToolStep(overrides);
  render(<ToolStep step={step} serverUrl={SERVER_URL} />);
  const user = userEvent.setup();
  const row = () => screen.getByRole("group", { name: `Tool call ${step.tool}` });
  return {
    row,
    expand: () => user.click(within(row()).getByRole("button", { name: step.tool })),
  };
}

describe("ToolStep", () => {
  it("names the tool and the execution policy the call ran with", () => {
    const step = renderStep({ tool: "run_demo" });

    expect(step.row()).toHaveTextContent(/run_demo.*SYNC 30 s → DETACH/);
  });

  it("labels a policy that fails at its timeout", () => {
    const step = renderStep({ policy: SYNC_10_THEN_FAIL });

    expect(step.row()).toHaveTextContent("SYNC 10 s → FAIL");
  });

  it("labels an ASYNC call by its mode alone", () => {
    const step = renderStep({ policy: ASYNC_JOB });

    expect(step.row()).toHaveTextContent("ASYNC");
  });

  it.each<[ToolStepStatus, string]>([
    ["running", "Running"],
    ["succeeded", "Done"],
    ["failed", "Failed"],
    ["detached", "Detached"],
    ["cancelled", "Cancelled"],
  ])("shows a %s call with the status %s", (status, label) => {
    const step = renderStep({ status });

    expect(within(step.row()).getByRole("status")).toHaveAccessibleName(label);
  });

  it("shows how long a finished call took", () => {
    const step = renderStep({ startedAt: 10_000, finishedAt: 12_400 });

    expect(step.row()).toHaveTextContent("2.4 s");
  });

  it("names the job a detached call became", () => {
    const step = renderStep({ status: "detached", jobId: "job-7" });

    expect(step.row()).toHaveTextContent("job-7");
  });

  it("is collapsed until opened, then shows the arguments and the result", async () => {
    const step = renderStep({
      argumentsJson: '{"dataset":"euroc-v1-01-easy"}',
      resultJson: '{"demos":["euroc-v1-01-easy"]}',
    });

    await step.expand();

    expect(within(step.row()).getByRole("region", { name: "Arguments" })).toHaveTextContent(
      '"dataset": "euroc-v1-01-easy"',
    );
  });

  it("shows the image a frame result carries", () => {
    renderStep({ tool: "get_frame", image: { bytes: ONE_PIXEL_PNG, mediaType: "image/png" } });

    expect(screen.getByRole("img", { name: "get_frame result" })).toBeInTheDocument();
  });

  it("previews the geometry a geometry result points at, resolved against the server", () => {
    renderStep({
      tool: "get_object_geometry",
      resultJson: '{"obj_text":"v 0 0 0","geometry_uri":"/geometry/run-7/obj-3.glb","decimated_from":1}',
    });

    expect(screen.getByRole("figure", { name: "Object geometry preview" })).toHaveAttribute(
      "data-geometry-url",
      "http://127.0.0.1:8780/geometry/run-7/obj-3.glb",
    );
  });
});
