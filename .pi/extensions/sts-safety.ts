/**
 * Defense-in-depth safety policy for interactive Pi use in sts_ai.
 *
 * AUTHORITATIVE SOURCE:
 * - MAX_AUTOMATED_SEEDS = 128 and seed-argument maps are imported from
 *   .pi/extensions/sts-cycle/policy.ts (the single authoritative definition).
 * - The Pi policy layer is the target authority for deterministic safety
 *   rules. tools/ai_cycle.py is a legacy orchestrator during migration.
 *
 * This hook blocks obviously unsafe interactive tool calls:
 * - destructive git commands
 * - sudo
 * - recursive deletion
 * - protected control-plane files
 * - oversized seed sweeps (>128)
 */

import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";
import {
  MAX_AUTOMATED_SEEDS,
  KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX,
  KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX,
} from "./sts-cycle/policy.ts";

const PROTECTED_PATHS = [
  "opencode.json",
  ".opencode/prompts/architect.md",
  ".opencode/prompts/implementer.md",
  ".opencode/prompts/reviewer.md",
  ".opencode/prompts/reviewer-escalation.md",
  "tools/ai_cycle.py",
  "tools/ai_inspect.py",
  "tools/test_ai_cycle.py",

  // Pi control plane: agents should not rewrite their harness while
  // doing ordinary STS implementation work. The sts-cycle extension itself
  // may be modified during migration but is protected during ordinary tasks.
  ".pi/agents/",
  ".pi/extensions/sts-safety.ts",
  ".pi/extensions/sts-tools.ts",
  ".pi/extensions/subagent/agents.ts",
  ".pi/extensions/subagent/index.ts",
  ".pi/extensions/subagent/runner.ts",
  ".pi/extensions/sts-cycle/policy.ts",
  ".pi/extensions/sts-cycle/index.ts",
  ".pi/prompts/",
];

const DANGEROUS_BASH_PATTERNS: Array<[RegExp, string]> = [
  [/\bgit\s+commit\b/i, "git commit is controlled by the human/orchestrator"],
  [/\bgit\s+push\b/i, "git push is controlled by the human/orchestrator"],
  [/\bgit\s+clean\b/i, "git clean can destroy local experiment data"],
  [/\bgit\s+reset\b/i, "git reset is forbidden for automated implementation"],
  [/\bgit\s+restore\b/i, "git restore can erase user changes"],
  [/\bgit\s+checkout\b/i, "git checkout can erase/switch working-tree state"],
  [/\brm\s+(-[A-Za-z]*r[A-Za-z]*f|-rf|-fr|--recursive)\b/i, "recursive deletion is forbidden"],
  [/\bsudo\b/i, "sudo is forbidden"],
];

function normalizeForCompare(p: string, cwd: string): string {
  const absolute = path.isAbsolute(p) ? path.normalize(p) : path.resolve(cwd, p);
  return path.relative(cwd, absolute).split(path.sep).join("/");
}

function isProtectedPath(p: string, cwd: string): boolean {
  const relative = normalizeForCompare(p, cwd);
  return PROTECTED_PATHS.some((protectedPath) => {
    if (protectedPath.endsWith("/")) {
      const dir = protectedPath.slice(0, -1);
      return relative === dir || relative.startsWith(dir + "/");
    }
    return relative === protectedPath;
  });
}

function splitCommand(command: string): string[] {
  const result: string[] = [];
  let current = "";
  let quote: "'" | '"' | null = null;
  let escaped = false;

  for (const ch of command) {
    if (escaped) { current += ch; escaped = false; continue; }
    if (ch === "\\" && quote !== "'") { escaped = true; continue; }
    if (quote) { if (ch === quote) quote = null; else current += ch; continue; }
    if (ch === "'" || ch === '"') { quote = ch; continue; }
    if (/\s/.test(ch)) { if (current) { result.push(current); current = ""; } continue; }
    current += ch;
  }
  if (current) result.push(current);
  return result;
}

function basename(token: string): string {
  return token.replaceAll("\\", "/").split("/").pop() ?? token;
}

function oversizedSeedSweep(command: string): string | null {
  const tokens = splitCommand(command);

  for (let exeIndex = 0; exeIndex < tokens.length; exeIndex++) {
    const exe = basename(tokens[exeIndex]);

    if (exe === "one_combat") {
      const mode = tokens[exeIndex + 1];
      const relativeSeedIndex = KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX[mode];
      if (relativeSeedIndex === undefined) continue;
      const seedToken = tokens[exeIndex + relativeSeedIndex];
      const seeds = Number(seedToken);
      if (Number.isInteger(seeds) && seeds > MAX_AUTOMATED_SEEDS) {
        return exe + " " + mode + " requests " + seeds + " seeds; automated maximum is " + MAX_AUTOMATED_SEEDS;
      }
    }

    if (exe === "python" || exe === "python3") {
      for (let scriptIndex = exeIndex + 1; scriptIndex < tokens.length; scriptIndex++) {
        const script = basename(tokens[scriptIndex]);
        const relativeSeedIndex = KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX[script];
        if (relativeSeedIndex === undefined) continue;
        const seedToken = tokens[scriptIndex + relativeSeedIndex];
        const seeds = Number(seedToken);
        if (Number.isInteger(seeds) && seeds > MAX_AUTOMATED_SEEDS) {
          return script + " requests " + seeds + " seeds; automated maximum is " + MAX_AUTOMATED_SEEDS;
        }
      }
    }
  }

  return null;
}

export default function stsSafety(pi: ExtensionAPI) {
  pi.on("tool_call", async (event, ctx) => {
    if (event.toolName === "write" || event.toolName === "edit") {
      const target = event.input.path as string | undefined;
      if (target && isProtectedPath(target, ctx.cwd)) {
        const reason = "Protected STS workflow path: " + normalizeForCompare(target, ctx.cwd);
        if (ctx.hasUI) ctx.ui.notify(reason, "warning");
        return { block: true, reason };
      }
      return undefined;
    }

    if (event.toolName !== "bash") return undefined;

    const command = String(event.input.command ?? "");

    for (const [pattern, explanation] of DANGEROUS_BASH_PATTERNS) {
      if (pattern.test(command)) {
        const reason = "Blocked STS command: " + explanation;
        if (ctx.hasUI) ctx.ui.notify(reason, "warning");
        return { block: true, reason };
      }
    }

    const seedProblem = oversizedSeedSweep(command);
    if (seedProblem) {
      if (ctx.hasUI) ctx.ui.notify(seedProblem, "warning");
      return { block: true, reason: seedProblem };
    }

    return undefined;
  });
}
