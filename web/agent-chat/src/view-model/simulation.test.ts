import { describe, expect, it } from "vitest";
import { aToolStep } from "@/test-support/view-items";
import type { TranscriptItem } from "./transcript";
import { simulationFromTranscript } from "./simulation";

const CREATE_RESULT = JSON.stringify({
  scenario: {
    id: "downtown-blaze",
    name: "Downtown blaze",
    version: 1,
    manifest_json: "{}",
    credits: [],
    url: "/sim/?scenario=downtown-blaze",
    updated_at: "2026-11-04T10:00:00Z",
  },
});

function editResult(version: number, id = "downtown-blaze", name = "Downtown blaze"): string {
  return JSON.stringify({
    scenario: {
      id,
      name,
      version,
      manifest_json: "{}",
      credits: ["Glass tower by A. Modeller (CC BY 4.0)"],
      url: `/sim/?scenario=${id}`,
      updated_at: "2026-11-04T10:05:00Z",
    },
  });
}

function assistant(text: string): TranscriptItem {
  return { kind: "assistant", id: `assistant:${text.length}`, turnId: "turn-1", text };
}

describe("simulationFromTranscript", () => {
  it("finds no simulation in an empty conversation", () => {
    expect(simulationFromTranscript([])).toBeNull();
  });

  it("finds no simulation when the agent only ran other tools", () => {
    const items = [aToolStep({ tool: "list_demos" })];

    expect(simulationFromTranscript(items)).toBeNull();
  });

  it("shows the scenario a succeeded create_scenario made", () => {
    const items = [
      aToolStep({ tool: "create_scenario", status: "succeeded", resultJson: CREATE_RESULT }),
    ];

    expect(simulationFromTranscript(items)).toEqual({
      id: "downtown-blaze",
      name: "Downtown blaze",
      version: 1,
      url: "/sim/?scenario=downtown-blaze",
      credits: [],
    });
  });

  it("ignores a create_scenario that is still running", () => {
    const items = [aToolStep({ tool: "create_scenario", status: "running", resultJson: null })];

    expect(simulationFromTranscript(items)).toBeNull();
  });

  it("ignores a create_scenario that failed", () => {
    const items = [
      aToolStep({
        tool: "create_scenario",
        status: "failed",
        resultJson: '{"error":"unknown preset"}',
      }),
    ];

    expect(simulationFromTranscript(items)).toBeNull();
  });

  it("ignores a create_scenario whose result is not JSON", () => {
    const items = [aToolStep({ tool: "create_scenario", status: "succeeded", resultJson: "not json" })];

    expect(simulationFromTranscript(items)).toBeNull();
  });

  it("shows the newest scenario when the agent created two", () => {
    const items = [
      aToolStep({ callId: "call-1", tool: "create_scenario", resultJson: CREATE_RESULT }),
      aToolStep({
        callId: "call-2",
        tool: "create_scenario",
        resultJson: editResult(1, "flood-street", "Flood street"),
      }),
    ];

    expect(simulationFromTranscript(items)?.id).toBe("flood-street");
  });

  it("bumps the version when a later edit returns the created scenario", () => {
    const items = [
      aToolStep({ callId: "call-1", tool: "create_scenario", resultJson: CREATE_RESULT }),
      aToolStep({ callId: "call-2", tool: "add_element", resultJson: editResult(4) }),
    ];

    expect(simulationFromTranscript(items)).toEqual({
      id: "downtown-blaze",
      name: "Downtown blaze",
      version: 4,
      url: "/sim/?scenario=downtown-blaze",
      credits: ["Glass tower by A. Modeller (CC BY 4.0)"],
    });
  });

  it("keeps the created scenario when a later edit names another one", () => {
    const items = [
      aToolStep({ callId: "call-1", tool: "create_scenario", resultJson: CREATE_RESULT }),
      aToolStep({
        callId: "call-2",
        tool: "add_element",
        resultJson: editResult(9, "old-scene", "Old scene"),
      }),
    ];

    expect(simulationFromTranscript(items)?.id).toBe("downtown-blaze");
    expect(simulationFromTranscript(items)?.version).toBe(1);
  });

  it("shows the scene the agent reports by URL when a subagent built it", () => {
    const items = [
      assistant("Built downtown-blaze at version 3 — open it at /sim/?scenario=downtown-blaze"),
    ];

    expect(simulationFromTranscript(items)).toEqual({
      id: "downtown-blaze",
      name: "downtown-blaze",
      version: null,
      url: "/sim/?scenario=downtown-blaze",
      credits: [],
    });
  });

  it("prefers the created scenario over a URL the agent mentioned earlier", () => {
    const items = [
      assistant("The old scene is at /sim/?scenario=old-scene"),
      aToolStep({ tool: "create_scenario", resultJson: CREATE_RESULT }),
    ];

    expect(simulationFromTranscript(items)?.id).toBe("downtown-blaze");
  });
});
