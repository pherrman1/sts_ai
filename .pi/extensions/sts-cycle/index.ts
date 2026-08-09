/**
 * /sts-cycle — Deterministic Pi-native agent orchestration state machine
 *
 * Replaces tools/ai_cycle.py with a native Pi command.
 *
 * States: PREFLIGHT → CLASSIFY → ARCHITECT → IMPLEMENT → VERIFY →
 *         REVIEW → (REPAIR|ESCALATE) → FINAL_VERIFY → ACCEPTED/REJECTED
 *
 * The parent model must NOT improvise the workflow sequence.
 * This extension decides transitions deterministically.
 */

import * as fs from "node:fs";
import * as os from "node:os";
import * as path from "node:path";
import type { ExtensionAPI } from "@earendil-works/pi-coding-agent";

import { classifyTask, createTrivialPlan, validatePlan, validateReview, shouldEscalate, confirmTrivialDiff } from "./policy.ts";
import { getChangedPathsStats, getHeadCommit, getStatusPorcelain, getDiff, snapshotState, candidateFingerprint } from "./git-state.ts";
import { runVerification } from "./verification.ts";
import {
  createSessionDir, ensureAiRoot,
  writeTask, writeState, loadState,
  writeClassification,
  writePlan, loadPlan, writePlanEli5,
  writeDiffPatch, writeGitSnapshot,
  writeVerification, writeReview, writeEscalation,
  writeCosts, summarizeCosts,
  writeEli5, composeFinalEli5,
} from "./artifacts.ts";
import { runPiChild, finalAssistantText, costEntriesFromEvents, parseJsonResponse } from "../subagent/runner.ts";
import type { RunnerEvent } from "../subagent/runner.ts";
import type {
  CycleState, CycleSessionState, TerminalState, FailureReason,
  ArchitecturePlan, ReviewResult, VerificationReport, CycleCostEntry,
} from "./types.ts";

// ============================================================================
// Agent configuration — loaded from .pi/agents/*.md frontmatter
// The frontmatter model: field is the SOLE source of truth.
// ============================================================================

interface AgentConfig {
  model: string;
  tools?: string;
  body: string;
}

interface MdFrontmatter {
  name?: string;
  description?: string;
  tools?: string;
  model?: string;
}

function parseFrontmatter(raw: string): { frontmatter: MdFrontmatter; body: string } {
  if (raw.startsWith("---")) {
    const end = raw.indexOf("\n---", 3);
    if (end !== -1) {
      const fmBlock = raw.substring(3, end);
      const frontmatter: MdFrontmatter = {};
      for (const line of fmBlock.split("\n")) {
        const colonIdx = line.indexOf(":");
        if (colonIdx > 0) {
          const key = line.substring(0, colonIdx).trim();
          const value = line.substring(colonIdx + 1).trim();
          if (key === "model" || key === "name" || key === "description" || key === "tools") {
            (frontmatter as any)[key] = value;
          }
        }
      }
      return { frontmatter, body: raw.substring(end + 4).trimStart() };
    }
  }
  return { frontmatter: {}, body: raw.trimStart() };
}

const PI_READONLY_TOOLS = "read,grep,find,ls,sts_git,sts_inspect";
const PI_READONLY_ROLES = new Set(["architect", "reviewer", "reviewer_escalation"]);

const ROLE_TO_AGENT_FILE: Record<string, string> = {
  architect: ".pi/agents/architect.md",
  implementer: ".pi/agents/implementer.md",
  reviewer: ".pi/agents/reviewer.md",
  reviewer_escalation: ".pi/agents/reviewer-pro.md",
};

let _agentConfigs: Map<string, AgentConfig> | null = null;

