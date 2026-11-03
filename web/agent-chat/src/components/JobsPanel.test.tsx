import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { JobView } from "@/view-model/jobs";
import { T0 } from "@/test-support/chat-driver";
import { aJob } from "@/test-support/view-items";
import { JobsPanel } from "./JobsPanel";

function renderPanel(jobs: JobView[], now = T0 + 65_000) {
  const cancelled: string[] = [];
  render(<JobsPanel jobs={jobs} now={now} onCancel={(jobId) => cancelled.push(jobId)} />);
  const user = userEvent.setup();
  const jobRow = (jobId: string) => screen.getByRole("listitem", { name: `Job ${jobId}` });
  return {
    cancelled,
    jobRow,
    cancel: (jobId: string) => user.click(within(jobRow(jobId)).getByRole("button", { name: "Cancel" })),
  };
}

describe("JobsPanel", () => {
  it("lists a running job with its tool, status and elapsed time", () => {
    const panel = renderPanel([aJob({ jobId: "job-7", tool: "run_demo", startedAt: T0 })], T0 + 65_000);

    expect(panel.jobRow("job-7")).toHaveTextContent(/run_demo.*Running.*1:05/);
  });

  it("stops the clock of a finished job at its last change", () => {
    const panel = renderPanel(
      [aJob({ jobId: "job-7", status: "succeeded", startedAt: T0, updatedAt: T0 + 42_000 })],
      T0 + 600_000,
    );

    expect(panel.jobRow("job-7")).toHaveTextContent(/Succeeded.*0:42/);
  });

  it("cancels a running job when its Cancel is pressed", async () => {
    const panel = renderPanel([aJob({ jobId: "job-7" }), aJob({ jobId: "job-8" })]);

    await panel.cancel("job-8");

    expect(panel.cancelled).toEqual(["job-8"]);
  });

  it("offers no Cancel on a job that has ended", () => {
    const panel = renderPanel([aJob({ jobId: "job-7", status: "failed", detail: "SAM unreachable" })]);

    expect(within(panel.jobRow("job-7")).queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("shows the server's note on a job", () => {
    const panel = renderPanel([aJob({ jobId: "job-7", status: "failed", detail: "SAM unreachable" })]);

    expect(panel.jobRow("job-7")).toHaveTextContent("SAM unreachable");
  });

  it("says so when there are no jobs yet", () => {
    renderPanel([]);

    expect(screen.getByRole("region", { name: "Jobs" })).toHaveTextContent("No jobs yet");
  });
});
