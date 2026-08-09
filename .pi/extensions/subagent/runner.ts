/**
 * StS Subagent Runner - Lifecycle-hardened child Pi process execution
 *
 * Spawns a `pi --mode json` child process with guaranteed bounded Promise
 * settlement. Never leaves the caller waiting forever.
 *
 * Shared by the `subagent` tool and `/sts-cycle`.
 *
 * Lifecycle guarantees (STS-SUBAGENT-LIFECYCLE-GUARD):
 *   - agent_end → short grace period → SIGTERM → SIGKILL
 *   - Hard wall-clock timeout defense in depth
 *   - AbortSignal integration
 *   - Bounded output capture
 */

import { spawn } from "node:child_process";

// ---------------------------------------------------------------------------
// Lifecycle timing constants
// ---------------------------------------------------------------------------

/** Grace period after agent_end before forcing child termination. */
export const AGENT_END_CLOSE_GRACE_MS = 5_000;

/** Grace period after SIGTERM before SIGKILL. */
export const CHILD_TERMINATION_GRACE_MS = 5_000;

/** Absolute ceiling for any subagent invocation. */
export const SUBAGENT_HARD_TIMEOUT_MS = 30 * 60 * 1_000;

/** Maximum stdout+stderr captured per process. */
const MAX_OUTPUT = 1 * 1024 * 1024;

// ---------------------------------------------------------------------------
// Types
// ---------------------------------------------------------------------------

export interface RunnerEvent {
  type: string;
  [key: string]: unknown;
}

export interface CompletedMessage {
  role: "assistant" | "user" | "toolResult";
  content: Array<{ type: string; text?: string; [key: string]: unknown }>;
  model?: string;
  stopReason?: string;
  errorMessage?: string;
  usage?: {
    input?: number;
    output?: number;
    cacheRead?: number;
    cacheWrite?: number;
    totalTokens?: number;
    cost?: { total?: number; [key: string]: unknown };
  };
}

export interface RunnerResult {
  /** Exit code or forced code. 0 on clean completion. */
  exitCode: number;
  /** All parsed JSONL events. */
  events: RunnerEvent[];
  /** All completed assistant/toolResult messages. */
  messages: CompletedMessage[];
  /** Raw stderr captured (truncated). */
  stderr: string;
  /** Whether the child was force-terminated. */
  wasTerminated: boolean;
  /** Whether the hard timeout fired. */
  wasTimedOut: boolean;
}

export interface RunnerOptions {
  /** Working directory for the child process. */
  cwd: string;
  /** Pi CLI arguments (NOT including --mode json -p --no-session). */
  args: string[];
  /** AbortSignal for external cancellation. */
  signal?: AbortSignal;
  /** Callback for each parsed event line, fired BEFORE internal processing. */
  onEvent?: (event: RunnerEvent) => void;
}

// ---------------------------------------------------------------------------
// Implementation
// ---------------------------------------------------------------------------

/**
 * Spawn a Pi child process in JSON mode with lifecycle hardening.
 *
 * The returned Promise is GUARANTEED to settle. A child that emits
 * `agent_end` but never closes stdio will be SIGTERMed after a short
 * grace period, then SIGKILLed. A child that never reaches `agent_end`
 * will be killed by the hard timeout.
 *
 * The onEvent callback fires BEFORE internal processing, so callers
 * can drive live activity updates without duplicating lifecycle logic.
 */
