import { Code, ConnectError, createClient, type Interceptor, type Transport } from "@connectrpc/connect";
import { createConnectTransport } from "@connectrpc/connect-web";
import { ChatService } from "@/gen/surmap/agent/v1/chat_pb";
import { AgentJobs } from "@/gen/surmap/agent/v1/jobs_pb";
import {
  MapLayerKind,
  MapTools,
  type GeoPoint,
  type MapScene,
} from "@/gen/surmap/agent/v1/map_tools_pb";
import {
  StationState,
  StationTools,
  type StationStatus,
  type StationStatusResponse,
} from "@/gen/surmap/agent/v1/station_tools_pb";
import type { ChatPort, DatasetView, MapPointView, MapSceneView, StationStateView, StationView } from "@/ports";
import type { SimulationView } from "@/view-model/simulation";

/** The header `AgentJobs` calls name their conversation in; each conversation has its own jobs. */
export const CONVERSATION_HEADER = "surmap-conversation-id";

/** The agent server's default address. */
export const DEFAULT_SERVER_URL = "http://127.0.0.1:8780";

/** A Connect transport to the agent server at `baseUrl`, adding `interceptors` to each call. */
export function createAgentTransport(baseUrl: string, interceptors: Interceptor[] = []): Transport {
  return createConnectTransport({ baseUrl, interceptors });
}

interface DatasetJson {
  id: string;
  title: string;
  description: string;
  provider: string;
  license: { name: string; url: string; attribution: string };
  modality: string;
  official_url: string;
  default_prompt: string;
  prepared: boolean;
  frame_count: number;
  thumbnail_available: boolean;
  thumbnail_url: string;
  location_label: string;
  gps_centre: { lon: number; lat: number } | null;
  gps_track: { lon: number; lat: number }[];
  credit: string;
  runs?: {
    cache_key: string;
    run_id: string;
    title: string;
    frames: number;
    created_at: number;
    preview_frame_id: number;
  }[];
}

/**
 * The `ChatPort` over the generated `ChatService` and `AgentJobs` clients; plain HTTP calls (the
 * gallery, simulation import) go to `baseUrl`, carrying `token()` as a bearer token when there is one.
 */
export function createConnectChatPort(
  transport: Transport,
  baseUrl: string = DEFAULT_SERVER_URL,
  token: () => string | null = () => null,
): ChatPort {
  const chat = createClient(ChatService, transport);
  const jobs = createClient(AgentJobs, transport);
  const map = createClient(MapTools, transport);
  const station = createClient(StationTools, transport);
  return {
    streamTurn: (input, signal) =>
      chat.streamTurn(
        {
          conversationId: input.conversationId,
          text: input.text,
          modelId: input.modelId ?? undefined,
        },
        { signal },
      ),
    watch: (conversationId, signal) => chat.watchConversation({ conversationId }, { signal }),
    async steer(conversationId, text) {
      const response = await chat.steer({ conversationId, text });
      return { accepted: response.accepted };
    },
    async cancelTurn(conversationId) {
      await chat.cancelTurn({ conversationId });
    },
    async cancelJob(conversationId, jobId) {
      await jobs.cancelJob(
        { jobId },
        { headers: { [CONVERSATION_HEADER]: conversationId } },
      );
    },
    async listModels() {
      const response = await chat.listModels({});
      return response.models.map((model) => ({
        id: model.id,
        provider: model.provider,
        displayName: model.displayName,
        available: model.available,
        detail: model.detail,
        isDefault: model.id === response.defaultModelId,
      }));
    },
    async getConversation(conversationId) {
      const response = await chat.getConversation({ conversationId });
      return response.events;
    },
    async getMapScene() {
      const response = await map.getMapScene({});
      if (!response.scene) throw new Error("the agent server returned no map scene");
      return sceneView(response.scene);
    },
    async listDatasets() {
      const response = await fetch(`${baseUrl.replace(/\/$/, "")}/datasets`);
      if (!response.ok) throw new Error(`dataset gallery failed: ${response.status}`);
      const body = (await response.json()) as { datasets: DatasetJson[] };
      return body.datasets.map(datasetView);
    },
    async importSimulation(bundle, into) {
      const query = into === null ? "" : `?into=${encodeURIComponent(into)}`;
      const session = token();
      const response = await fetch(`${baseUrl.replace(/\/$/, "")}/sim/import${query}`, {
        method: "POST",
        headers: { "content-type": "application/zip", ...(session ? { authorization: `Bearer ${session}` } : {}) },
        body: bundle,
      });
      if (!response.ok) {
        const reason = response.status === 413 ? "the bundle is too large to upload" : await response.text();
        throw new Error(`import refused (${response.status}): ${reason}`);
      }
      const body = (await response.json()) as { scenario: SimulationView };
      return body.scenario;
    },
    async getStationStatus() {
      try {
        return stationView(await station.getStationStatus({}));
      } catch (error) {
        // An agent with no station does not mount StationTools.
        if (ConnectError.from(error).code === Code.Unimplemented) return null;
        throw error;
      }
    },
    async startStation() {
      return stationView(await station.startStation({}));
    },
    async stopStation() {
      return stationView(await station.stopStation({}));
    },
  };
}

