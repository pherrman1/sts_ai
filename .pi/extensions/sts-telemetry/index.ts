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

const PROCESS_STARTED_AT_MS = Date.now();
const PROCESS_MARKER_MAX_AGE_MS = 24 * 60 * 60 * 1000;

interface ProcessMarker {
  session: string;
  agent?: string;
  agent_instance: string;
  invocation_id: string;
  pid: number;
  parent_pid: number;
  cwd: string;
  created_at: string;
}

interface SessionIdentity {
  session: string;
  parent_session?: string;
  invocation_id: string;
  agent?: string;
  agent_instance: string;
  process_id: number;
  parent_process_id: number;
}

interface TelemetryRecord extends SessionIdentity {
  ts: string;
  model?: string;
  turn?: number;
  tool: string;
  path?: string;
  offset?: number;
  limit?: number;
  start_line?: number;
  end_line?: number;
  requested_lines?: number;
  pattern?: string;
  ok: boolean;
  durationMs?: number;
}

let telemetryDir: string | null = null;
let identity: SessionIdentity | null = null;
let turnCount = 0;
let markerPath: string | null = null;

function hashString(s: string): number {
  let h = 0;
  for (let i = 0; i < s.length; i++) {
    h = (Math.imul(31, h) + s.charCodeAt(i)) | 0;
  }
  return h;
}

function ensureDir(dir: string): boolean {
  try {
    fs.mkdirSync(dir, { recursive: true });
    return true;
  } catch {
    return false;
  }
}

function sessionIdFromFile(sessionFile: string | undefined | null): string | null {
  if (!sessionFile) return null;
  return path.basename(sessionFile, path.extname(sessionFile));
}

function inferAgentFromArgv(): string | undefined {
  // Explicit launcher metadata wins.
  const explicit = process.env.STS_PI_AGENT_NAME || process.env.PI_AGENT_NAME;
  if (explicit?.trim()) return explicit.trim();

  // The reference subagent extension uses:
  //   --append-system-prompt /tmp/.../prompt-<agent>.md
  // ai_cycle may also pass .pi/agents/<agent>.md directly.
  const idx = process.argv.indexOf("--append-system-prompt");
  if (idx >= 0 && idx + 1 < process.argv.length) {
    const promptPath = process.argv[idx + 1];
    const base = path.basename(promptPath);

    const promptMatch = /^prompt-(.+)\.md$/i.exec(base);
    if (promptMatch?.[1]) return promptMatch[1];

    if (path.basename(path.dirname(promptPath)) === "agents") {
      const stem = path.basename(base, path.extname(base));
      if (stem) return stem;
    }
  }

  return undefined;
}

function makeEphemeralSessionId(cwd: string, agent: string | undefined): string {
  const cwdHash = Math.abs(hashString(cwd)).toString(36).slice(0, 8);
  const safeAgent = (agent || "pi").replace(/[^\w.-]+/g, "_");
  return `${cwdHash}-${safeAgent}-${process.pid}-${PROCESS_STARTED_AT_MS.toString(36)}`;
}

function processMarkerDir(cwd: string): string {
  return path.join(cwd, ".ai", ".pi-processes");
}

function processMarkerPath(cwd: string, pid: number): string {
  return path.join(processMarkerDir(cwd), `${pid}.json`);
}

function readProcessMarker(cwd: string, pid: number): ProcessMarker | null {
  if (!Number.isInteger(pid) || pid <= 0) return null;

  try {
    const raw = fs.readFileSync(processMarkerPath(cwd, pid), "utf-8");
    const marker = JSON.parse(raw) as Partial<ProcessMarker>;

    if (
      typeof marker.session !== "string" ||
      typeof marker.agent_instance !== "string" ||
      typeof marker.invocation_id !== "string" ||
      typeof marker.cwd !== "string" ||
      typeof marker.created_at !== "string"
    ) {
      return null;
    }

    // Avoid linking to a stale marker if the OS has reused a PID.
    const createdAtMs = Date.parse(marker.created_at);
    if (
      !Number.isFinite(createdAtMs) ||
      Date.now() - createdAtMs > PROCESS_MARKER_MAX_AGE_MS
    ) {
      return null;
    }

    if (path.resolve(marker.cwd) !== path.resolve(cwd)) return null;

    return marker as ProcessMarker;
  } catch {
    return null;
  }
}

function writeProcessMarker(
  cwd: string,
  currentIdentity: SessionIdentity,
): string | null {
  const dir = processMarkerDir(cwd);
  if (!ensureDir(dir)) return null;

  const target = processMarkerPath(cwd, process.pid);
  const marker: ProcessMarker = {
    session: currentIdentity.session,
    agent: currentIdentity.agent,
    agent_instance: currentIdentity.agent_instance,
    invocation_id: currentIdentity.invocation_id,
    pid: process.pid,
    parent_pid: process.ppid,
    cwd: path.resolve(cwd),
    created_at: new Date().toISOString(),
  };

  try {
    fs.writeFileSync(target, JSON.stringify(marker) + "\n", {
      encoding: "utf-8",
      mode: 0o600,
      flag: "w",
    });
    return target;
  } catch {
    return null;
  }
}

function removeOwnProcessMarker(): void {
  if (!markerPath) return;
  try {
    fs.unlinkSync(markerPath);
  } catch {
    // Telemetry cleanup failure is non-fatal.
  }
  markerPath = null;
}

