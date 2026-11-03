import { render, screen, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import App from "./App";
import { SurveyTools } from "./gen/surmap/agent/v1/survey_tools_pb";

describe("placeholder page", () => {
  it("lists every SurveyTools rpc from the generated descriptor, in declaration order", () => {
    render(<App />);

    const list = screen.getByRole("list", { name: "SurveyTools rpcs" });

    expect(within(list).getAllByRole("listitem").map((item) => item.textContent)).toEqual(
      SurveyTools.methods.map((method) => method.name),
    );
  });

  it("shows the rpc list under a heading for the service", () => {
    render(<App />);

    expect(screen.getByRole("heading", { name: "SurveyTools" })).toBeInTheDocument();
  });
});
