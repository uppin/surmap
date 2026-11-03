import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import type { TranscriptItem } from "@/view-model/transcript";
import { SERVER_URL, aToolStep } from "@/test-support/view-items";
import { Transcript } from "./Transcript";

function renderTranscript(items: TranscriptItem[], { awaitingReply = false } = {}) {
  render(<Transcript items={items} serverUrl={SERVER_URL} awaitingReply={awaitingReply} />);
  return { log: () => screen.getByRole("log", { name: "Conversation" }) };
}

describe("Transcript", () => {
  it("shows the user's message and the agent's reply in order", () => {
    const transcript = renderTranscript([
      { kind: "user", id: "u1", turnId: "turn-1", text: "What demos are there?" },
      { kind: "assistant", id: "a1", turnId: "turn-1", text: "Three demos are ready." },
    ]);

    expect(transcript.log()).toHaveTextContent(/What demos are there\?.*Three demos are ready\./);
  });

  it("renders the agent's reply as Markdown", () => {
    const transcript = renderTranscript([
      { kind: "assistant", id: "a1", turnId: "turn-1", text: "The **box** is 1.2 m tall." },
    ]);

    expect(within(transcript.log()).getByText("box").tagName).toBe("STRONG");
  });

  it("shows each tool call as its own step", () => {
    renderTranscript([aToolStep({ tool: "run_demo" })]);

    expect(screen.getByRole("group", { name: "Tool call run_demo" })).toBeInTheDocument();
  });

  it("marks where the turn took steering guidance", () => {
    const transcript = renderTranscript([
      { kind: "steer", id: "s1", turnId: "turn-1", text: "Use the KITTI scene", detachedCallIds: ["call-1"] },
    ]);

    expect(transcript.log()).toHaveTextContent("Steered: Use the KITTI scene");
  });

  it("opens a job-event turn with a notice for the job that ended", () => {
    const transcript = renderTranscript([
      {
        kind: "job_notice",
        id: "n1",
        turnId: "turn-2",
        jobId: "job-7",
        tool: "run_demo",
        status: "succeeded",
        detail: "run run-7 ended",
      },
    ]);

    expect(transcript.log()).toHaveTextContent("Job job-7 (run_demo) succeeded");
  });

  it("shows a typing indicator after the conversation while awaiting the agent's reply", () => {
    const transcript = renderTranscript(
      [{ kind: "user", id: "u1", turnId: "turn-1", text: "What demos are there?" }],
      { awaitingReply: true },
    );

    expect(within(transcript.log()).getByRole("status", { name: "Agent is thinking" })).toBeInTheDocument();
  });

  it("shows no typing indicator when no reply is awaited", () => {
    renderTranscript([{ kind: "assistant", id: "a1", turnId: "turn-1", text: "Three demos are ready." }]);

    expect(screen.queryByRole("status", { name: "Agent is thinking" })).not.toBeInTheDocument();
  });

  it("shows an error as an alert", () => {
    renderTranscript([{ kind: "error", id: "e1", turnId: "turn-1", message: "Muse is unreachable" }]);

    expect(screen.getByRole("alert")).toHaveTextContent("Muse is unreachable");
  });
});
