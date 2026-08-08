/**
 * Read-only STS inspection tools for Pi architect/reviewer subagents.
 *
 * These tools deliberately expose a tiny, auditable surface instead of
 * granting read-only agents arbitrary bash access.
 */

import { spawn } from "node:child_process";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import { Type } from "typebox";

const MAX_OUTPUT_BYTES = 2 * 1024 * 1024;

type RunResult = {
  code: number;
  stdout: string;
  stderr: string;
};

function runProcess(
  executable: string,
  args: string[],
  cwd: string,
  signal?: AbortSignal,
): Promise<RunResult> {
  return new Promise((resolve) => {
    const proc = spawn(executable, args, {
      cwd,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let outputBytes = 0;
    let truncated = false;

    const append = (target: "stdout" | "stderr", chunk: Buffer) => {
      if (outputBytes >= MAX_OUTPUT_BYTES) {
        truncated = true;
        return;
      }

      const remaining = MAX_OUTPUT_BYTES - outputBytes;
      const slice = chunk.subarray(0, remaining);
      outputBytes += slice.length;
      if (slice.length < chunk.length) truncated = true;

      if (target === "stdout") stdout += slice.toString();
      else stderr += slice.toString();
    };

    proc.stdout.on("data", (chunk: Buffer) => append("stdout", chunk));
    proc.stderr.on("data", (chunk: Buffer) => append("stderr", chunk));

    const abort = () => {
      proc.kill("SIGTERM");
      setTimeout(() => {
        if (!proc.killed) proc.kill("SIGKILL");
      }, 2000).unref();
    };

    if (signal) {
      if (signal.aborted) abort();
      else signal.addEventListener("abort", abort, { once: true });
    }

    proc.on("error", (error) => {
      resolve({ code: 1, stdout, stderr: `${stderr}\n${String(error)}`.trim() });
    });

    proc.on("close", (code) => {
      if (truncated) {
        stderr += "\n[output truncated by sts-tools]";
      }
      resolve({ code: code ?? 1, stdout, stderr });
    });
  });
}

const GitSubcommand = Type.Union([
  Type.Literal("status"),
  Type.Literal("diff"),
  Type.Literal("log"),
  Type.Literal("show"),
  Type.Literal("grep"),
  Type.Literal("blame"),
  Type.Literal("ls-files"),
  Type.Literal("check-ignore"),
  Type.Literal("rev-parse"),
]);

export default function stsTools(pi: ExtensionAPI) {
  pi.registerTool({
    name: "sts_git",
    label: "STS Git Inspect",
    description:
      "Run one allowlisted read-only git subcommand in the current sts_ai repository. " +
      "Allowed: status, diff, log, show, grep, blame, ls-files, check-ignore, rev-parse.",
    parameters: Type.Object({
      subcommand: GitSubcommand,
      args: Type.Optional(
        Type.Array(Type.String(), {
          maxItems: 32,
          description: "Arguments passed after the fixed read-only git subcommand.",
        }),
      ),
    }),

    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = [params.subcommand, ...(params.args ?? [])];
      const result = await runProcess("git", args, ctx.cwd, signal);

      const text = [result.stdout.trimEnd(), result.stderr.trimEnd()]
        .filter(Boolean)
        .join("\n");

      return {
        content: [{ type: "text", text: text || "(no output)" }],
        details: { argv: ["git", ...args], exitCode: result.code },
        isError: result.code !== 0,
      };
    },
  });

  pi.registerTool({
    name: "sts_inspect",
    label: "STS Artifact Inspect",
    description:
      "Run the repository's restricted read-only artifact inspector: " +
      "python3 -I tools/ai_inspect.py <args>. Use only for supported CSV/JSON inspection.",
    parameters: Type.Object({
      args: Type.Array(Type.String(), {
        maxItems: 32,
        description: "Arguments passed to tools/ai_inspect.py.",
      }),
    }),

    async execute(_toolCallId, params, signal, _onUpdate, ctx) {
      const args = ["-I", "tools/ai_inspect.py", ...params.args];
      const result = await runProcess("python3", args, ctx.cwd, signal);

      const text = [result.stdout.trimEnd(), result.stderr.trimEnd()]
        .filter(Boolean)
        .join("\n");

      return {
        content: [{ type: "text", text: text || "(no output)" }],
        details: { argv: ["python3", ...args], exitCode: result.code },
        isError: result.code !== 0,
      };
    },
  });
}
