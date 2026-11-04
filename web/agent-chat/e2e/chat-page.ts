import type { Locator, Page } from "@playwright/test";

/** The chat page as a user sees it: by role and accessible name, never by CSS class. */
export class ChatPage {
  constructor(private readonly page: Page) {}

  /** The header's SAM station indicator. */
  station(): Locator {
    return this.page.getByRole("status", { name: "SAM station" });
  }

  async startStation(): Promise<void> {
    await this.page.getByRole("button", { name: "Start SAM" }).click();
  }

  async stopStation(): Promise<void> {
    await this.page.getByRole("button", { name: "Stop SAM" }).click();
  }

  /** Opens the chat on the stub server, in a named conversation so reloads find it again. */
  async open(serverUrl: string, conversationId = "e2e-1"): Promise<void> {
    const query = new URLSearchParams({ server: serverUrl, conversation: conversationId });
    await this.page.goto(`/?${query.toString()}`);
  }

  async reload(): Promise<void> {
    await this.page.reload();
  }

  messageBox(): Locator {
    return this.page.getByRole("textbox", { name: "Message" });
  }

  button(name: "Send" | "Steer" | "Stop"): Locator {
    return this.page.getByRole("button", { name, exact: true });
  }

  async send(text: string): Promise<void> {
    await this.messageBox().fill(text);
    await this.button("Send").click();
  }

  async steer(text: string): Promise<void> {
    await this.messageBox().fill(text);
    await this.button("Steer").click();
  }

  async stop(): Promise<void> {
    await this.button("Stop").click();
  }

  conversation(): Locator {
    return this.page.getByRole("log", { name: "Conversation" });
  }

  toolStep(tool: string): Locator {
    return this.page.getByRole("group", { name: `Tool call ${tool}` });
  }

  job(jobId: string): Locator {
    return this.page
      .getByRole("region", { name: "Tasks" })
      .getByRole("listitem", { name: `Job ${jobId}` });
  }

  subagent(subagentId: string): Locator {
    return this.page
      .getByRole("region", { name: "Tasks" })
      .getByRole("listitem", { name: `Subagent ${subagentId}` });
  }

  modelPicker(): Locator {
    return this.page.getByRole("combobox", { name: "Model" });
  }

  frameImage(tool: string): Locator {
    return this.page.getByRole("img", { name: `${tool} result` });
  }

  geometryPreview(): Locator {
    return this.page.getByRole("figure", { name: "Object geometry preview" });
  }

  /** The right-side simulation pane shown when the agent creates a simulation. */
  simulation(): Locator {
    return this.page.getByRole("region", { name: "Simulation" });
  }

  simulationFrame(name: string): Locator {
    return this.page.getByTitle(`Simulation: ${name}`);
  }
}
