import { Code, ConnectError } from "@connectrpc/connect";
import { useEffect, useMemo, useReducer, useRef, useState, type ReactNode } from "react";
import { Composer } from "@/components/Composer";
import { DatasetGallery } from "@/components/DatasetGallery";
import { TasksPanel } from "@/components/TasksPanel";
import { MapPane } from "@/components/MapPane";
import { ModelPicker } from "@/components/ModelPicker";
import { DroneMapPane } from "@/components/DroneMapPane";
import { SimulationPane } from "@/components/SimulationPane";
import { StationIndicator } from "@/components/StationIndicator";
import { Transcript } from "@/components/Transcript";
import type { ChatPort, DatasetView, DroneMapView, MapSceneView, StationView } from "@/ports";
import {
  chatReducer,
  initialChatState,
  isAwaitingReply,
  isTurnActive,
} from "@/view-model/chat-reducer";
import { simulationFromTranscript, type SimulationView } from "@/view-model/simulation";

export interface ChatPageProps {
  port: ChatPort;
  /** The agent server the port talks to; relative geometry URLs resolve against it. */
  serverUrl: string;
  /** The agent's stereo bridge the simulation preview streams to; none: the preview does not. */
  bridgeUrl?: string;
  conversationId: string;
  /** The model to start on, kept when the server lists it; otherwise the server's default. */
  initialModelId?: string | null;
  /** Called with the model the conversation's turns will use, whenever it is set or changes. */
  onModelChange?: (modelId: string) => void;
}

/**
 * The chat: the port, the reducer and the components wired together. The watch stream opens once
 * the server knows the conversation (its history answered, or a turn's first event arrived),
 * because the server answers `WatchConversation` with `NOT_FOUND` before the first turn.
 */
