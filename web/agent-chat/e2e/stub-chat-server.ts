/**
 * A scripted stand-in for the agent server (`python -m surmap.agent`) for the Playwright suite:
 * `ChatService` and `AgentJobs` over the Connect protocol, plus `GET /geometry/...` GLBs, with the
 * CORS the browser needs. Each test scripts its own turns and reads back what the page sent.
 */
import { createServer, type IncomingMessage, type ServerResponse } from "node:http";
import type { AddressInfo } from "node:net";
import { Readable } from "node:stream";
import { createConnectRouter } from "@connectrpc/connect";
import { createFetchHandler } from "@connectrpc/connect/protocol";
import {
  ChatService,
  type TurnEvent,
  type UserMessage,
} from "../src/gen/surmap/agent/v1/chat_pb";
import { JobStatus } from "../src/gen/surmap/agent/v1/execution_pb";
import { AgentJobs } from "../src/gen/surmap/agent/v1/jobs_pb";

/** The header `AgentJobs` calls name their conversation in. */
const CONVERSATION_HEADER = "surmap-conversation-id";

export interface TurnRequest {
  conversationId: string;
  text: string;
  modelId: string | undefined;
}

/** What a scripted turn can wait on while it streams. */
export interface TurnScriptContext {
  request: TurnRequest;
  /** The text of the next `Steer` sent while this turn runs. */
  nextSteer(): Promise<string>;
  /** Settles when `CancelTurn` is called for this turn's conversation. */
  cancelled: Promise<void>;
}

/**
 * Streams a turn after the stub's own `user_message` event. Yielded events are re-stamped with the
 * conversation, the turn id and the next `seq`, so scripts can build them with `aConversation()`.
 */
export type TurnScript = (context: TurnScriptContext) => AsyncIterable<TurnEvent>;

export interface StubModel {
  id: string;
  provider: string;
  displayName: string;
  available?: boolean;
  detail?: string;
}

export interface StubChatOptions {
  models?: StubModel[];
  defaultModelId?: string;
  /** How every `StreamTurn` answers; a turn that only finishes when absent. */
  turn?: TurnScript;
  /** Events already recorded per conversation, served by `GetConversation`. */
  history?: Record<string, TurnEvent[]>;
  /** GLB bodies by request path, e.g. `/geometry/run-7/obj-3.glb`. */
  glb?: Record<string, Uint8Array>;
}

export interface StubChatServer {
  url: string;
  received: {
    turns: TurnRequest[];
    steers: { conversationId: string; text: string }[];
    cancelTurns: string[];
    cancelJobs: { conversationId: string | null; jobId: string }[];
    geometry: string[];
  };
  /** Settles once the page holds a `WatchConversation` stream open for the conversation. */
  watching(conversationId: string): Promise<void>;
  /** Streams a job-event turn to the conversation's watchers. */
  pushWatchTurn(conversationId: string, events: TurnEvent[]): void;
  close(): Promise<void>;
}

const DEFAULT_MODELS: StubModel[] = [
  { id: "meta:muse-spark", provider: "muse", displayName: "Muse Spark" },
];

/** A queue whose `next()` waits for the next `push`. */
class Mailbox<T> {
  private readonly items: T[] = [];
  private readonly waiters: ((item: T) => void)[] = [];

  push(item: T): void {
    const waiter = this.waiters.shift();
    if (waiter) waiter(item);
    else this.items.push(item);
  }

  next(): Promise<T> {
    const item = this.items.shift();
    if (item !== undefined) return Promise.resolve(item);
    return new Promise((resolve) => this.waiters.push(resolve));
  }
}

interface RunningTurn {
  steers: Mailbox<string>;
  cancel: () => void;
}

class StubState {
  readonly received: StubChatServer["received"] = {
    turns: [],
    steers: [],
    cancelTurns: [],
    cancelJobs: [],
    geometry: [],
  };
  private readonly seqs = new Map<string, bigint>();
  private readonly turnCounts = new Map<string, number>();
  readonly running = new Map<string, RunningTurn>();
  readonly watchers = new Map<string, Mailbox<TurnEvent[]>>();
  readonly watchOpened = new Map<string, () => void>();
  readonly watchOpen = new Map<string, Promise<void>>();

  constructor(readonly options: StubChatOptions) {
    for (const [conversationId, events] of Object.entries(options.history ?? {})) {
      this.seqs.set(conversationId, BigInt(events.length));
      this.turnCounts.set(conversationId, new Set(events.map((event) => event.turnId)).size);
    }
  }

  nextTurnId(conversationId: string): string {
    const count = (this.turnCounts.get(conversationId) ?? 0) + 1;
    this.turnCounts.set(conversationId, count);
    return `turn-${count}`;
  }