export async function runPiChild(options: RunnerOptions): Promise<RunnerResult> {
  const { cwd, args, signal, onEvent } = options;

  const result: RunnerResult = {
    exitCode: -1,
    events: [],
    messages: [],
    stderr: "",
    wasTerminated: false,
    wasTimedOut: false,
  };

  const allArgs = ["--mode", "json", "-p", "--no-session", ...args];

  const exitCode = await new Promise<number>((resolve) => {
    const proc = spawn("pi", allArgs, {
      cwd,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let buffer = "";
    let settled = false;
    let forcedExitCode: number | null = null;
    let agentEndTimer: ReturnType<typeof setTimeout> | null = null;
    let terminationTimer: ReturnType<typeof setTimeout> | null = null;
    let hardTimeoutTimer: ReturnType<typeof setTimeout> | null = null;
    let abortHandler: (() => void) | null = null;

    const processStillRunning = () =>
      proc.exitCode === null && proc.signalCode === null;

    const clearTimer = (timer: ReturnType<typeof setTimeout> | null) => {
      if (timer !== null) clearTimeout(timer);
    };

    const cleanupLifecycle = () => {
      clearTimer(agentEndTimer);
      clearTimer(terminationTimer);
      clearTimer(hardTimeoutTimer);
      agentEndTimer = null;
      terminationTimer = null;
      hardTimeoutTimer = null;
      if (signal && abortHandler) {
        signal.removeEventListener("abort", abortHandler);
        abortHandler = null;
      }
    };

    const processLine = (line: string) => {
      if (!line.trim()) return;
      let event: RunnerEvent;
      try {
        event = JSON.parse(line);
      } catch {
        return;
      }

      // Fire caller callback FIRST so live activity tracking happens
      // before internal processing.
      if (onEvent) {
        try { onEvent(event); } catch { /* ignore callback errors */ }
      }

      result.events.push(event);

      if (event.type === "agent_end") {
        // Pi has declared the agent complete. Give the child a short
        // grace period to close stdio cleanly. If it doesn't, force
        // termination and settle from the already-captured output.
        clearTimer(agentEndTimer);
        agentEndTimer = setTimeout(() => {
          if (settled) return;

          const hasMessages = result.messages.length > 0;
          forcedExitCode = hasMessages ? 0 : 1;

          if (!processStillRunning()) {
            finish(forcedExitCode);
            return;
          }

          result.wasTerminated = true;
          proc.kill("SIGTERM");
          terminationTimer = setTimeout(() => {
            if (settled) return;
            if (processStillRunning()) proc.kill("SIGKILL");
            finish(forcedExitCode ?? 1);
          }, CHILD_TERMINATION_GRACE_MS);
        }, AGENT_END_CLOSE_GRACE_MS);
        return;
      }

      if (event.type === "message_end" && event.message) {
        result.messages.push(event.message as CompletedMessage);
      }

      if (event.type === "tool_result_end" && event.message) {
        result.messages.push(event.message as CompletedMessage);
      }
    };

    const flushBufferedLine = () => {
      if (!buffer.trim()) return;
      const pending = buffer;
      buffer = "";
      processLine(pending);
    };

    const finish = (code: number) => {
      if (settled) return;
      settled = true;
      flushBufferedLine();
      cleanupLifecycle();
      resolve(code);
    };

    const terminateAndFinish = (code: number) => {
      if (settled) return;
      forcedExitCode = code;
      result.wasTerminated = true;

      if (!processStillRunning()) {
        finish(code);
        return;
      }

      proc.kill("SIGTERM");
      clearTimer(terminationTimer);
      terminationTimer = setTimeout(() => {
        if (settled) return;
        if (processStillRunning()) proc.kill("SIGKILL");
        finish(code);
      }, CHILD_TERMINATION_GRACE_MS);
    };

    let outputBytes = 0;
    proc.stdout.on("data", (data: Buffer) => {
      if (outputBytes >= MAX_OUTPUT) return;
      const chunk = data.toString();
      outputBytes += Buffer.byteLength(chunk, "utf8");
      buffer += chunk;
      const lines = buffer.split("\n");
      buffer = lines.pop() || "";
      for (const line of lines) processLine(line);
    });

    proc.stderr.on("data", (data: Buffer) => {
      const chunk = data.toString();
      if (result.stderr.length < MAX_OUTPUT) {
        result.stderr += chunk.substring(0, MAX_OUTPUT - result.stderr.length);
      }
    });

    proc.on("close", (code) => {
      finish(forcedExitCode ?? code ?? 0);
    });

    proc.on("error", (error) => {
      result.stderr += `\nProcess error: ${error.message}`;
      finish(1);
    });

    // Defense in depth: a child that never reaches agent_end cannot
    // keep the parent waiting indefinitely.
    hardTimeoutTimer = setTimeout(() => {
      result.wasTimedOut = true;
      terminateAndFinish(1);
    }, SUBAGENT_HARD_TIMEOUT_MS);

    if (signal) {
      abortHandler = () => {
        terminateAndFinish(1);
      };
      if (signal.aborted) abortHandler();
      else signal.addEventListener("abort", abortHandler, { once: true });
    }
  });

  result.exitCode = exitCode;
  return result;
}

/**
 * Extract the final assistant text from runner events.
 */
export function finalAssistantText(events: RunnerEvent[]): string {
  for (let i = events.length - 1; i >= 0; i--) {
    const event = events[i];
    if (event.type !== "message_end") continue;
    const message = event.message as CompletedMessage | undefined;
    if (!message || message.role !== "assistant") continue;
    const textParts = message.content
      .filter((part) => part.type === "text" && typeof part.text === "string")
      .map((part) => part.text!)
      .join("\n");
    if (textParts) return textParts.trim() + "\n";
  }
  return "";
}

/**
 * Accumulate cost entries from runner events.
 */
export function costEntriesFromEvents(
  agent: string,
  events: RunnerEvent[],
): Array<{
  agent: string;
  model: string;
  cost: number;
  tokens_input: number;
  tokens_output: number;
  tokens_reasoning: number;
  tokens_cache_read: number;
  tokens_cache_write: number;
}> {
  const totals = { input: 0, output: 0, cacheRead: 0, cacheWrite: 0 };
  let reasoning = 0;
  let totalCost = 0;
  let model = "";

  for (const event of events) {
    if (event.type !== "message_end") continue;
    const message = event.message as CompletedMessage | undefined;
    if (!message || message.role !== "assistant") continue;
    if (message.usage) {
      totals.input += message.usage.input || 0;
      totals.output += message.usage.output || 0;
      totals.cacheRead += message.usage.cacheRead || 0;
      totals.cacheWrite += message.usage.cacheWrite || 0;
      reasoning += (message.usage as any).reasoning || 0;
      if (message.usage.cost?.total) totalCost += message.usage.cost.total;
    }
    if (message.model) model = message.model;
  }

  if (model || totalCost || Object.values(totals).some((v) => v > 0)) {
    return [
      {
        agent,
        model,
        cost: totalCost,
        tokens_input: totals.input,
        tokens_output: totals.output,
        tokens_reasoning: reasoning,
        tokens_cache_read: totals.cacheRead,
        tokens_cache_write: totals.cacheWrite,
      },
    ];
  }
  return [];
}

/**
 * Parse a Pi final response, handling fenced JSON and trailing JSON.
 */
export function parseJsonResponse(text: string, source: string): Record<string, unknown> {
  const clean = text.trim();

  // Fast path
  try {
    const data = JSON.parse(clean);
    if (data && typeof data === "object" && !Array.isArray(data)) return data;
  } catch { /* continue */ }

  // Fenced code block
  const fenced = clean.match(/```(?:json)?\s*(\{[\s\S]*?\})\s*```/);
  if (fenced) {
    try {
      const data = JSON.parse(fenced[1]);
      if (data && typeof data === "object" && !Array.isArray(data)) return data;
    } catch { /* continue */ }
  }

  // Trailing JSON object scan
  const lines = clean.split("\n");
  for (let i = lines.length - 1; i >= 0; i--) {
    const line = lines[i].trim();
    if (!line.startsWith("{")) continue;
    const candidate = lines.slice(i).join("\n").trim();
    try {
      const data = JSON.parse(candidate);
      if (data && typeof data === "object" && !Array.isArray(data)) return data;
    } catch { /* continue */ }
  }

  throw new Error(
    `${source} returned no parseable final JSON object.\nRaw response:\n${clean.substring(0, 500)}`,
  );
}
