import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { StationView } from "@/ports";
import { aStation } from "@/test-support/view-items";
import { StationIndicator } from "./StationIndicator";

function renderIndicator(status: StationView | null) {
  const asked: string[] = [];
  render(
    <StationIndicator status={status} onStart={() => asked.push("start")} onStop={() => asked.push("stop")} />,
  );
  return { asked, user: userEvent.setup(), indicator: () => screen.queryByRole("status", { name: "SAM station" }) };
}

describe("StationIndicator", () => {
  it("shows nothing when the agent has no SAM station", () => {
    const view = renderIndicator(null);

    expect(view.indicator()).toBeNull();
  });

  it("shows which state the SAM station is in", () => {
    const view = renderIndicator(aStation({ state: "ready", containers: 1 }));

    expect(view.indicator()).toHaveTextContent("SAM · ready");
  });

  it("offers to start a station that is off, and reports the click", async () => {
    const view = renderIndicator(aStation({ state: "off" }));

    await view.user.click(screen.getByRole("button", { name: "Start SAM" }));

    expect(view.asked).toEqual(["start"]);
  });

  it("offers to stop a station that is up, and reports the click", async () => {
    const view = renderIndicator(aStation({ state: "ready", containers: 1 }));

    await view.user.click(screen.getByRole("button", { name: "Stop SAM" }));

    expect(view.asked).toEqual(["stop"]);
  });

  it("offers to stop a station still waiting for a GPU, and says why it waits", () => {
    renderIndicator(aStation({ state: "queued", detail: "waiting for a GPU" }));

    expect(screen.getByRole("button", { name: "Stop SAM" })).toBeEnabled();
    expect(screen.getByRole("status", { name: "SAM station" })).toHaveAttribute("title", "waiting for a GPU");
  });

  it("lets nothing be clicked while the station is stopping", () => {
    renderIndicator(aStation({ state: "stopping", containers: 1 }));

    expect(screen.getByRole("button", { name: "Stop SAM" })).toBeDisabled();
  });

  it("shows an error with its cause and offers to start again", () => {
    renderIndicator(aStation({ state: "error", detail: "station did not pass its health check" }));

    expect(screen.getByRole("status", { name: "SAM station" })).toHaveTextContent("SAM · error");
    expect(screen.getByRole("status", { name: "SAM station" })).toHaveAttribute(
      "title",
      "station did not pass its health check",
    );
    expect(screen.getByRole("button", { name: "Start SAM" })).toBeEnabled();
  });

  it("says how long a ready station has been idle against its timeout", () => {
    renderIndicator(aStation({ state: "ready", containers: 1, idleForS: 90, idleTimeoutS: 300 }));

    expect(screen.getByRole("status", { name: "SAM station" })).toHaveAttribute("title", "idle 1:30 of 5:00");
  });
});