function loadAgentConfigs(cwd: string): Map<string, AgentConfig> {
  if (_agentConfigs) return _agentConfigs;
  _agentConfigs = new Map();
  for (const [role, relPath] of Object.entries(ROLE_TO_AGENT_FILE)) {
    try {
      const fullPath = path.join(cwd, relPath);
      const raw = fs.readFileSync(fullPath, "utf-8");
      const { frontmatter, body } = parseFrontmatter(raw);
      if (!frontmatter.model || !frontmatter.model.trim()) {
        throw new Error(
          `Agent config error: ${relPath} has no model field in frontmatter. ` +
          `Model must be declared in the agent markdown file.`
        );
      }
      if (!body.trim()) {
        throw new Error(`Agent config error: ${relPath} has no prompt body after frontmatter.`);
      }
      _agentConfigs.set(role, {
        model: frontmatter.model.trim(),
        tools: frontmatter.tools?.trim(),
        body: body.trim(),
      });
    } catch (e: any) {
      if (e.message.startsWith("Agent config error:")) throw e;
      throw new Error(
        `Agent config error: cannot load ${relPath} for role '${role}': ${e.message}`
      );
    }
  }
  return _agentConfigs;
}

function agentConfig(cwd: string, role: string): AgentConfig {
  const configs = loadAgentConfigs(cwd);
  const cfg = configs.get(role);
  if (!cfg) {
    throw new Error(
      `Agent config error: no agent definition for role '${role}'. ` +
      `Expected a markdown file with model frontmatter.`
    );
  }
  return cfg;
}

// ============================================================================
// Agent invocation
// ============================================================================

interface AgentResult {
  text: string;
  events: RunnerEvent[];
  costs: CycleCostEntry[];
}

async function invokeAgent(
  cwd: string,
  role: string,
  prompt: string,
  files: string[],
  signal?: AbortSignal,
): Promise<AgentResult> {
  const cfg = agentConfig(cwd, role);
  const model = cfg.model;


  const args: string[] = [
    "--model", model,
    "--extension", path.join(cwd, ".pi/extensions/sts-tools.ts"),
    "--extension", path.join(cwd, ".pi/extensions/sts-safety.ts"),
  ];

  if (PI_READONLY_ROLES.has(role)) {
    const toolAllowlist = cfg.tools || PI_READONLY_TOOLS;
    args.push("--tools", toolAllowlist);
  }

  // Write system prompt to temp file
  const tmpDir = fs.mkdtempSync(path.join(os.tmpdir(), "sts-cycle-prompt-"));
  const promptFile = path.join(tmpDir, "system.md");
  fs.writeFileSync(promptFile, cfg.body, "utf-8");
  args.push("--append-system-prompt", promptFile);

  // Attach files via @-syntax
  for (const f of files) {
    args.push(`@${f}`);
  }

  args.push(`Task: ${prompt}`);

  let events: RunnerEvent[] = [];

  try {
    const result = await runPiChild({
      cwd,
      args,
      signal,
      onEvent: (event) => { events.push(event); },
    });

    const text = finalAssistantText(result.events);
    const costs = costEntriesFromEvents(role, result.events);

    if (result.exitCode !== 0 && !result.wasTerminated) {
      throw new Error(
        `Pi agent '${role}' failed with exit code ${result.exitCode}.\n${result.stderr.substring(0, 2000)}`,
      );
    }

    const lastAssistant = result.messages
      .filter((m) => m.role === "assistant")
      .pop() as any;

    if (lastAssistant?.stopReason === "error" || lastAssistant?.stopReason === "aborted") {
      throw new Error(
        `Pi agent '${role}' stopped with ${lastAssistant.stopReason}. ${lastAssistant.errorMessage || ""}`,
      );
    }

    if (!text) {
      throw new Error(`Pi agent '${role}' produced no final assistant response.`);
    }

    return { text, events, costs };
  } finally {
    try { fs.unlinkSync(promptFile); } catch { /* ignore */ }
    try { fs.rmdirSync(tmpDir); } catch { /* ignore */ }
  }
}

// ============================================================================
// Prompt templates
// ============================================================================