  stamp(event: TurnEvent, conversationId: string, turnId: string): TurnEvent {
    const seq = (this.seqs.get(conversationId) ?? 0n) + 1n;
    this.seqs.set(conversationId, seq);
    return { ...event, conversationId, turnId, seq };
  }

  watchOpenFor(conversationId: string): Promise<void> {
    let opened = this.watchOpen.get(conversationId);
    if (!opened) {
      opened = new Promise((resolve) => this.watchOpened.set(conversationId, resolve));
      this.watchOpen.set(conversationId, opened);
    }
    return opened;
  }

  watcherFor(conversationId: string): Mailbox<TurnEvent[]> {
    let mailbox = this.watchers.get(conversationId);
    if (!mailbox) {
      mailbox = new Mailbox();
      this.watchers.set(conversationId, mailbox);
    }
    return mailbox;
  }
}

function userMessage(text: string): TurnEvent {
  const value: UserMessage = { $typeName: "surmap.agent.v1.UserMessage", text };
  return {
    $typeName: "surmap.agent.v1.TurnEvent",
    conversationId: "",
    turnId: "",
    seq: 0n,
    event: { case: "userMessage", value },
  };
}

async function* finishOnly(): AsyncIterable<TurnEvent> {
  // A turn that ends at once; tests that care script their own.
}

function routerFor(state: StubState) {
  const router = createConnectRouter();
  router.service(ChatService, {
    async *streamTurn(request) {
      const turnRequest: TurnRequest = {
        conversationId: request.conversationId,
        text: request.text,
        modelId: request.modelId,
      };
      state.received.turns.push(turnRequest);
      const turnId = state.nextTurnId(request.conversationId);
      let cancel = () => {};
      const cancelled = new Promise<void>((resolve) => {
        cancel = resolve;
      });
      const steers = new Mailbox<string>();
      state.running.set(request.conversationId, { steers, cancel });
      try {
        yield state.stamp(userMessage(request.text), request.conversationId, turnId);
        const script = state.options.turn ?? finishOnly;
        for await (const event of script({
          request: turnRequest,
          nextSteer: () => steers.next(),
          cancelled,
        })) {
          yield state.stamp(event, request.conversationId, turnId);
        }
      } finally {
        state.running.delete(request.conversationId);
      }
    },
    async *watchConversation(request, context) {
      const mailbox = state.watcherFor(request.conversationId);
      void state.watchOpenFor(request.conversationId);
      state.watchOpened.get(request.conversationId)?.();
      const closed = new Promise<null>((resolve) =>
        context.signal.addEventListener("abort", () => resolve(null)),
      );
      for (;;) {
        const events = await Promise.race([mailbox.next(), closed]);
        if (events === null) return;
        const turnId = state.nextTurnId(request.conversationId);
        for (const event of events) yield state.stamp(event, request.conversationId, turnId);
      }
    },
    steer(request) {
      state.received.steers.push({ conversationId: request.conversationId, text: request.text });
      const turn = state.running.get(request.conversationId);
      turn?.steers.push(request.text);
      return { accepted: turn !== undefined };
    },
    cancelTurn(request) {
      state.received.cancelTurns.push(request.conversationId);
      const turn = state.running.get(request.conversationId);
      turn?.cancel();
      return { cancelled: turn !== undefined };
    },
    listModels() {
      const models = state.options.models ?? DEFAULT_MODELS;
      return {
        models: models.map((model) => ({
          ...model,
          available: model.available ?? true,
          detail: model.detail ?? "",
        })),
        defaultModelId: state.options.defaultModelId ?? models[0]?.id ?? "",
      };
    },
    getConversation(request) {
      return {
        conversationId: request.conversationId,
        events: state.options.history?.[request.conversationId] ?? [],
      };
    },
  });
  router.service(AgentJobs, {
    cancelJob(request, context) {
      state.received.cancelJobs.push({
        conversationId: context.requestHeader.get(CONVERSATION_HEADER),
        jobId: request.jobId,
      });
      return { job: { jobId: request.jobId, tool: "", status: JobStatus.CANCELLED, detail: "" } };
    },
  });
  return new Map(router.handlers.map((handler) => [handler.requestPath, createFetchHandler(handler)]));
}

function allowCors(request: IncomingMessage, response: ServerResponse): void {
  response.setHeader("access-control-allow-origin", "*");
  response.setHeader("access-control-allow-methods", "GET, POST, OPTIONS");
  response.setHeader(
    "access-control-allow-headers",
    request.headers["access-control-request-headers"] ?? "*",
  );
  response.setHeader(
    "access-control-expose-headers",
    "connect-protocol-version, grpc-status, grpc-message",
  );
}