const STATION_STATES: Record<StationState, StationStateView> = {
  [StationState.UNSPECIFIED]: "off",
  [StationState.OFF]: "off",
  [StationState.QUEUED]: "queued",
  [StationState.STARTING]: "starting",
  [StationState.READY]: "ready",
  [StationState.STOPPING]: "stopping",
  [StationState.ERROR]: "error",
};

function stationView(response: StationStatusResponse): StationView {
  const status: StationStatus | undefined = response.status;
  return {
    state: STATION_STATES[status?.state ?? StationState.UNSPECIFIED],
    detail: status?.detail ?? "",
    containers: status?.containers ?? 0,
    idleTimeoutS: status?.idleTimeoutS ?? 0,
    idleForS: status?.idleForS ?? 0,
    backend: status?.backend ?? "",
  };
}

function datasetView(json: DatasetJson): DatasetView {
  return {
    id: json.id,
    title: json.title,
    description: json.description,
    provider: json.provider,
    licenseName: json.license.name,
    licenseUrl: json.license.url,
    attribution: json.license.attribution,
    modality: json.modality === "color" ? "color" : "grey",
    officialUrl: json.official_url,
    defaultPrompt: json.default_prompt,
    prepared: json.prepared,
    frameCount: json.frame_count,
    thumbnailAvailable: json.thumbnail_available,
    thumbnailUrl: json.thumbnail_url ?? "",
    locationLabel: json.location_label,
    gpsCentre: json.gps_centre,
    gpsTrack: json.gps_track,
    runs: (json.runs ?? []).map((run) => ({
      cacheKey: run.cache_key,
      runId: run.run_id,
      title: run.title,
      frames: run.frames,
      createdAt: run.created_at,
      previewFrameId: run.preview_frame_id,
    })),
  };
}

function pointView(point: GeoPoint | undefined): MapPointView {
  return { lon: point?.lon ?? 0, lat: point?.lat ?? 0, altM: point?.altM ?? null };
}

function sceneView(scene: MapScene): MapSceneView {
  return {
    sceneId: scene.sceneId,
    revision: Number(scene.revision),
    camera: {
      centre: pointView(scene.camera?.centre),
      zoom: scene.camera?.zoom ?? 16,
      pitchDeg: scene.camera?.pitchDeg ?? 0,
      bearingDeg: scene.camera?.bearingDeg ?? 0,
    },
    objects: scene.objects.map((object) => ({
      id: object.id,
      label: object.label,
      geometryUri: object.geometryUri,
      position: pointView(object.position),
      rotationDeg: object.rotationDeg,
      scale: object.scale,
    })),
    routes: scene.routes.map((route) => ({
      id: route.id,
      name: route.name,
      color: route.color,
      waypoints: route.waypoints.map(pointView),
    })),
    layers: scene.layers.map((layer) => ({
      id: layer.id,
      name: layer.name,
      kind: layer.kind === MapLayerKind.RASTER ? ("RASTER" as const) : ("VECTOR" as const),
      sourceUrl: layer.sourceUrl,
      sourceLayer: layer.sourceLayer,
      loaded: layer.loaded,
      isDefault: layer.isDefault,
    })),
  };
}
