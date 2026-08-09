/**
 * StS Cycle - Verification execution
 *
 * Parses, validates, and executes verification commands from an architecture plan.
 * Never blindly executes arbitrary shell strings from an LLM.
 */

import { spawn } from "node:child_process";
import * as path from "node:path";
import {
  MAX_AUTOMATED_SEEDS,
  validateVerificationCheck,
  validateSeedCount,
} from "./policy.ts";
import type {
  ArchitecturePlan,
  SingleCheckResult,
  VerificationCheck,
  VerificationReport,
} from "./types.ts";

const MAX_OUTPUT = 500 * 1024;

export interface RunResult {
  code: number;
  stdout: string;
  stderr: string;
  timedOut: boolean;
  durationMs: number;
}

async function runCommand(
  argv: string[],
  cwd: string,
  env: Record<string, string>,
  timeoutSeconds: number,
  signal?: AbortSignal,
): Promise<RunResult> {
  const startTime = Date.now();

  return new Promise((resolve) => {
    const childEnv = { ...process.env, ...env };
    const proc = spawn(argv[0], argv.slice(1), {
      cwd,
      env: childEnv,
      shell: false,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let total = 0;
    let timedOut = false;

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

    let settled = false;

    const finish = (code: number, timedOut: boolean) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      if (signal && abortHandler) signal.removeEventListener("abort", abortHandler);
      resolve({
        code,
        stdout,
        stderr,
        timedOut,
        durationMs: Date.now() - startTime,
      });
    };

    const timer = setTimeout(() => {
      timedOut = true;
      proc.kill("SIGTERM");
      setTimeout(() => {
        if (!proc.killed) proc.kill("SIGKILL");
        finish(-1, true);
      }, 5000).unref();
    }, timeoutSeconds * 1000);

    let abortHandler: (() => void) | null = null;
    if (signal) {
      abortHandler = () => {
        proc.kill("SIGTERM");
        setTimeout(() => { if (!proc.killed) proc.kill("SIGKILL"); }, 2000).unref();
        finish(-1, false);
      };
      if (signal.aborted) abortHandler();
      else signal.addEventListener("abort", abortHandler, { once: true });
    }

    proc.on("error", (err) => {
      finish(1, false);
    });

    proc.on("close", (code) => {
      finish(code ?? 1, false);
    });
  });
}

/**
 * Validate all verification commands in a plan before executing any.
 * Returns null if all valid, or an error string.
 */
export function validateAllVerification(plan: ArchitecturePlan): string | null {
  for (let i = 0; i < plan.verification.length; i++) {
    const err = validateVerificationCheck(plan.verification[i], i + 1);
    if (err) return err;
  }
  return null;
}

/**
 * Execute all verification checks matching the requested cost tier.
 */
export async function runVerification(
  plan: ArchitecturePlan,
  costsToRun: Set<"cheap" | "expensive">,
  cwd: string,
  signal?: AbortSignal,
): Promise<VerificationReport> {
  const results: SingleCheckResult[] = [];

  for (const check of plan.verification) {
    const cost = check.cost;

    if (!costsToRun.has(cost)) {
      results.push({
        name: check.name,
        argv: [...check.argv],
        cwd: check.cwd,
        env: { ...check.env },
        required: check.required,
        cost,
        status: "NOT_RUN_THIS_PHASE",
        returncode: null,
        stdout: "",
        duration_ms: 0,
      });
      continue;
    }

    const resolvedCwd = path.resolve(cwd, check.cwd);
    const timeout = check.timeout_seconds || 300;

    let runResult: RunResult;
    try {
      runResult = await runCommand(
        check.argv,
        resolvedCwd,
        check.env,
        timeout,
        signal,
      );
    } catch {
      runResult = { code: 1, stdout: "", stderr: "execution error", timedOut: false, durationMs: 0 };
    }

    let status: SingleCheckResult["status"];
    if (runResult.timedOut) {
      status = "TIMEOUT";
    } else {
      status = runResult.code === 0 ? "PASS" : "FAIL";
    }

    results.push({
      name: check.name,
      argv: [...check.argv],
      cwd: check.cwd,
      env: { ...check.env },
      required: check.required,
      cost,
      status,
      returncode: runResult.code,
      stdout: runResult.stdout,
      duration_ms: runResult.durationMs,
    });
  }

  const requiredOk = results.every(
    (r) =>
      !r.required ||
      r.status === "PASS" ||
      r.cost === "NOT_RUN_THIS_PHASE" as any ||
      (r.cost !== "cheap" && r.cost !== "expensive") ||
      !costsToRun.has(r.cost),
  );

  // More precise: only check required checks that we actually ran
  const requiredPassed = results
    .filter((r) => r.required && costsToRun.has(r.cost as "cheap" | "expensive"))
    .every((r) => r.status === "PASS");

  return {
    required_checks_passed: requiredPassed,
    costs_run: [...costsToRun].sort(),
    checks: results,
  };
}

/**
 * Validate that a raw verification command array does not exceed seed cap.
 * Used by the interactive safety hook.
 */
export function checkSeedCap(argv: string[]): string | null {
  return validateSeedCount(argv);
}
