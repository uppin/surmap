import { Code, ConnectError } from "@connectrpc/connect";
import { useEffect, useReducer, useRef, useState, type ReactNode } from "react";
import { Composer } from "@/components/Composer";
import { DatasetGallery } from "@/components/DatasetGallery";
import { JobsPanel } from "@/components/JobsPanel";
import { MapPane } from "@/components/MapPane";
import { ModelPicker } from "@/components/ModelPicker";
import { Transcript } from "@/components/Transcript";
import type { ChatPort, DatasetView, MapSceneView } from "@/ports";
import { chatReducer, initialChatState, isTurnActive } from "@/view-model/chat-reducer";

export interface ChatPageProps {
  port: ChatPort;
  /** The agent server the port talks to; relative geometry URLs resolve against it. */
  serverUrl: string;
  conversationId: string;
}

/**
 * The chat: the port, the reducer and the components wired together. The watch stream opens once
 * the server knows the conversation (its history answered, or a turn's first event arrived),
 * because the server answers `WatchConversation` with `NOT_FOUND` before the first turn.
 */
export function ChatPage(props: ChatPageProps): ReactNode {
  const { port, conversationId } = props;
  const [state, dispatch] = useReducer(chatReducer, conversationId, initialChatState);
  const [onServer, setOnServer] = useState(false);
  const [mapScene, setMapScene] = useState<MapSceneView | null>(null);
  const [datasets, setDatasets] = useState<DatasetView[]>([]);
  const [now, setNow] = useState(0);
  const turn = useRef<AbortController | null>(null);

  useEffect(() => {
    const clock = window.setInterval(() => setNow(Date.now()), 1000);
    return () => window.clearInterval(clock);
  }, []);

  // The map scene lives server-side and the agent edits it mid-turn; poll it so
  // placements, moves, camera navigation and routes appear without a reload.
  useEffect(() => {
    let current = true;
    const poll = () => {
      port.getMapScene().then(
        (scene) => {
          if (current) setMapScene((prev) => (prev?.revision === scene.revision ? prev : scene));
        },
        () => {},
      );
    };
    poll();
    const timer = window.setInterval(poll, 2000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [port]);

  useEffect(() => {
    let current = true;
    port.listDatasets().then(
      (found) => {
        if (current) setDatasets(found);
      },
      () => {},
    );
    return () => {
      current = false;
    };
  }, [port]);

  useEffect(() => {
    let current = true;
    port.listModels().then(
      (models) => {
        if (current) dispatch({ type: "models_loaded", models });
      },
      (error: unknown) => {
        if (current) dispatch({ type: "request_failed", message: messageOf(error) });
      },
    );
    return () => {
      current = false;
    };
  }, [port]);

  useEffect(() => {
    let current = true;
    port.getConversation(conversationId).then(
      (events) => {
        if (!current) return;
        setOnServer(true);
        dispatch({ type: "history_loaded", events, at: Date.now() });
      },
      (error: unknown) => {
        if (current && !isNotFound(error)) dispatch({ type: "request_failed", message: messageOf(error) });
      },
    );
    return () => {
      current = false;
    };
  }, [port, conversationId]);

  useEffect(() => {
    if (!onServer) return;
    const controller = new AbortController();
    void (async () => {
      try {
        for await (const event of port.watch(conversationId, controller.signal)) {
          dispatch({ type: "event", event, at: Date.now() });
        }
      } catch (error) {
        if (!controller.signal.aborted) dispatch({ type: "request_failed", message: messageOf(error) });
      }
    })();
    return () => controller.abort();
  }, [port, conversationId, onServer]);

  useEffect(() => () => turn.current?.abort(), []);

  const startTurn = (text: string) => {
    dispatch({ type: "turn_requested" });
    const controller = new AbortController();
    turn.current = controller;
    void (async () => {
      let finished = false;
      try {
        const events = port.streamTurn({ conversationId, modelId: state.modelId, text }, controller.signal);
        for await (const event of events) {
          // The first event means the server has created the conversation, so it can be watched.
          setOnServer(true);
          if (event.event.case === "turnFinished") finished = true;
          dispatch({ type: "event", event, at: Date.now() });
        }
        if (!finished && !controller.signal.aborted) {
          dispatch({ type: "stream_failed", message: "the agent server closed the stream" });
        }
      } catch (error) {
        if (!controller.signal.aborted) dispatch({ type: "stream_failed", message: messageOf(error) });
      }
    })();
  };

  // Guidance goes to the running turn; when the server had no turn running, it starts one instead.
  const steer = (text: string) => {
    void port.steer(conversationId, text).then(
      (outcome) => {
        if (!outcome.accepted) startTurn(text);
      },
      (error: unknown) => dispatch({ type: "request_failed", message: messageOf(error) }),
    );
  };

  const stop = () => {
    dispatch({ type: "stop_requested" });
    port.cancelTurn(conversationId).catch((error: unknown) => {
      dispatch({ type: "request_failed", message: messageOf(error) });
    });
  };

  const cancelJob = (jobId: string) => {
    port.cancelJob(conversationId, jobId).catch((error: unknown) => {
      dispatch({ type: "request_failed", message: messageOf(error) });
    });
  };

  return (
    <main className="mx-auto flex min-h-svh w-full max-w-5xl flex-col gap-4 p-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col">
          <h1 className="text-lg font-semibold">Survey agent</h1>
          <p className="text-xs text-muted-foreground">{props.serverUrl}</p>
        </div>
        <ModelPicker
          models={state.models}
          value={state.modelId}
          onChange={(modelId) => dispatch({ type: "model_selected", modelId })}
        />
      </header>
      <MapPane scene={mapScene} />
      <DatasetGallery datasets={datasets} serverUrl={props.serverUrl} onRun={startTurn} />
      <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_16rem]">
        <Transcript items={state.transcript} serverUrl={props.serverUrl} />
        <JobsPanel jobs={state.jobs} now={now} onCancel={cancelJob} />
      </div>
      <Composer busy={isTurnActive(state)} onSend={startTurn} onSteer={steer} onStop={stop} />
    </main>
  );
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isNotFound(error: unknown): boolean {
  return error instanceof ConnectError && error.code === Code.NotFound;
}