const ARCHITECT_PROMPT = `
Analyze the attached user task for this repository.

Return ONLY the valid JSON architecture plan required by your architect
instructions.

Do not modify repository files.
`.trim();

const BASE_IMPLEMENT = "Implement the attached architecture plan for the attached user task.\n\nActually modify the repository. The orchestration program, not you, is authoritative for final verification and will execute the plan's verification commands independently after you finish.\n\nYou may run cheap focused checks yourself when useful for debugging, but do not run checks marked expensive and do not modify the architecture plan or its verification commands.\n\nDo not commit or push.\n\nNever run destructive repository operations or revert a file merely because it was already changed or looks unrelated. Leave such a file untouched and report it.";

const FINAL_BLOCK = "\n\nWrap only your final user-facing summary between these exact marker lines:\n\nFINAL_RESPONSE_BEGIN\n<final summary>\nFINAL_RESPONSE_END";

const IMPLEMENT_PROMPT = BASE_IMPLEMENT + FINAL_BLOCK;

const REVIEW_PROMPT = `
Review the current working-tree implementation against:
- the original user task
- the architecture plan
- the independent verification report

Inspect the actual repository state, git diff, affected code, callers,
consumers, tests, and maintained documentation yourself.

Do not modify files.

Return ONLY the valid JSON review object required by your reviewer
instructions.
`.trim();

// ============================================================================
// State machine
// ============================================================================

interface CycleContext {
  sessionDir: string;
  cwd: string;
  task: string;
  state: CycleSessionState;
  plan: ArchitecturePlan | null;
  costs: CycleCostEntry[];
  signal?: AbortSignal;
  onProgress?: (state: string, detail: string) => void;
}

async function runPreflight(ctx: CycleContext): Promise<CycleContext> {
  ctx.onProgress?.("PREFLIGHT", "Checking repository state...");

  const status = await getStatusPorcelain(ctx.cwd, true);
  if (status.trim()) {
    throw Object.assign(
      new Error(
        "Tracked working-tree changes already exist.\n\n" +
        "Commit or stash them before starting an AI cycle so that the " +
        "reviewer can attribute all tracked changes to this task.\n\n" +
        status,
      ),
      { failureReason: "FAILED_POLICY" as FailureReason },
    );
  }

  const head = await getHeadCommit(ctx.cwd);
  const fingerprint = await candidateFingerprint(ctx.cwd);

  ctx.state.baselineCommit = head;
  ctx.state.baselineFingerprint = fingerprint;
  ctx.state.startedAt = new Date().toISOString();

  writeState(ctx.sessionDir, ctx.state);
  await snapshotAndSave(ctx, "00-before");

  ctx.onProgress?.("PREFLIGHT", `Baseline: ${head.substring(0, 8)}`);
  return ctx;
}

async function snapshotAndSave(ctx: CycleContext, name: string): Promise<void> {
  const snap = await snapshotState(ctx.cwd);
  writeGitSnapshot(ctx.sessionDir, name, snap);
}

async function runClassify(ctx: CycleContext): Promise<CycleContext> {
  ctx.onProgress?.("CLASSIFY", "Classifying task...");

  const { isCandidate, reasons } = classifyTask(ctx.task);
  const taskClass = isCandidate ? "TRIVIAL_CANDIDATE" : "NORMAL";

  ctx.state.taskClass = taskClass;
  writeClassification(ctx.sessionDir, { class: taskClass, reasons });
  writeState(ctx.sessionDir, ctx.state);

  ctx.onProgress?.("CLASSIFY", `Class: ${taskClass} (${reasons[0] || "no keywords matched"})`);
  return ctx;
}

