import { useState, type ReactNode } from "react";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export interface ComposerProps {
  /** A turn is in flight: the input stays enabled and sends Steer; Stop is offered. */
  busy: boolean;
  onSend(text: string): void;
  onSteer(text: string): void;
  onStop(): void;
}

/** The message box. Idle it starts a turn; busy it steers the running turn and offers Stop. */
export function Composer(props: ComposerProps): ReactNode {
  const [draft, setDraft] = useState("");

  const submit = () => {
    const text = draft.trim();
    if (text === "") return;
    setDraft("");
    if (props.busy) props.onSteer(text);
    else props.onSend(text);
  };

  return (
    <form
      className="flex flex-col gap-2 border-t pt-3"
      onSubmit={(event) => {
        event.preventDefault();
        submit();
      }}
    >
      <Textarea
        aria-label="Message"
        rows={2}
        value={draft}
        placeholder={props.busy ? "Steer the running turn…" : "Ask the survey agent…"}
        onChange={(event) => setDraft(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
            event.preventDefault();
            submit();
          }
        }}
      />
      <div className="flex justify-end gap-2">
        {props.busy ? (
          <>
            <Button type="button" variant="outline" onClick={props.onStop}>
              Stop
            </Button>
            <Button type="submit">Steer</Button>
          </>
        ) : (
          <Button type="submit">Send</Button>
        )}
      </div>
    </form>
  );
}
