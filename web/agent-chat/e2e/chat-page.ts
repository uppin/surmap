import type { Locator, Page } from "@playwright/test";

/** The chat page as a user sees it: by role and accessible name, never by CSS class. */
export class ChatPage {
  constructor(private readonly page: Page) {}

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
      .getByRole("region", { name: "Jobs" })
      .getByRole("listitem", { name: `Job ${jobId}` });
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
}