async function runArchitect(ctx: CycleContext): Promise<CycleContext> {
  ctx.onProgress?.(
  "ARCHITECT",
  `Running architect · ${agentConfig(ctx.cwd, "architect").model}`
);

  const taskFile = path.join(ctx.sessionDir, "task.txt");
  const result = await invokeAgent(ctx.cwd, "architect", ARCHITECT_PROMPT, [taskFile], ctx.signal);
  ctx.costs.push(...result.costs);

  let plan: ArchitecturePlan;
  try {
    plan = parseJsonResponse(result.text, "Architect") as unknown as ArchitecturePlan;
  } catch (e: any) {
    throw Object.assign(
      new Error(`Architect response parse failed: ${e.message}`),
      { failureReason: "FAILED_AGENT" as FailureReason },
    );
  }

  const validationErr = validatePlan(plan);
  if (validationErr) {
    throw Object.assign(
      new Error(`Architect plan validation failed: ${validationErr}`),
      { failureReason: "FAILED_AGENT" as FailureReason },
    );
  }

  ctx.plan = plan;
  writePlan(ctx.sessionDir, plan);
  writePlanEli5(ctx.sessionDir, plan);

  // Verify architect didn't modify files
  const postStatus = await getStatusPorcelain(ctx.cwd, true);
  if (postStatus.trim()) {
    throw Object.assign(
      new Error(
        "Architect changed tracked repository files despite read-only instructions. Aborting.\n\n" +
        postStatus,
      ),
      { failureReason: "FAILED_AGENT" as FailureReason },
    );
  }

  ctx.state.state = "ARCHITECT";
  writeState(ctx.sessionDir, ctx.state);

  ctx.onProgress?.("ARCHITECT", `Plan: ${plan.design.substring(0, 80)}...`);
  return ctx;
}

