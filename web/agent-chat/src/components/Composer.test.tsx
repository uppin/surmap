import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it } from "vitest";
import { Composer } from "./Composer";

/** Renders the composer and records what it asks the chat to do. */
function renderComposer({ busy }: { busy: boolean }) {
  const asked = { sent: [] as string[], steered: [] as string[], stops: 0 };
  render(
    <Composer
      busy={busy}
      onSend={(text) => asked.sent.push(text)}
      onSteer={(text) => asked.steered.push(text)}
      onStop={() => {
        asked.stops += 1;
      }}
    />,
  );
  const user = userEvent.setup();
  const offers = (name: string) => screen.queryByRole("button", { name }) !== null;
  const messageBox = () => screen.getByRole("textbox", { name: "Message" });
  return {
    asked,
    messageBox,
    write: (text: string) => user.type(messageBox(), text),
    press: (name: string) => user.click(screen.getByRole("button", { name })),
    pressEnter: () => user.keyboard("{Enter}"),
    offered: () => ({
      send: offers("Send"),
      steer: offers("Steer"),
      stop: offers("Stop"),
    }),
  };
}

describe("Composer", () => {
  it("starts a turn with the message when idle and Send is pressed", async () => {
    const composer = renderComposer({ busy: false });
    await composer.write("Survey the warehouse");

    await composer.press("Send");

    expect(composer.asked).toEqual({ sent: ["Survey the warehouse"], steered: [], stops: 0 });
  });

  it("starts a turn when Enter is pressed in the message box", async () => {
    const composer = renderComposer({ busy: false });
    await composer.write("List the demos");

    await composer.pressEnter();

    expect(composer.asked.sent).toEqual(["List the demos"]);
  });

  it("clears the message box once the message is sent", async () => {
    const composer = renderComposer({ busy: false });
    await composer.write("List the demos");

    await composer.press("Send");

    expect(composer.messageBox()).toHaveValue("");
  });

  it("sends nothing for a blank message", async () => {
    const composer = renderComposer({ busy: false });
    await composer.write("   ");

    await composer.pressEnter();

    expect(composer.asked).toEqual({ sent: [], steered: [], stops: 0 });
  });

  it("offers Send, and no Stop, while idle", () => {
    const composer = renderComposer({ busy: false });

    expect(composer.offered()).toEqual({ send: true, steer: false, stop: false });
  });

  it("offers Steer and Stop, instead of Send, while busy", () => {
    const composer = renderComposer({ busy: true });

    expect(composer.offered()).toEqual({ send: false, steer: true, stop: true });
  });

  it("keeps the message box enabled while the agent works", () => {
    const composer = renderComposer({ busy: true });

    expect(composer.messageBox()).toBeEnabled();
  });

  it("steers the running turn, instead of starting one, while busy", async () => {
    const composer = renderComposer({ busy: true });
    await composer.write("Use the KITTI scene instead");

    await composer.press("Steer");

    expect(composer.asked).toEqual({ sent: [], steered: ["Use the KITTI scene instead"], stops: 0 });
  });

  it("cancels the running turn when Stop is pressed", async () => {
    const composer = renderComposer({ busy: true });

    await composer.press("Stop");

    expect(composer.asked).toEqual({ sent: [], steered: [], stops: 1 });
  });
});
