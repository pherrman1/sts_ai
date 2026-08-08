/**
 * Lightweight read/search telemetry for Pi agent sessions.
 *
 * Hooks tool_call events to record metadata about reads, greps, finds, and
 * other repository-inspection tool calls. Writes per-session JSONL to
 * .ai/<sessionId>/context-reads.jsonl.
 *
 * Telemetry is diagnostic only. Agent execution must not fail because
 * telemetry cannot be written.
 *
 * Never records: hidden reasoning, API keys, full file contents, full
 * prompts, arbitrary environment variables, or private user data.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { isToolCallEventType } from "@earendil-works/pi-coding-agent";

const TOOLS_OF_INTEREST = new Set([
  "read",
  "grep",
  "find",
  "ls",
  "sts_git",
  "sts_inspect",
]);

/** Derive a stable telemetry directory from the session file path.
 *  Falls back to .ai/<cwdHash>-unknown-<ts> if no session file. */
function resolveTelemetryDir(cwd: string, sessionFile: string | undefined | null): string {
  if (sessionFile) {
    // Session file is e.g. /home/user/.pi/sessions/<id>.json
    const sessionId = path.basename(sessionFile, path.extname(sessionFile));
    return path.join(cwd, ".ai", sessionId);
  }
  // Ephemeral session without a backing file: use a timestamped dir.
  const hash = Math.abs(hashString(cwd)).toString(36).slice(0, 8);
  const ts = Date.now().toString(36);
  return path.join(cwd, ".ai", `${hash}-${ts}`);
}

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return h;
}

function relativePath(cwd: string, p: string): string {
  try {
    return path.relative(cwd, p);
  } catch {
    return p;
  }
}

interface TelemetryRecord {
  ts: string;
  agent?: string;
  model?: string;
  turn?: number;
  tool: string;
  path?: string;
  offset?: number;
  limit?: number;
  pattern?: string;
  ok: boolean;
  durationMs?: number;
}

let telemetryDir: string | null = null;
let turnCount = 0;

function ensureDir(dir: string): boolean {
  try {
    fs.mkdirSync(dir, { recursive: true });
    return true;
  } catch {
    return false;
  }
}

function appendRecord(record: TelemetryRecord): void {
  if (!telemetryDir) return;
  ensureDir(telemetryDir);
  const filePath = path.join(telemetryDir, "context-reads.jsonl");
  try {
    fs.appendFileSync(filePath, JSON.stringify(record) + "\n", { encoding: "utf-8", flag: "a" });
  } catch {
    // Telemetry write failure is non-fatal.
  }
}

export default function stsTelemetry(pi: ExtensionAPI) {
  pi.on("session_start", async (_event, ctx) => {
    const sessionFile = ctx.sessionManager.getSessionFile();
    telemetryDir = resolveTelemetryDir(ctx.cwd, sessionFile);
    if (telemetryDir) ensureDir(telemetryDir);
  });

  pi.on("turn_start", async () => {
    turnCount++;
  });

  pi.on("tool_call", async (event, ctx) => {
    if (!TOOLS_OF_INTEREST.has(event.toolName)) return undefined;

    const record: TelemetryRecord = {
      ts: new Date().toISOString(),
      tool: event.toolName,
      ok: true, // optimistic; updated on tool_execution_end
    };

    // Extract model if available from the session manager.
    try {
      record.model = ctx.model?.id;
    } catch {
      // ignore
    }
    record.turn = turnCount;

    if (isToolCallEventType("read", event)) {
      record.path = event.input.path ? relativePath(ctx.cwd, event.input.path as string) : undefined;
      record.offset = event.input.offset as number | undefined;
      record.limit = event.input.limit as number | undefined;
    } else if (event.toolName === "grep") {
      record.pattern = event.input.pattern as string | undefined;
      record.path = event.input.path ? relativePath(ctx.cwd, event.input.path as string) : undefined;
    } else if (event.toolName === "find") {
      record.pattern = event.input.pattern as string | undefined;
      record.path = event.input.path ? relativePath(ctx.cwd, event.input.path as string) : undefined;
    } else if (event.toolName === "ls") {
      record.path = event.input.path ? relativePath(ctx.cwd, event.input.path as string) : undefined;
    } else if (event.toolName === "sts_git") {
      record.pattern = event.input.subcommand as string | undefined;
    } else if (event.toolName === "sts_inspect") {
      const args = event.input.args as string[] | undefined;
      record.pattern = args?.join(" ");
    }

    // We can't get duration from the tool_call event alone, so we write
    // optimistically here. A tool_execution_end handler could update ok.
    // For simplicity and reliability, we write on tool_call.
    appendRecord(record);

    return undefined; // never block
  });
}