async function runImplement(ctx: CycleContext): Promise<CycleContext> {
  // Implementer
  ctx.onProgress?.(
    "IMPLEMENT",
    `Running implementer · ${agentConfig(ctx.cwd, "implementer").model}`,
  );

  const taskFile = path.join(ctx.sessionDir, "task.txt");
  const planFile = path.join(ctx.sessionDir, "plan.json");

  const result = await invokeAgent(ctx.cwd, "implementer", IMPLEMENT_PROMPT, [taskFile, planFile], ctx.signal);
  ctx.costs.push(...result.costs);

  // Extract ELI5 section from final response
  const eli5Match = result.text.match(/(?:^|\n)#*\s*ELI5\s*:?\s*\n([\s\S]*?)(?:\n#+\s|\n[A-Z][A-Z\s/-]+$|$)/i);
  const eli5 = eli5Match ? eli5Match[1].replace(/^[-*]\s+/gm, "").trim() : "(no ELI5 recorded)";
  writeEli5(ctx.sessionDir, eli5, "implementation-1");

  ctx.state.state = "IMPLEMENT";
  ctx.state.implementationRound++;
  writeState(ctx.sessionDir, ctx.state);

  await snapshotAndSave(ctx, "01-after-implementation");

  ctx.onProgress?.("IMPLEMENT", "Implementation complete");
  return ctx;
}

async function runVerify(ctx: CycleContext): Promise<{ ok: boolean; report: VerificationReport; reportFile: string }> {
  ctx.onProgress?.("VERIFY", "Running verification...");

  const report = await runVerification(ctx.plan!, new Set(["cheap"]), ctx.cwd, ctx.signal);
  const fingerprint = await candidateFingerprint(ctx.cwd);
  report.candidate_fingerprint = fingerprint;

  const attempt = ctx.state.implementationRound;
  const reportFile = writeVerification(ctx.sessionDir, "cheap", attempt, report);

  ctx.state.state = "VERIFY";
  writeState(ctx.sessionDir, ctx.state);

  const summary = report.checks
    .filter(c => c.status !== "NOT_RUN_THIS_PHASE")
    .map(c => `${c.name}: ${c.status}`).join(", ");
  ctx.onProgress?.("VERIFY", summary || "(no checks run)");

  return { ok: report.required_checks_passed, report, reportFile };
}

async function runReview(
  ctx: CycleContext,
  verificationFile: string,
  round: number,
  sol: boolean = false,
  extraFiles: string[] = [],
  prompt?: string,
): Promise<{ file: string; data: ReviewResult }> {
  const label = sol ? "ESCALATION REVIEW" : "REVIEW";

  const taskFile = path.join(ctx.sessionDir, "task.txt");
  const planFile = path.join(ctx.sessionDir, "plan.json");
  const role = sol ? "reviewer_escalation" : "reviewer";

  ctx.onProgress?.(
    sol ? "ESCALATE" : "REVIEW",
    `${label} round ${round} · ${agentConfig(ctx.cwd, role).model}`,
  );

  const reviewPrompt = prompt || REVIEW_PROMPT;

  const stats = await getChangedPathsStats(ctx.cwd);
  let listingLines = "";
  if (stats.paths.length > 0) {
    listingLines = "\n\nOrchestrator-provided changed files (verify against git yourself):\n" +
      stats.paths.slice(0, 60).map((p) => `- ${p}`).join("\n");
    if (stats.paths.length > 60) {
      listingLines += `\n- ... and ${stats.paths.length - 60} more`;
    }
  }

  const result = await invokeAgent(
    ctx.cwd,
    role,
    reviewPrompt + listingLines,
    [taskFile, planFile, verificationFile, ...extraFiles],
    ctx.signal,
  );
  ctx.costs.push(...result.costs);

  let reviewData: ReviewResult;
  try {
    reviewData = parseJsonResponse(result.text, role) as unknown as ReviewResult;
  } catch (e: any) {
    throw Object.assign(
      new Error(`Reviewer response parse failed: ${e.message}`),
      { failureReason: "FAILED_AGENT" as FailureReason },
    );
  }

  const validationErr = validateReview(reviewData);
  if (validationErr) {
    throw Object.assign(
      new Error(`Review validation failed: ${validationErr}`),
      { failureReason: "FAILED_AGENT" as FailureReason },
    );
  }

  reviewData.candidate_fingerprint = await candidateFingerprint(ctx.cwd);
  const reviewFile = writeReview(ctx.sessionDir, round, sol, reviewData);

  ctx.onProgress?.(sol ? "ESCALATE" : "REVIEW", `${reviewData.verdict} (uncertainty: ${reviewData.uncertainty})`);

  return { file: reviewFile, data: reviewData };
}

async function runFix(
  ctx: CycleContext,
  reviewFile: string,
  label: string,
): Promise<void> {
    ctx.onProgress?.(
    "REPAIR",
    `Fixing: ${label} · ${agentConfig(ctx.cwd, "implementer").model}`,
  );

  const taskFile = path.join(ctx.sessionDir, "task.txt");
  const planFile = path.join(ctx.sessionDir, "plan.json");

  const FIX_PROMPT = "The senior reviewer found concrete problems in the implementation.\n\nRead:\n- the original user task\n- the architecture plan\n- the attached review\n\nFix ONLY the review findings and any directly necessary consequences.\nDo not perform unrelated improvements.\nDo not modify the architecture plan or its verification commands.\nDo not commit or push.\n\nThe orchestrator will independently run the required verification after you finish.\n\n" + "Never use destructive repository operations or revert a file merely because it was already changed or looks unrelated. Leave such a file untouched and report it.\n\nWrap only your final user-facing summary between these exact marker lines:\n\nFINAL_RESPONSE_BEGIN\n<final summary>\nFINAL_RESPONSE_END";

  const result = await invokeAgent(ctx.cwd, "implementer", FIX_PROMPT, [taskFile, planFile, reviewFile], ctx.signal);
  ctx.costs.push(...result.costs);

  await snapshotAndSave(ctx, `${label}-after-fix`);
}

async function runCycle(ctx: CycleContext): Promise<{ state: TerminalState; eli5: string }> {
  await runPreflight(ctx);
  await runClassify(ctx);

  const isTrivial = ctx.state.taskClass === "TRIVIAL_CANDIDATE";

  // ---- TRIVIAL path ----
  if (isTrivial) {
    ctx.plan = createTrivialPlan(ctx.task);
    writePlan(ctx.sessionDir, ctx.plan);
    writePlanEli5(ctx.sessionDir, ctx.plan);

    await runImplement(ctx);

    const stats = await getChangedPathsStats(ctx.cwd);
    const diff = await getDiff(ctx.cwd);
    const { confirmed, reasons } = confirmTrivialDiff(stats, diff);
    writeDiffPatch(ctx.sessionDir, diff);

    if (!confirmed) {
      return {
        state: "FAILED",
        eli5: `Fast path aborted: diff is not confidently non-behavioral.\n${reasons.join("\n")}`,
      };
    }

    ctx.state.confirmedTrivial = true;
    writeState(ctx.sessionDir, ctx.state);

    const { ok: verifOk } = await runVerify(ctx);
    if (!verifOk) {
      return { state: "FAILED_VERIFICATION" as any, eli5: "Required cheap verification failed." };
    }

    const verifFile = path.join(ctx.sessionDir, "cheap-verification-1.json");
    const { data: reviewData } = await runReview(ctx, verifFile, 1);

    if (reviewData.verdict === "PASS") {
      await snapshotAndSave(ctx, "02-accepted");
      return accepted(ctx);
    }

    await runFix(ctx, path.join(ctx.sessionDir, "review-1.json"), "review-1");

    const { ok: verifOk2 } = await runVerify(ctx);
    if (!verifOk2) {
      return { state: "FAILED_VERIFICATION" as any, eli5: "Cheap verification failed after fix." };
    }

    const stats2 = await getChangedPathsStats(ctx.cwd);
    const diff2 = await getDiff(ctx.cwd);
    const { confirmed: confirmed2, reasons: reasons2 } = confirmTrivialDiff(stats2, diff2);
    if (!confirmed2) {
      return {
        state: "FAILED",
        eli5: `Post-fix diff is not confidently non-behavioral.\n${reasons2.join("\n")}`,
      };
    }

    const verifFile2 = path.join(ctx.sessionDir, "cheap-verification-2.json");
    const { data: reviewData2 } = await runReview(ctx, verifFile2, 2);

    if (reviewData2.verdict === "PASS") {
      await snapshotAndSave(ctx, "02-accepted");
      return accepted(ctx);
    }

    return {
      state: "REJECTED",
      eli5: "Fast-path review still reports issues after one fix round. Run through the normal cycle for deeper review.",
    };
  }

  // ---- NORMAL path ----
  await runArchitect(ctx);
  await runImplement(ctx);

  const MAX_R = 2;
  const MAX_SOL = 3;
  let lunaReviews: ReviewResult[] = [];
  let activeVerifFile: string | null = null;
  let activeFingerprint: string | null = null;

  for (let round = 1; round <= MAX_R + 1; round++) {
    const fingerprint = await candidateFingerprint(ctx.cwd);
    activeFingerprint = fingerprint;

    const verifResult = await runVerify(ctx);
    activeVerifFile = verifResult.reportFile;

    if (!verifResult.ok) {
      if (ctx.state.implementationRound <= MAX_R) {
        await runFix(ctx, verifResult.reportFile, `verification-fix-${ctx.state.implementationRound}`);
        ctx.state.implementationRound++;
        continue;
      }
      return { state: "FAILED_VERIFICATION" as any, eli5: "Required cheap verification failed after retry limit." };
    }

    const reviewResult = await runReview(ctx, activeVerifFile, round);
    lunaReviews.push(reviewResult.data);

    if (reviewResult.data.verdict === "PASS") break;
    if (round >= MAX_R) break;

    await runFix(ctx, reviewResult.file, `review-${round}`);
    ctx.state.implementationRound++;
  }

  const latestLuna = lunaReviews[lunaReviews.length - 1];
  if (latestLuna && latestLuna.verdict === "FIX") {
    return {
      state: "REJECTED",
      eli5: `Review limit reached with FIX verdict. The implementation could not satisfy the reviewer within ${MAX_R} rounds.`,
    };
  }

  const stats = await getChangedPathsStats(ctx.cwd);
  const escalationInput = {
    changedPaths: stats.paths,
    changedLines: stats.changedLines,
    trackedFileCount: stats.trackedFiles,
    plan: ctx.plan!,
    verificationHistory: [],
    lunaReviews,
    latestLunaReview: latestLuna!,
    confirmedTrivial: ctx.state.confirmedTrivial,
  };

  const { escalated, reasons: escalationReasons } = shouldEscalate(escalationInput);
  ctx.state.escalated = escalated;
  ctx.state.escalationReasons = escalationReasons;

  const escDecision = { escalated, reasons: escalationReasons, candidate_fingerprint: activeFingerprint || "" };
  writeEscalation(ctx.sessionDir, escDecision);
  writeState(ctx.sessionDir, ctx.state);

  if (escalated) {
    ctx.onProgress?.("ESCALATE", `Escalating: ${escalationReasons.join("; ")}`);
    let escalationPassed = false;
    for (let solRound = 1; solRound <= MAX_SOL; solRound++) {
      const solResult = await runReview(
        ctx, activeVerifFile!, solRound, true,
        [path.join(ctx.sessionDir, "escalation.json")],
      );

      if (solResult.data.verdict === "PASS") {
        escalationPassed = true;
        break;
      }

      await runFix(ctx, solResult.file, `sol-review-${solRound}`);
      const verifResult = await runVerify(ctx);
      if (!verifResult.ok) {
        return { state: "FAILED_VERIFICATION" as any, eli5: "Verification failed after escalation fix." };
      }
    }
    if (!escalationPassed) {
      return {
        state: "REJECTED",
        eli5: `Escalation reviewer could not reach PASS within ${MAX_SOL} rounds.`,
      };
    }
  } else {
    ctx.onProgress?.("ESCALATE", "Not required");
  }

  const finalReport = await runVerification(ctx.plan!, new Set(), ctx.cwd, ctx.signal);
  finalReport.candidate_fingerprint = activeFingerprint;
  finalReport.expensive_gate_enabled = false;
  writeVerification(ctx.sessionDir, "final-expensive", 1, finalReport);

  await snapshotAndSave(ctx, "02-accepted");
  return accepted(ctx);
}

function accepted(ctx: CycleContext): { state: TerminalState; eli5: string } {
  const eli5 = composeFinalEli5(ctx.sessionDir, true);
  return { state: "ACCEPTED", eli5 };
}

// ============================================================================
// Pi-native progress UI
// ============================================================================

/**
 * Keep cycle progress in a compact widget above the editor instead of the
 * footer/status line. Pi already owns the footer for cwd/context/model, so
 * orchestration state is clearer in its own widget.
 */
function setCycleProgressWidget(
  ctx: any,
  stateName: string,
  detail: string,
): void {
  if (!ctx.hasUI) {
    console.log(`[sts-cycle] ${stateName}: ${detail}`);
    return;
  }

  const separator = " · ";
  const splitAt = detail.lastIndexOf(separator);
  const hasModel =
    splitAt > 0 &&
    detail.substring(splitAt + separator.length).includes("/");

  const lines: string[] = [];
  if (hasModel) {
    const message = detail.substring(0, splitAt);
    const model = detail.substring(splitAt + separator.length);
    lines.push(`STS CYCLE  ▶ ${stateName}`);
    lines.push(message);
    lines.push(`model: ${model}`);
  } else {
    lines.push(`STS CYCLE  ▶ ${stateName}`);
    lines.push(detail);
  }

  // Default placement is above the editor.
  ctx.ui.setWidget("sts-cycle-progress", lines);
}

function clearCycleProgressWidget(ctx: any): void {
  if (!ctx.hasUI) return;
  ctx.ui.setWidget("sts-cycle-progress", undefined);
  // Also clear stale footer status from older versions of this extension.
  ctx.ui.setStatus("sts-cycle", undefined);
}

// ============================================================================
// Pi extension registration
// ============================================================================

export default function stsCycle(pi: ExtensionAPI) {
  pi.registerCommand("sts-cycle", {
    description: "Deterministic agent orchestration: architect → implement → verify → review → accept/reject",

    handler: async (args, ctx) => {
      const task = args.trim();
      if (!task) {
        if (ctx.hasUI) ctx.ui.notify("Usage: /sts-cycle <task description>", "warning");
        else console.error("Usage: /sts-cycle <task description>");
        return;
      }

      const cwd = ctx.cwd;
      ensureAiRoot();

      const head = await getHeadCommit(cwd);
      const sessionDir = createSessionDir();
      writeTask(sessionDir, task);

      const state: CycleSessionState = {
        state: "PREFLIGHT",
        taskClass: "NORMAL",
        task,
        baselineCommit: head,
        baselineFingerprint: "",
        implementationRound: 0,
        reviewRound: 0,
        solReviewRound: 0,
        expensiveRepairs: 0,
        confirmedTrivial: false,
        escalated: false,
        escalationReasons: [],
        startedAt: new Date().toISOString(),
        costs: { per_agent: {}, total: 0 },
      };

      const cycleCtx: CycleContext = {
        sessionDir,
        cwd,
        task,
        state,
        plan: null,
        costs: [],
        // Commands normally run while Pi is idle, so ctx.signal is usually
        // undefined. runPiChild still enforces its own lifecycle watchdogs.
        signal: ctx.signal,
        onProgress: (stateName: string, detail: string) => {
          setCycleProgressWidget(ctx, stateName, detail);
        },
      };

      try {
        const result = await runCycle(cycleCtx);

        const costSummary = summarizeCosts(cycleCtx.costs);
        state.costs = costSummary;
        state.state = result.state;
        writeState(sessionDir, state);
        writeCosts(sessionDir, cycleCtx.costs);

        let output = `STS Cycle: ${result.state}\n\n`;
        output += `Session: ${sessionDir}\n`;
        output += `Task: ${task.substring(0, 120)}${task.length > 120 ? "..." : ""}\n`;
        output += `Baseline: ${state.baselineCommit.substring(0, 8)}\n\n`;
        output += `Final ELI5\n${result.eli5}\n`;

        if (cycleCtx.costs.length > 0) {
          output += "\nCost\n";
          for (const [agent, costValue] of Object.entries(costSummary.per_agent)) {
            output += `- ${agent}: $${costValue.toFixed(4)}\n`;
          }
          output += `- Total: $${costSummary.total.toFixed(4)}\n`;
        }

        if (result.state === "ACCEPTED") {
          output += "\nNo commit was created. Inspect with:\n";
          output += "git status --short\n";
          output += "git diff\n";
        }

        if (ctx.hasUI) {
          clearCycleProgressWidget(ctx);
          ctx.ui.setWidget("sts-cycle-result", output.split("\n"));
          ctx.ui.notify(
            `STS Cycle finished: ${result.state}`,
            result.state === "ACCEPTED" ? "info" : "warning",
          );
        } else {
          console.log(output);
        }
      } catch (error: any) {
        const failureReason = error.failureReason || "FAILED_AGENT";
        const terminalState: TerminalState = "FAILED";

        state.state = terminalState;
        writeState(sessionDir, state);
        writeCosts(sessionDir, cycleCtx.costs);

        const output =
          `STS Cycle: ${terminalState}\n\n` +
          `Reason: ${failureReason}\n` +
          `Error: ${error.message}\n\n` +
          `Session: ${sessionDir}`;

        if (ctx.hasUI) {
          clearCycleProgressWidget(ctx);
          ctx.ui.setWidget("sts-cycle-result", output.split("\n"));
          ctx.ui.notify(`STS Cycle failed: ${failureReason}`, "error");
        } else {
          console.error(output);
        }
      }
    },
  });
}