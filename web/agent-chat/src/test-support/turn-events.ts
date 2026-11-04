import { create } from "@bufbuild/protobuf";
import {
  ToolCallFinished_Status,
  TurnEventSchema,
  TurnFinished_Reason,
  type TurnEvent,
} from "@/gen/surmap/agent/v1/chat_pb";
import {
  ExecutionMode,
  ExecutionPolicySchema,
  JobHandleSchema,
  JobStatus,
  OnTimeout,
  type ExecutionPolicy,
  type JobHandle,
} from "@/gen/surmap/agent/v1/execution_pb";
import type { JobState } from "@/view-model/jobs";
import type { PolicyView } from "@/view-model/transcript";

/** The policy most survey tools declare: block 30 s, then keep running as a job. */
export const SYNC_30_THEN_DETACH: PolicyView = { mode: "SYNC", timeoutS: 30, onTimeout: "DETACH" };
/** A quick read that fails rather than detaching. */
export const SYNC_10_THEN_FAIL: PolicyView = { mode: "SYNC", timeoutS: 10, onTimeout: "FAIL" };
/** A call handed to a job at once. */
export const ASYNC_JOB: PolicyView = { mode: "ASYNC", timeoutS: 0, onTimeout: "DETACH" };

export type FinishReason = "stop" | "length" | "cancelled" | "error";

const JOB_STATUS: Record<JobState, JobStatus> = {
  running: JobStatus.RUNNING,
  succeeded: JobStatus.SUCCEEDED,
  failed: JobStatus.FAILED,
  cancelled: JobStatus.CANCELLED,
};

const FINISH_REASON: Record<FinishReason, TurnFinished_Reason> = {
  stop: TurnFinished_Reason.STOP,
  length: TurnFinished_Reason.LENGTH,
  cancelled: TurnFinished_Reason.CANCELLED,
  error: TurnFinished_Reason.ERROR,
};

export function executionPolicy(policy: PolicyView): ExecutionPolicy {
  return create(ExecutionPolicySchema, {
    mode: policy.mode === "SYNC" ? ExecutionMode.SYNC : ExecutionMode.ASYNC,
    timeoutS: policy.timeoutS,
    onTimeout: policy.onTimeout === "FAIL" ? OnTimeout.FAIL : OnTimeout.DETACH,
  });
}

export function jobHandle(job: {
  jobId: string;
  tool: string;
  status?: JobState;
  detail?: string;
}): JobHandle {
  return create(JobHandleSchema, {
    jobId: job.jobId,
    tool: job.tool,
    status: JOB_STATUS[job.status ?? "running"],
    detail: job.detail ?? "",
  });
}

type EventBody = TurnEvent["event"];

/**
 * Builds a conversation's `TurnEvent`s the way the server streams them: one `seq` per event from
 * 1 with no gaps, each event in the turn last named with `inTurn`.
 */
export class ConversationScript {
  private readonly events: TurnEvent[] = [];
  private turnId = "turn-1";
  private seq: bigint;

  constructor(
    readonly conversationId: string = "conv-1",
    startSeq: bigint = 1n,
  ) {
    this.seq = startSeq;
  }

  inTurn(turnId: string): this {
    this.turnId = turnId;
    return this;
  }

  userMessage(text: string): this {
    return this.push({ case: "userMessage", value: { $typeName: "surmap.agent.v1.UserMessage", text } });
  }

  textDelta(text: string): this {
    return this.push({ case: "textDelta", value: text });
  }

  toolStarted(
    callId: string,
    tool: string,
    options: { argumentsJson?: string; policy?: PolicyView | null } = {},
  ): this {
    const policy = options.policy === undefined ? SYNC_30_THEN_DETACH : options.policy;
    return this.push({
      case: "toolCallStarted",
      value: {
        $typeName: "surmap.agent.v1.ToolCallStarted",
        callId,
        tool,
        argumentsJson: options.argumentsJson ?? "{}",
        execution: policy === null ? undefined : executionPolicy(policy),
      },
    });
  }

  toolSucceeded(
    callId: string,
    options: { resultJson?: string; image?: Uint8Array; mediaType?: string; job?: JobHandle } = {},
  ): this {
    return this.finished(callId, ToolCallFinished_Status.SUCCEEDED, options.resultJson ?? "{}", options);
  }

  toolFailed(callId: string, resultJson: string): this {
    return this.finished(callId, ToolCallFinished_Status.FAILED, resultJson, {});
  }

  toolDetached(callId: string, job: { jobId: string; tool: string }): this {
    return this.finished(callId, ToolCallFinished_Status.DETACHED, "{}", { job: jobHandle(job) });
  }

  toolCancelled(callId: string): this {
    return this.finished(callId, ToolCallFinished_Status.CANCELLED, "{}", {});
  }

  jobUpdate(job: { jobId: string; tool: string; status: JobState; detail?: string }): this {
    return this.push({ case: "jobUpdate", value: jobHandle(job) });
  }

  steerApplied(text: string, detachedCallIds: string[] = []): this {
    return this.push({
      case: "steerApplied",
      value: { $typeName: "surmap.agent.v1.SteerApplied", text, detachedCallIds },
    });
  }

  subagentMessage(subagentId: string, name: string, text: string): this {
    return this.push({
      case: "subagentMessage",
      value: { $typeName: "surmap.agent.v1.SubagentMessage", subagentId, name, text },
    });
  }

  turnFinished(reason: FinishReason = "stop"): this {
    return this.push({
      case: "turnFinished",
      value: { $typeName: "surmap.agent.v1.TurnFinished", reason: FINISH_REASON[reason] },
    });
  }

  error(message: string): this {
    return this.push({ case: "error", value: { $typeName: "surmap.agent.v1.TurnError", message } });
  }

  build(): TurnEvent[] {
    return [...this.events];
  }

  private finished(
    callId: string,
    status: ToolCallFinished_Status,
    resultJson: string,
    options: { image?: Uint8Array; mediaType?: string; job?: JobHandle },
  ): this {
    return this.push({
      case: "toolCallFinished",
      value: {
        $typeName: "surmap.agent.v1.ToolCallFinished",
        callId,
        status,
        resultJson,
        image: options.image,
        mediaType: options.mediaType,
        job: options.job,
      },
    });
  }

  private push(event: EventBody): this {
    this.events.push(
      create(TurnEventSchema, {
        conversationId: this.conversationId,
        turnId: this.turnId,
        seq: this.seq,
        event,
      }),
    );
    this.seq += 1n;
    return this;
  }
}

/** A new conversation script; events start at `seq` 1 unless `startSeq` says otherwise. */
export function aConversation(conversationId = "conv-1", startSeq = 1n): ConversationScript {
  return new ConversationScript(conversationId, startSeq);
}
