import { createClient, type Transport } from "@connectrpc/connect";
import { createConnectTransport } from "@connectrpc/connect-web";
import { ChatService } from "@/gen/surmap/agent/v1/chat_pb";
import { AgentJobs } from "@/gen/surmap/agent/v1/jobs_pb";
import {
  MapLayerKind,
  MapTools,
  type GeoPoint,
  type MapScene,
} from "@/gen/surmap/agent/v1/map_tools_pb";
import type { ChatPort, MapPointView, MapSceneView } from "@/ports";

/** The header `AgentJobs` calls name their conversation in; each conversation has its own jobs. */
export const CONVERSATION_HEADER = "surmap-conversation-id";

/** The agent server's default address. */
export const DEFAULT_SERVER_URL = "http://127.0.0.1:8780";

/** A Connect transport to the agent server at `baseUrl`. */
export function createAgentTransport(baseUrl: string): Transport {
  return createConnectTransport({ baseUrl });
}

/** The `ChatPort` over the generated `ChatService` and `AgentJobs` clients. */
export function createConnectChatPort(transport: Transport): ChatPort {
  const chat = createClient(ChatService, transport);
  const jobs = createClient(AgentJobs, transport);
  const map = createClient(MapTools, transport);
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