function resolveIdentity(
  cwd: string,
  sessionFile: string | undefined | null,
): SessionIdentity {
  const agent = inferAgentFromArgv();

  const explicitSession =
    process.env.STS_PI_SESSION_ID?.trim() ||
    process.env.PI_SESSION_ID?.trim() ||
    sessionIdFromFile(sessionFile);

  const session = explicitSession || makeEphemeralSessionId(cwd, agent);

  // Environment metadata is preferred if a launcher explicitly supplies it.
  // Otherwise a child Pi process can discover its parent Pi session through
  // the PID marker written by this same extension in the parent process.
  const parentMarker = readProcessMarker(cwd, process.ppid);
  const parentSession =
    process.env.STS_PI_PARENT_SESSION?.trim() ||
    process.env.PI_PARENT_SESSION?.trim() ||
    parentMarker?.session;

  const invocationId =
    process.env.STS_PI_INVOCATION_ID?.trim() ||
    process.env.PI_INVOCATION_ID?.trim() ||
    session;

  const agentInstance =
    process.env.STS_PI_AGENT_INSTANCE?.trim() ||
    process.env.PI_AGENT_INSTANCE?.trim() ||
    `${agent || "pi"}-${process.pid}`;

  return {
    session,
    parent_session: parentSession,
    invocation_id: invocationId,
    agent,
    agent_instance: agentInstance,
    process_id: process.pid,
    parent_process_id: process.ppid,
  };
}

function resolveTelemetryDir(cwd: string, currentIdentity: SessionIdentity): string {
  return path.join(cwd, ".ai", currentIdentity.session);
}

function repositoryRelativePath(cwd: string, p: string): string {
  try {
    const absolute = path.isAbsolute(p) ? p : path.resolve(cwd, p);
    const rel = path.relative(cwd, absolute);
    return rel || ".";
  } catch {
    return p;
  }
}

function appendRecord(record: TelemetryRecord): void {
  if (!telemetryDir) return;
  if (!ensureDir(telemetryDir)) return;

  const filePath = path.join(telemetryDir, "context-reads.jsonl");
  try {
    fs.appendFileSync(filePath, JSON.stringify(record) + "\n", {
      encoding: "utf-8",
      flag: "a",
    });
  } catch {
    // Telemetry write failure is non-fatal.
  }
}

function applyReadRangeMetadata(
  record: TelemetryRecord,
  offset: number | undefined,
  limit: number | undefined,
): void {
  if (Number.isFinite(offset)) record.offset = offset;
  if (Number.isFinite(limit)) record.limit = limit;

  // Pi's read tool uses 1-based offsets. A limit without an offset starts
  // at line 1.
  const startLine = Number.isFinite(offset)
    ? Math.max(1, Math.trunc(offset as number))
    : 1;

  if (Number.isFinite(offset) || Number.isFinite(limit)) {
    record.start_line = startLine;
  }

  if (Number.isFinite(limit) && (limit as number) > 0) {
    const requestedLines = Math.trunc(limit as number);
    record.requested_lines = requestedLines;
    record.end_line = startLine + requestedLines - 1;
  }
}

export default function stsTelemetry(pi: ExtensionAPI) {
  pi.on("session_start", async (_event, ctx) => {
    turnCount = 0;

    const sessionFile = ctx.sessionManager.getSessionFile();
    identity = resolveIdentity(ctx.cwd, sessionFile);
    telemetryDir = resolveTelemetryDir(ctx.cwd, identity);

    ensureDir(telemetryDir);

    // Publish only non-sensitive identity metadata so direct child Pi
    // processes can attribute their telemetry to this parent session.
    markerPath = writeProcessMarker(ctx.cwd, identity);
  });

  pi.on("session_shutdown", async () => {
    removeOwnProcessMarker();
  });

  pi.on("turn_start", async () => {
    turnCount++;
  });

  pi.on("tool_call", async (event, ctx) => {
    if (!TOOLS_OF_INTEREST.has(event.toolName)) return undefined;

    if (!identity) {
      // Defensive fallback for unusual extension/event ordering.
      const sessionFile = ctx.sessionManager.getSessionFile();
      identity = resolveIdentity(ctx.cwd, sessionFile);
      telemetryDir = resolveTelemetryDir(ctx.cwd, identity);
      if (!markerPath) markerPath = writeProcessMarker(ctx.cwd, identity);
    }

    const currentIdentity = identity;
    const record: TelemetryRecord = {
      ts: new Date().toISOString(),
      ...currentIdentity,
      tool: event.toolName,
      ok: true, // tool_call is pre-execution; current telemetry is optimistic.
    };

    try {
      record.model = ctx.model?.id;
    } catch {
      // Model metadata is optional.
    }

    record.turn = turnCount;

    if (isToolCallEventType("read", event)) {
      record.path = event.input.path
        ? repositoryRelativePath(ctx.cwd, event.input.path as string)
        : undefined;

      applyReadRangeMetadata(
        record,
        event.input.offset as number | undefined,
        event.input.limit as number | undefined,
      );
    } else if (event.toolName === "grep") {
      record.pattern = event.input.pattern as string | undefined;
      record.path = event.input.path
        ? repositoryRelativePath(ctx.cwd, event.input.path as string)
        : undefined;
    } else if (event.toolName === "find") {
      record.pattern = event.input.pattern as string | undefined;
      record.path = event.input.path
        ? repositoryRelativePath(ctx.cwd, event.input.path as string)
        : undefined;
    } else if (event.toolName === "ls") {
      record.path = event.input.path
        ? repositoryRelativePath(ctx.cwd, event.input.path as string)
        : undefined;
    } else if (event.toolName === "sts_git") {
      record.pattern = event.input.subcommand as string | undefined;
    } else if (event.toolName === "sts_inspect") {
      const args = event.input.args as string[] | undefined;
      record.pattern = args?.join(" ");
    }

    appendRecord(record);
    return undefined; // telemetry must never block a tool
  });
}