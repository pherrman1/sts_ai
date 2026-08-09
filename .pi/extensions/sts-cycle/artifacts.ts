/**
 * StS Cycle - Artifact I/O
 *
 * Session directory creation, JSON read/write, and artifact management.
 * No LLM calls, no process management.
 */

import * as fs from "node:fs";
import * as path from "node:path";
import type { ArchitecturePlan, CycleCostEntry, CycleCostSummary, CycleSessionState, EscalationDecision, ReviewResult, VerificationReport } from "./types.ts";

const AI_ROOT = ".ai";

export function ensureDir(dir: string): void {
  fs.mkdirSync(dir, { recursive: true });
}

export function saveJson(p: string, data: unknown): void {
  fs.writeFileSync(p, JSON.stringify(data, null, 2) + "\n", { encoding: "utf-8" });
}

export function loadJson<T>(p: string): T {
  const raw = fs.readFileSync(p, { encoding: "utf-8" });
  const data = JSON.parse(raw);
  return data as T;
}

export function saveText(p: string, content: string): void {
  fs.writeFileSync(p, content, { encoding: "utf-8" });
}

export function loadText(p: string): string {
  return fs.readFileSync(p, { encoding: "utf-8" });
}

export function fileExists(p: string): boolean {
  return fs.existsSync(p);
}

/**
 * Create a timestamped session directory under .ai/cycles/
 */
export function createSessionDir(): string {
  const now = new Date();
  const ts = now.toISOString().replace(/[:.]/g, "-").replace("T", "-").substring(0, 19);
  const dir = path.join(AI_ROOT, "cycles", ts);
  ensureDir(dir);
  return dir;
}

/**
 * Ensure the AI root directory exists.
 */
export function ensureAiRoot(): void {
  ensureDir(path.join(AI_ROOT, "cycles"));
}

// ---------------------------------------------------------------------------
// Artifact writers
// ---------------------------------------------------------------------------

export function writeTask(sessionDir: string, task: string): void {
  saveText(path.join(sessionDir, "task.txt"), task + "\n");
}

export function writeState(sessionDir: string, state: CycleSessionState): void {
  saveJson(path.join(sessionDir, "state.json"), state);
}

export function loadState(sessionDir: string): CycleSessionState {
  return loadJson<CycleSessionState>(path.join(sessionDir, "state.json"));
}

export function writeClassification(
  sessionDir: string,
  classification: { class: string; reasons: string[] },
): void {
  saveJson(path.join(sessionDir, "classification.json"), classification);
}

export function writePlan(sessionDir: string, plan: ArchitecturePlan): void {
  saveJson(path.join(sessionDir, "plan.json"), plan);
}

export function loadPlan(sessionDir: string): ArchitecturePlan {
  return loadJson<ArchitecturePlan>(path.join(sessionDir, "plan.json"));
}

export function writePlanEli5(sessionDir: string, plan: ArchitecturePlan): void {
  if (plan.eli5_summary) {
    saveText(path.join(sessionDir, "plan-eli5.md"), plan.eli5_summary.trim() + "\n");
  }
}

export function writeDiffPatch(sessionDir: string, diff: string): void {
  saveText(path.join(sessionDir, "diff.patch"), diff);
}

export function writeGitSnapshot(sessionDir: string, name: string, content: string): void {
  saveText(path.join(sessionDir, `${name}.txt`), content);
}

export function writeVerification(
  sessionDir: string,
  phase: string,
  attempt: number,
  report: VerificationReport,
): string {
  const p = path.join(sessionDir, `${phase}-verification-${attempt}.json`);
  saveJson(p, report);
  return p;
}

export function writeReview(
  sessionDir: string,
  roundNumber: number,
  sol: boolean,
  review: ReviewResult,
): string {
  const stem = sol ? `sol-review-${roundNumber}` : `review-${roundNumber}`;
  const p = path.join(sessionDir, `${stem}.json`);
  saveJson(p, review);
  saveText(path.join(sessionDir, `${stem}-eli5.md`), review.eli5_summary.trim() + "\n");
  return p;
}

export function writeEscalation(
  sessionDir: string,
  decision: EscalationDecision,
): string {
  const p = path.join(sessionDir, "escalation.json");
  saveJson(p, decision);
  return p;
}

export function writeCosts(
  sessionDir: string,
  entries: CycleCostEntry[],
): void {
  const p = path.join(sessionDir, "costs.json");
  let existing: CycleCostEntry[] = [];
  if (fileExists(p)) {
    try {
      const loaded = loadJson<{ entries: CycleCostEntry[] }>(p);
      if (loaded?.entries) existing = loaded.entries;
    } catch { /* ignore */ }
  }
  saveJson(p, { entries: [...existing, ...entries] });
}

export function summarizeCosts(entries: CycleCostEntry[]): CycleCostSummary {
  const perAgent: Record<string, number> = {};
  let total = 0;
  for (const e of entries) {
    const agent = e.agent || "unknown";
    const cost = e.cost || 0;
    perAgent[agent] = (perAgent[agent] || 0) + cost;
    total += cost;
  }
  return { per_agent: perAgent, total };
}

export function writeEli5(sessionDir: string, eli5: string, stem?: string): void {
  const filename = stem ? `${stem}-eli5.md` : "eli5.md";
  saveText(path.join(sessionDir, filename), eli5.trim() + "\n");
}

export function loadEli5(sessionDir: string, stem: string): string | null {
  const p = path.join(sessionDir, `${stem}-eli5.md`);
  if (!fileExists(p)) return null;
  return loadText(p).trim();
}

export function composeFinalEli5(
  sessionDir: string,
  accepted: boolean,
): string {
  const planEli5 = loadEli5(sessionDir, "plan") || "(no plan summary)";
  const implEli5 = loadEli5(sessionDir, "implementation-1") || "(no implementation summary)";
  const reviewEli5 = loadEli5(sessionDir, "review-1") || loadEli5(sessionDir, "sol-review-1") || "(no review summary)";

  const lines = [
    "===== FINAL ELI5 =====",
    "",
    "What we wanted:",
    planEli5,
    "",
    "What was built:",
    implEli5,
    "",
    "What the reviewer found:",
    reviewEli5,
    "",
    accepted
      ? "Verdict: ACCEPTED — the change passed the review loop.\nWhat to do next: inspect the diff (git status --short, git diff) and commit if it matches the task."
      : "Verdict: NOT ACCEPTED — the review loop could not reach a passing state.\nWhat to do next: see the session rejection notes above.",
  ];
  return lines.join("\n");
}
