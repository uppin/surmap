import { render, screen } from "@testing-library/react";
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
  it("embeds the live simulation page for the created scenario", () => {
    render(<SimulationPane simulation={SIMULATION} serverUrl={SERVER_URL} />);

    expect(screen.getByTitle("Simulation: Downtown blaze")).toHaveAttribute(
      "src",
      "http://127.0.0.1:8780/sim/?scenario=downtown-blaze",
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
      "http://station.test/sim/?scenario=downtown-blaze",
    );
  });
});
