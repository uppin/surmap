import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { SERVER_URL } from "@/test-support/view-items";
import type { SimulationView } from "@/view-model/simulation";
import { SimulationPane } from "./SimulationPane";

const SIMULATION: SimulationView = {
  id: "downtown-blaze",
  name: "Downtown blaze",
  version: 3,
  url: "/sim/?scenario=downtown-blaze",
  credits: ["Glass tower by A. Modeller (CC BY 4.0)"],
};

describe("SimulationPane", () => {
  it("embeds the scenario's live preview, linked to the fleet", () => {
    render(<SimulationPane simulation={SIMULATION} serverUrl={SERVER_URL} />);

    expect(screen.getByTitle("Simulation: Downtown blaze")).toHaveAttribute(
      "src",
      "http://127.0.0.1:8780/sim/?scenario=downtown-blaze&view=preview&fleet=1",
    );
  });

  it("streams the preview to the stereo bridge when the chat knows one", () => {
    render(<SimulationPane simulation={SIMULATION} serverUrl={SERVER_URL} bridgeUrl="ws://127.0.0.1:8790" />);

    expect(screen.getByTitle("Simulation: Downtown blaze")).toHaveAttribute(
      "src",
      "http://127.0.0.1:8780/sim/?scenario=downtown-blaze&view=preview&fleet=1&bridge=ws%3A%2F%2F127.0.0.1%3A8790",
    );
  });

  it("names the scenario, its version and its credits", () => {
    render(<SimulationPane simulation={SIMULATION} serverUrl={SERVER_URL} />);

    const pane = screen.getByRole("region", { name: "Simulation" });
    expect(pane).toHaveTextContent("Downtown blaze");
    expect(pane).toHaveTextContent("v3");
    expect(pane).toHaveTextContent("Glass tower by A. Modeller (CC BY 4.0)");
  });

  it("links to the full simulation page", () => {
    render(<SimulationPane simulation={SIMULATION} serverUrl={SERVER_URL} />);

    expect(screen.getByRole("link", { name: "Open simulation" })).toHaveAttribute(
      "href",
      "http://127.0.0.1:8780/sim/?scenario=downtown-blaze",
    );
  });

  it("shows no version when the agent only reported the URL", () => {
    render(
      <SimulationPane
        simulation={{ ...SIMULATION, name: "downtown-blaze", version: null, credits: [] }}
        serverUrl={SERVER_URL}
      />,
    );

    expect(screen.getByRole("region", { name: "Simulation" })).not.toHaveTextContent(/v\d+/);
  });

  it("uses an absolute simulation URL as it is", () => {
    render(
      <SimulationPane
        simulation={{ ...SIMULATION, url: "http://station.test/sim/?scenario=downtown-blaze" }}
        serverUrl={SERVER_URL}
      />,
    );

    expect(screen.getByTitle("Simulation: Downtown blaze")).toHaveAttribute(
      "src",
      "http://station.test/sim/?scenario=downtown-blaze&view=preview&fleet=1",
    );
  });

  it("exports the scenario as a bundle download from the agent server", () => {
    render(<SimulationPane simulation={SIMULATION} serverUrl={SERVER_URL} />);

    const exportLink = screen.getByRole("link", { name: "Export" });
    expect(exportLink).toHaveAttribute("href", "http://127.0.0.1:8780/sim/export/downtown-blaze.zip");
    expect(exportLink).toHaveAttribute("download", "downtown-blaze.surmap-sim.zip");
  });

  it("hands a picked bundle to onImport", async () => {
    const picked: string[] = [];
    render(
      <SimulationPane simulation={SIMULATION} serverUrl={SERVER_URL} onImport={(file) => picked.push(file.name)} />,
    );

    await userEvent.upload(
      screen.getByLabelText("Import simulation"),
      new File(["PK"], "flooded.surmap-sim.zip", { type: "application/zip" }),
    );

    expect(picked).toEqual(["flooded.surmap-sim.zip"]);
  });

  it("disables importing while an import runs", () => {
    render(<SimulationPane simulation={SIMULATION} serverUrl={SERVER_URL} onImport={() => {}} importing />);

    expect(screen.getByLabelText("Import simulation")).toBeDisabled();
  });

  it("shows why the last import was refused", () => {
    render(
      <SimulationPane
        simulation={SIMULATION}
        serverUrl={SERVER_URL}
        onImport={() => {}}
        importError="not a SurMap scenario bundle"
      />,
    );

    expect(screen.getByRole("alert")).toHaveTextContent("not a SurMap scenario bundle");
  });
});