function headersOf(request: IncomingMessage): Headers {
  const headers = new Headers();
  for (const [name, value] of Object.entries(request.headers)) {
    if (typeof value === "string") headers.set(name, value);
    else if (Array.isArray(value)) headers.set(name, value.join(", "));
  }
  return headers;
}

/** Starts the stub on a free loopback port. */
export async function startStubChatServer(options: StubChatOptions = {}): Promise<StubChatServer> {
  const state = new StubState(options);
  const handlers = routerFor(state);

  const server = createServer((request, response) => {
    void serve(request, response).catch((error: unknown) => {
      response.destroy(error instanceof Error ? error : new Error(String(error)));
    });
  });

  async function serve(request: IncomingMessage, response: ServerResponse): Promise<void> {
    allowCors(request, response);
    if (request.method === "OPTIONS") {
      response.writeHead(204).end();
      return;
    }
    const url = new URL(request.url ?? "/", "http://127.0.0.1");
    const glb = options.glb?.[url.pathname];
    if (request.method === "GET" && glb) {
      state.received.geometry.push(url.pathname);
      response.writeHead(200, { "content-type": "model/gltf-binary" }).end(glb);
      return;
    }
    const handler = handlers.get(url.pathname);
    if (!handler) {
      response.writeHead(404).end();
      return;
    }
    const aborted = new AbortController();
    response.on("close", () => aborted.abort());
    const answer = await handler(
      new Request(url, {
        method: request.method,
        headers: headersOf(request),
        body: request.method === "POST" ? (Readable.toWeb(request) as ReadableStream<Uint8Array>) : null,
        duplex: "half",
        signal: aborted.signal,
      }),
    );
    response.writeHead(answer.status, Object.fromEntries(answer.headers));
    if (answer.body) {
      for await (const chunk of answer.body) response.write(chunk);
    }
    response.end();
  }

  await new Promise<void>((resolve) => server.listen(0, "127.0.0.1", resolve));
  const { port } = server.address() as AddressInfo;

  return {
    url: `http://127.0.0.1:${port}`,
    received: state.received,
    watching: (conversationId) => state.watchOpenFor(conversationId),
    pushWatchTurn: (conversationId, events) => state.watcherFor(conversationId).push(events),
    close: () =>
      new Promise<void>((resolve) => {
        server.closeAllConnections();
        server.close(() => resolve());
      }),
  };
}

/** A GLB of one POINTS primitive, the shape `get_object_geometry`'s `geometry_uri` serves. */
export function pointsGlb(points: [number, number, number][]): Uint8Array {
  const positions = new Float32Array(points.flat());
  const axis = (i: number) => points.map((point) => point[i] ?? 0);
  const json = JSON.stringify({
    asset: { version: "2.0" },
    scene: 0,
    scenes: [{ nodes: [0] }],
    nodes: [{ mesh: 0 }],
    meshes: [{ primitives: [{ attributes: { POSITION: 0 }, mode: 0 }] }],
    accessors: [
      {
        bufferView: 0,
        componentType: 5126,
        count: points.length,
        type: "VEC3",
        min: [0, 1, 2].map((i) => Math.min(...axis(i))),
        max: [0, 1, 2].map((i) => Math.max(...axis(i))),
      },
    ],
    bufferViews: [{ buffer: 0, byteOffset: 0, byteLength: positions.byteLength }],
    buffers: [{ byteLength: positions.byteLength }],
  });
  const jsonBytes = padTo4(new TextEncoder().encode(json), 0x20);
  const binBytes = padTo4(new Uint8Array(positions.buffer), 0x00);
  const total = 12 + 8 + jsonBytes.length + 8 + binBytes.length;
  const glb = new Uint8Array(total);
  const view = new DataView(glb.buffer);
  view.setUint32(0, 0x46546c67, true);
  view.setUint32(4, 2, true);
  view.setUint32(8, total, true);
  view.setUint32(12, jsonBytes.length, true);
  view.setUint32(16, 0x4e4f534a, true);
  glb.set(jsonBytes, 20);
  const binAt = 20 + jsonBytes.length;
  view.setUint32(binAt, binBytes.length, true);
  view.setUint32(binAt + 4, 0x004e4942, true);
  glb.set(binBytes, binAt + 8);
  return glb;
}

function padTo4(bytes: Uint8Array, fill: number): Uint8Array {
  const padded = new Uint8Array(Math.ceil(bytes.length / 4) * 4).fill(fill);
  padded.set(bytes);
  return padded;
}