export function ChatPage(props: ChatPageProps): ReactNode {
  const { port, conversationId, onModelChange } = props;
  const [state, dispatch] = useReducer(
    chatReducer,
    { conversationId, modelId: props.initialModelId ?? null },
    ({ conversationId, modelId }) => initialChatState(conversationId, modelId),
  );
  const [onServer, setOnServer] = useState(false);
  const [mapScene, setMapScene] = useState<MapSceneView | null>(null);
  const [datasets, setDatasets] = useState<DatasetView[]>([]);
  const [station, setStation] = useState<StationView | null>(null);
  const [screen, setScreen] = useState<"chat" | "gallery">(() =>
    new URLSearchParams(window.location.search).get("screen") === "gallery" ? "gallery" : "chat",
  );

  const showScreen = (next: "chat" | "gallery") => {
    setScreen(next);
    const params = new URLSearchParams(window.location.search);
    if (next === "gallery") params.set("screen", "gallery");
    else params.delete("screen");
    window.history.replaceState({}, "", `${window.location.pathname}?${params}`);
  };
  const [now, setNow] = useState(0);
  const turn = useRef<AbortController | null>(null);
  // A simulation the agent created in this conversation, shown in the right-side pane — or the
  // version an import from the pane made of it, until the transcript reports a newer one.
  const created = useMemo(() => simulationFromTranscript(state.transcript), [state.transcript]);
  const [imported, setImported] = useState<SimulationView | null>(null);
  const [importing, setImporting] = useState(false);
  const [importError, setImportError] = useState<string | null>(null);
  const simulation = newerOf(created, imported);
  const scenarioId = simulation?.id ?? null;

  // The map the simulation's drone builds: shown from the first poll that finds it flying, and
  // kept with its last image once it lands (a poll with no flying drone changes nothing).
  const [heldMap, setHeldMap] = useState<{ scenarioId: string; map: DroneMapView } | null>(null);
  const droneMap = heldMap !== null && heldMap.scenarioId === scenarioId ? heldMap.map : null;
  useEffect(() => {
    if (scenarioId === null) return;
    let current = true;
    const poll = () => {
      port.getDroneMap(scenarioId).then(
        (map) => {
          if (current && map !== null) setHeldMap({ scenarioId, map });
        },
        () => {},
      );
    };
    poll();
    const timer = window.setInterval(poll, 1000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [port, scenarioId]);

  const importSimulation = (bundle: File) => {
    if (simulation === null) return;
    setImporting(true);
    setImportError(null);
    port.importSimulation(bundle, simulation.id).then(
      (scenario) => {
        setImported(scenario);
        setImporting(false);
      },
      (error: unknown) => {
        setImportError(messageOf(error));
        setImporting(false);
      },
    );
  };

  // Only once models load: before then the model is the URL's unchecked preference.
  const modelInUse = state.models.length > 0 ? state.modelId : null;
  useEffect(() => {
    if (modelInUse !== null) onModelChange?.(modelInUse);
  }, [modelInUse, onModelChange]);

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

  // The SAM station's status reads Modal's counters, never the station, so polling it neither
  // starts its GPU nor keeps it up.
  useEffect(() => {
    let current = true;
    const poll = () => {
      port.getStationStatus().then(
        (status) => {
          if (current) setStation(status);
        },
        () => {},
      );
    };
    poll();
    const timer = window.setInterval(poll, 5000);
    return () => {
      current = false;
      window.clearInterval(timer);
    };
  }, [port]);

  const driveStation = (action: "start" | "stop") => {
    setStation((prev) => (prev ? { ...prev, state: action === "start" ? "starting" : "stopping", detail: "" } : prev));
    (action === "start" ? port.startStation() : port.stopStation()).then(setStation, (error: unknown) =>
      setStation((prev) => (prev ? { ...prev, state: "error", detail: messageOf(error) } : prev)),
    );
  };

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

  const runFromGallery = (text: string) => {
    showScreen("chat");
    startTurn(text);
  };

  return (
    <main
      className={`mx-auto flex min-h-svh w-full flex-col gap-4 p-4 ${screen === "gallery" || simulation !== null ? "max-w-7xl" : "max-w-5xl"}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div className="flex flex-col">
          <h1 className="text-lg font-semibold">Survey agent</h1>
          <p className="text-xs text-muted-foreground">{props.serverUrl}</p>
        </div>
        <div className="flex items-center gap-3">
          <nav aria-label="Screens" className="flex gap-1 rounded-md border p-1">
            <button
              type="button"
              aria-pressed={screen === "chat"}
              className={`rounded px-3 py-1 text-sm ${screen === "chat" ? "bg-primary text-primary-foreground" : ""}`}
              onClick={() => showScreen("chat")}
            >
              Chat
            </button>
            <button
              type="button"
              aria-pressed={screen === "gallery"}
              className={`rounded px-3 py-1 text-sm ${screen === "gallery" ? "bg-primary text-primary-foreground" : ""}`}
              onClick={() => showScreen("gallery")}
            >
              Dataset gallery
            </button>
          </nav>
          <StationIndicator
            status={station}
            onStart={() => driveStation("start")}
            onStop={() => driveStation("stop")}
          />
          <ModelPicker
            models={state.models}
            value={state.modelId}
            onChange={(modelId) => dispatch({ type: "model_selected", modelId })}
          />
        </div>
      </header>
      {screen === "gallery" ? (
        <DatasetGallery datasets={datasets} serverUrl={props.serverUrl} onRun={runFromGallery} />
      ) : simulation !== null ? (
        <>
          <MapPane scene={mapScene} />
          <div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1fr)_28rem]">
            <div className="flex min-w-0 flex-col gap-4">
              <Transcript
                items={state.transcript}
                serverUrl={props.serverUrl}
                awaitingReply={isAwaitingReply(state)}
              />
              <Composer busy={isTurnActive(state)} onSend={startTurn} onSteer={steer} onStop={stop} />
            </div>
            <div className="flex flex-col gap-4">
              <SimulationPane
                simulation={simulation}
                serverUrl={props.serverUrl}
                bridgeUrl={props.bridgeUrl}
                onImport={importSimulation}
                importing={importing}
                importError={importError}
              />
              {droneMap !== null && <DroneMapPane map={droneMap} />}
              <TasksPanel jobs={state.jobs} subagents={state.subagents} now={now} onCancel={cancelJob} />
            </div>
          </div>
        </>
      ) : (
        <>
          <MapPane scene={mapScene} />
          <div className="grid gap-4 md:grid-cols-[minmax(0,1fr)_16rem]">
            <Transcript
              items={state.transcript}
              serverUrl={props.serverUrl}
              awaitingReply={isAwaitingReply(state)}
            />
            <TasksPanel jobs={state.jobs} subagents={state.subagents} now={now} onCancel={cancelJob} />
          </div>
          <Composer busy={isTurnActive(state)} onSend={startTurn} onSteer={steer} onStop={stop} />
        </>
      )}
    </main>
  );
}

/** The imported version when it is of the created simulation and newer than the transcript's. */
function newerOf(created: SimulationView | null, imported: SimulationView | null): SimulationView | null {
  if (created === null || imported === null || imported.id !== created.id) return created;
  return (created.version ?? 0) < (imported.version ?? 0) ? imported : created;
}

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

function isNotFound(error: unknown): boolean {
  return error instanceof ConnectError && error.code === Code.NotFound;
}
