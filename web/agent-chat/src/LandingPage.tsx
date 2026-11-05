import { useState, type FormEvent, type ReactNode } from "react";
import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const REPOSITORY_URL = "https://github.com/uppin/surmap";

export interface LandingPageProps {
  /** Whether the chat needs the pass code first: the agent is gated and this tab is not signed in. */
  needsCode: boolean;
  /** Trades the pass code for a session; rejects when the agent refuses it. */
  signIn: (code: string) => Promise<void>;
  /** Opens the chat, once signed in or when no code is needed. */
  onEnter: () => void;
  /** Why the last sign-in failed, e.g. a refused `?code=`; shown until the next attempt. */
  initialError?: string | null;
}

/** The page the chat app opens on: what SurMap is, its source, and the way into the chat. */
export function LandingPage(props: LandingPageProps): ReactNode {
  const [code, setCode] = useState("");
  const [error, setError] = useState<string | null>(props.initialError ?? null);
  const [busy, setBusy] = useState(false);

  async function enter(event: FormEvent<HTMLFormElement>): Promise<void> {
    event.preventDefault();
    if (!props.needsCode) {
      props.onEnter();
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await props.signIn(code);
      props.onEnter();
    } catch (refused) {
      setError(refused instanceof Error ? refused.message : String(refused));
      setBusy(false);
    }
  }

  return (
    <main className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle className="text-2xl">SurMap</CardTitle>
          <CardDescription>
            A passive drone surveyor for disaster response: a GPS-anchored 3D semantic map from stereo video,
            and a survey agent to plan, run and question it.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <form className="flex flex-col gap-2" onSubmit={(event) => void enter(event)}>
            {props.needsCode && (
              <>
                <label htmlFor="pass-code" className="text-sm font-medium">
                  Pass code
                </label>
                <input
                  id="pass-code"
                  type="password"
                  autoComplete="current-password"
                  autoFocus
                  required
                  className="rounded-md border bg-background px-2 py-1.5 text-sm"
                  value={code}
                  onChange={(event) => setCode(event.target.value)}
                />
              </>
            )}
            {error && (
              <p role="alert" className="text-sm text-destructive">
                {error}
              </p>
            )}
            <Button type="submit" disabled={busy}>
              {props.needsCode ? "Enter chat" : "Open chat"}
            </Button>
          </form>
          <a
            href={REPOSITORY_URL}
            target="_blank"
            rel="noreferrer"
            className="inline-flex items-center gap-1 self-start text-sm text-muted-foreground underline-offset-4 hover:underline"
          >
            Source on GitHub — uppin/surmap
            <ExternalLink aria-hidden className="size-3.5" />
          </a>
        </CardContent>
      </Card>
    </main>
  );
}
