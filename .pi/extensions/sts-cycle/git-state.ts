/**
 * StS Cycle - Git state operations
 *
 * Deterministic read-only git operations for preflight checks,
 * state snapshots, and diff inspection. All commands use `git`
 * with allowlisted subcommands.
 */

import { spawn } from "node:child_process";
import * as path from "node:path";

const MAX_OUTPUT = 500 * 1024; // 500KB

async function runGit(
  args: string[],
  cwd: string,
  signal?: AbortSignal,
): Promise<{ code: number; stdout: string; stderr: string }> {
  return new Promise((resolve) => {
    const proc = spawn("git", args, {
      cwd,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let total = 0;

    proc.stdout.on("data", (chunk: Buffer) => {
      if (total < MAX_OUTPUT) {
        const slice = chunk.subarray(0, MAX_OUTPUT - total);
        total += slice.length;
        stdout += slice.toString();
      }
    });

    proc.stderr.on("data", (chunk: Buffer) => {
      stderr += chunk.toString();
    });

    const abort = () => {
      proc.kill("SIGTERM");
      setTimeout(() => { if (!proc.killed) proc.kill("SIGKILL"); }, 2000).unref();
    };

    if (signal) {
      if (signal.aborted) abort();
      else signal.addEventListener("abort", abort, { once: true });
    }

    proc.on("error", (err) => {
      resolve({ code: 1, stdout, stderr: `${stderr}\n${String(err)}`.trim() });
    });

    proc.on("close", (code) => {
      resolve({ code: code ?? 1, stdout, stderr });
    });
  });
}

export async function getHeadCommit(cwd: string): Promise<string> {
  const result = await runGit(["rev-parse", "HEAD"], cwd);
  if (result.code !== 0) throw new Error(`git rev-parse HEAD failed: ${result.stderr}`);
  return result.stdout.trim();
}

export async function getStatusPorcelain(
  cwd: string,
  trackedOnly: boolean = false,
): Promise<string> {
  const args = ["status", "--porcelain"];
  if (trackedOnly) args.push("--untracked-files=no");
  const result = await runGit(args, cwd);
  return result.stdout.trim();
}

export async function getDiff(cwd: string): Promise<string> {
  const result = await runGit(["diff", "HEAD"], cwd);
  return result.stdout;
}

export async function getDiffNameOnly(cwd: string): Promise<string[]> {
  const result = await runGit(["diff", "--name-only", "HEAD"], cwd);
  return result.stdout.trim().split("\n").filter(Boolean);
}

export async function getDiffNumstat(
  cwd: string,
): Promise<{ files: number; lines: number }> {
  const result = await runGit(["diff", "--numstat", "HEAD"], cwd);
  let files = 0;
  let lines = 0;
  for (const line of result.stdout.trim().split("\n")) {
    if (!line) continue;
    const parts = line.split("\t");
    if (parts.length < 3) continue;
    files++;
    if (/^\d+$/.test(parts[0])) lines += parseInt(parts[0], 10);
    if (/^\d+$/.test(parts[1])) lines += parseInt(parts[1], 10);
  }
  return { files, lines };
}

export async function getUntrackedFiles(cwd: string): Promise<string[]> {
  const result = await runGit(
    ["status", "--porcelain", "--untracked-files=all"],
    cwd,
  );
  const paths: string[] = [];
  for (const line of result.stdout.trim().split("\n")) {
    if (line.startsWith("?? ")) {
      paths.push(line.substring(3));
    }
  }
  return paths;
}

export interface ChangedPathsStats {
  paths: string[];
  changedLines: number;
  trackedFiles: number;
}

/**
 * Return all changed/untracked paths and diff stats.
 * Mirrors changed_diff_stats() in ai_cycle.py.
 */
export async function getChangedPathsStats(cwd: string): Promise<ChangedPathsStats> {
  const diffPaths = await getDiffNameOnly(cwd);
  const { files: trackedFiles, lines: changedLines } = await getDiffNumstat(cwd);
  const untracked = await getUntrackedFiles(cwd);

  const allPaths = [...new Set([...diffPaths, ...untracked])].sort();
  return { paths: allPaths, changedLines, trackedFiles };
}

/**
 * Create a human-readable snapshot of the current git state.
 * Mirrors snapshot_git_state() in ai_cycle.py.
 */
export async function snapshotState(
  cwd: string,
): Promise<string> {
  const head = await getHeadCommit(cwd);
  const status = await getStatusPorcelain(cwd);
  const diffStat = (await runGit(["diff", "--stat", "HEAD"], cwd)).stdout;
  const diff = await getDiff(cwd);

  return [
    "HEAD",
    "====",
    head,
    "",
    "STATUS",
    "======",
    status,
    "",
    "DIFF STAT",
    "=========",
    diffStat,
    "",
    "DIFF",
    "====",
    diff,
  ].join("\n") + "\n";
}

/**
 * Compute a candidate fingerprint from git state.
 */
export async function candidateFingerprint(cwd: string): Promise<string> {
  const { createHash } = await import("node:crypto");
  const hash = createHash("sha256");

  const head = await getHeadCommit(cwd);
  hash.update(head);

  const diff = await getDiff(cwd);
  hash.update(diff);

  const status = await runGit(
    ["status", "--porcelain", "--untracked-files=all"],
    cwd,
  );
  hash.update(status.stdout);

  // Hash untracked file contents too, for new non-ignored files.
  const untracked = await getUntrackedFiles(cwd);
  const { readFile } = await import("node:fs/promises");
  for (const relPath of untracked) {
    const fullPath = path.join(cwd, relPath);
    try {
      const content = await readFile(fullPath);
      hash.update(content);
    } catch {
      // File may have been deleted between listing and read.
    }
  }

  return hash.digest("hex");
}
