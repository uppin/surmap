import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import type { JobView, SubagentView } from "@/view-model/tasks";
import { T0 } from "@/test-support/chat-driver";
import { aJob, aSubagent } from "@/test-support/view-items";
import { TasksPanel } from "./TasksPanel";

function renderPanel(
  tasks: { jobs?: JobView[]; subagents?: SubagentView[] },
  now = T0 + 65_000,
) {
  const cancelled: string[] = [];
  render(
    <TasksPanel
      jobs={tasks.jobs ?? []}
      subagents={tasks.subagents ?? []}
      now={now}
      onCancel={(jobId) => cancelled.push(jobId)}
    />,
  );
  const user = userEvent.setup();
  const jobRow = (jobId: string) => screen.getByRole("listitem", { name: `Job ${jobId}` });
  const subagentRow = (subagentId: string) =>
    screen.getByRole("listitem", { name: `Subagent ${subagentId}` });
  return {
    cancelled,
    jobRow,
    subagentRow,
    cancel: (row: HTMLElement) => user.click(within(row).getByRole("button", { name: "Cancel" })),
  };
}

describe("TasksPanel", () => {
  it("lists a running job with its tool, status and elapsed time", () => {
    const panel = renderPanel({ jobs: [aJob({ jobId: "job-7", tool: "run_demo", startedAt: T0 })] }, T0 + 65_000);

    expect(panel.jobRow("job-7")).toHaveTextContent(/run_demo.*Running.*1:05/);
  });

  it("stops the clock of a finished job at its last change", () => {
    const panel = renderPanel(
      { jobs: [aJob({ jobId: "job-7", status: "succeeded", startedAt: T0, updatedAt: T0 + 42_000 })] },
      T0 + 600_000,
    );

    expect(panel.jobRow("job-7")).toHaveTextContent(/Succeeded.*0:42/);
  });

  it("cancels a running job when its Cancel is pressed", async () => {
    const panel = renderPanel({ jobs: [aJob({ jobId: "job-7" }), aJob({ jobId: "job-8" })] });

    await panel.cancel(panel.jobRow("job-8"));

    expect(panel.cancelled).toEqual(["job-8"]);
  });

  it("offers no Cancel on a job that has ended", () => {
    const panel = renderPanel({ jobs: [aJob({ jobId: "job-7", status: "failed", detail: "SAM unreachable" })] });

    expect(within(panel.jobRow("job-7")).queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("shows the server's note on a job", () => {
    const panel = renderPanel({ jobs: [aJob({ jobId: "job-7", status: "failed", detail: "SAM unreachable" })] });

    expect(panel.jobRow("job-7")).toHaveTextContent("SAM unreachable");
  });

  it("lists a running subagent with its name, status, elapsed time and what it reported", () => {
    const panel = renderPanel(
      { subagents: [aSubagent({ subagentId: "sa-1", name: "scene-builder", detail: "Placing the house" })] },
      T0 + 65_000,
    );

    expect(panel.subagentRow("sa-1")).toHaveTextContent(/scene-builder.*Subagent.*Running.*1:05.*Placing the house/);
  });

  it("cancels a running subagent's job when its Cancel is pressed", async () => {
    const panel = renderPanel({ subagents: [aSubagent({ subagentId: "sa-1", jobId: "job-4" })] });

    await panel.cancel(panel.subagentRow("sa-1"));

    expect(panel.cancelled).toEqual(["job-4"]);
  });

  it("offers no Cancel on a subagent that has finished", () => {
    const panel = renderPanel({ subagents: [aSubagent({ subagentId: "sa-1", status: "succeeded" })] });

    expect(within(panel.subagentRow("sa-1")).queryByRole("button", { name: "Cancel" })).not.toBeInTheDocument();
  });

  it("does not list a subagent's turn again as a job", () => {
    renderPanel({
      subagents: [aSubagent({ subagentId: "sa-1", jobId: "job-4" })],
      jobs: [aJob({ jobId: "job-4", tool: "subagent:sa-1", status: "succeeded" })],
    });

    expect(screen.queryByRole("listitem", { name: "Job job-4" })).not.toBeInTheDocument();
  });

  it("says so when there are no tasks yet", () => {
    renderPanel({});

    expect(screen.getByRole("region", { name: "Tasks" })).toHaveTextContent("No tasks yet");
  });
});
