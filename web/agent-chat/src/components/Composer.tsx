import type { ReactNode } from "react";

export interface ComposerProps {
  /** A turn is in flight: the input stays enabled and sends Steer; Stop is offered. */
  busy: boolean;
  onSend(text: string): void;
  onSteer(text: string): void;
  onStop(): void;
}

/** The message box. Idle it starts a turn; busy it steers the running turn and offers Stop. */
export function Composer(props: ComposerProps): ReactNode {
  void props;
  // TODO(pr-9): implement
  return null;
}
