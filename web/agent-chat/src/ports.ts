import type { TurnEvent } from "@/gen/surmap/agent/v1/chat_pb";
import type { SimulationView } from "@/view-model/simulation";

/** What a turn is started with. */
export interface StreamTurnInput {
  /** The conversation to continue; the server starts it when it does not exist. */
  conversationId: string;
  /** A `ChatModel` id; `null` lets the server use its default model. */
  modelId: string | null;
  /** The user's message. */
  text: string;
}

/** How the server took a steer. */
export interface SteerOutcome {
  /** `false` when no turn was running to take the guidance; the client starts a turn instead. */
  accepted: boolean;
}

/** A model a conversation can run on, as the picker shows it. */
export interface ModelInfo {
  id: string;
  /** Who serves it, e.g. `"muse"` or `"ollama"`. */
  provider: string;
  displayName: string;
  /** Whether the server can reach it now. */
  available: boolean;
  /** Why it cannot be reached; empty when it can. */
  detail: string;
  /** Whether a turn uses it when no model is named. */
  isDefault: boolean;
}

/** A WGS84 position on the map, as the map pane draws it. */
export interface MapPointView {
  lon: number;
  lat: number;
  altM: number | null;
}

/** One GLB shape placed on the map by the agent. */
export interface MapObjectView {
  id: string;
  label: string;
  geometryUri: string;
  position: MapPointView;
  rotationDeg: number;
  scale: number;
}

/** One route path drawn on the map by the agent. */
export interface MapRouteView {
  id: string;
  name: string;
  color: string;
  waypoints: MapPointView[];
}

/** Where the map camera looks. */
export interface MapCameraView {
  centre: MapPointView;
  zoom: number;
  pitchDeg: number;
  bearingDeg: number;
}

/** One catalogue layer and whether this scene draws it. */
export interface MapLayerView {
  id: string;
  name: string;
  kind: "RASTER" | "VECTOR";
  sourceUrl: string;
  sourceLayer: string;
  loaded: boolean;
  isDefault: boolean;
}

/** One dataset in the gallery, as its card shows it. */
export interface DatasetView {
  id: string;
  title: string;
  description: string;
  /** Who publishes it, e.g. `"KITTI"`; a new source names itself here. */
  provider: string;
  licenseName: string;
  licenseUrl: string;
  attribution: string;
  /** `"grey"` or `"color"` frames. */
  modality: "grey" | "color";
  officialUrl: string;
  defaultPrompt: string;
  prepared: boolean;
  frameCount: number;
  thumbnailAvailable: boolean;
  /** A thumbnail the source itself publishes; empty when it has none. */
  thumbnailUrl: string;
  locationLabel: string;
  gpsCentre: { lon: number; lat: number } | null;
  gpsTrack: { lon: number; lat: number }[];
}

/** How a gallery card asks the agent to run a dataset. */
export type DatasetRunMode = "rtabmap" | "sam" | "both";

/** The whole display scene the map pane renders; `revision` bumps on every agent edit. */
export interface MapSceneView {
  sceneId: string;
  revision: number;
  camera: MapCameraView;
  objects: MapObjectView[];
  routes: MapRouteView[];
  layers: MapLayerView[];
}

/** Where the SAM station (the GPU SAM runs on) is in its life. */
export type StationStateView = "off" | "queued" | "starting" | "ready" | "stopping" | "error";

/** The SAM station as `StationTools` reports it. */
export interface StationView {
  state: StationStateView;
  /** One line on the state: what it waits for, or why it errored. */
  detail: string;
  containers: number;
  /** Seconds without a SAM frame after which the agent stops it. */
  idleTimeoutS: number;
  /** Seconds since its last SAM frame; 0 when it is not ready. */
  idleForS: number;
  /** What runs it, e.g. "modal:main/surmap-station". */
  backend: string;
}

/**
 * Everything the chat UI asks of the agent server. Components and the view model never reach the
 * network except through this port; the Connect adapter implements it and tests fake it.
 */
export interface ChatPort {
  /** Sends the user's message and streams the turn it starts, until the turn finishes. */
  streamTurn(input: StreamTurnInput, signal: AbortSignal): AsyncIterable<TurnEvent>;
  /** Streams turns that start while no `streamTurn` is open (job-event turns). */
  watch(conversationId: string, signal: AbortSignal): AsyncIterable<TurnEvent>;
  /** Adds guidance to the running turn. */
  steer(conversationId: string, text: string): Promise<SteerOutcome>;
  /** Cancels the running turn and its blocking tool calls. */
  cancelTurn(conversationId: string): Promise<void>;
  /** Cancels one of the conversation's jobs. */
  cancelJob(conversationId: string, jobId: string): Promise<void>;
  /** The models the server is configured with, the default one marked. */
  listModels(): Promise<ModelInfo[]>;
  /** Every event of the conversation so far, in order, for redrawing it after a reload. */
  getConversation(conversationId: string): Promise<TurnEvent[]>;
  /** The current map scene (objects, camera, routes); the pane polls it to redraw agent edits. */
  getMapScene(): Promise<MapSceneView>;
  /** Every dataset in the gallery catalogue, in catalogue order. */
  listDatasets(): Promise<DatasetView[]>;
  /** The SAM station's status; `null` when the agent runs without one. Never starts the GPU. */
  getStationStatus(): Promise<StationView | null>;
  /** Starts the SAM station's GPU; resolves once it answers. */
  startStation(): Promise<StationView>;
  /** Stops the SAM station's GPU now. */
  stopStation(): Promise<StationView>;
  /**
   * Stores an exported simulation bundle on the station: as the next version of `into`, or as a
   * new scenario when `null`. Resolves with the scenario it became; rejects with the reason the
   * station refused it.
   */
  importSimulation(bundle: File, into: string | null): Promise<SimulationView>;
}
