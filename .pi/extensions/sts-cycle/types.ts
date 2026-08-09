/**
 * StS Cycle - Shared types
 *
 * Types for the deterministic Pi-native agent orchestration state machine.
 * Replaces the Python orchestrator in tools/ai_cycle.py.
 */

// ---------------------------------------------------------------------------
// Task classification
// ---------------------------------------------------------------------------

export type TaskClass = "TRIVIAL_CANDIDATE" | "NORMAL" | "HIGH_RISK";

export interface ClassificationResult {
  class: TaskClass;
  reasons: string[];
}

// ---------------------------------------------------------------------------
// Cycle states
// ---------------------------------------------------------------------------

export type CycleState =
  | "PREFLIGHT"
  | "CLASSIFY"
  | "ARCHITECT"
  | "IMPLEMENT"
  | "VERIFY"
  | "REVIEW"
  | "REPAIR"
  | "ESCALATE"
  | "FINAL_VERIFY"
  | "ACCEPTED"
  | "REJECTED"
  | "FAILED"
  | "ABORTED";

export type TerminalState = "ACCEPTED" | "REJECTED" | "FAILED" | "ABORTED";

export type FailureReason =
  | "FAILED_VERIFICATION"
  | "FAILED_AGENT"
  | "FAILED_POLICY"
  | "TIMED_OUT";

export interface CycleError {
  state: TerminalState;
  failureReason: FailureReason;
  message: string;
}

// ---------------------------------------------------------------------------
// Architecture plan (matches the JSON schema from .pi/agents/architect.md)
// ---------------------------------------------------------------------------

export interface VerificationCheck {
  name: string;
  argv: string[];
  cwd: string;
  env: Record<string, string>;
  required: boolean;
  cost: "cheap" | "expensive";
  seed_count?: number;
  timeout_seconds: number;
}

export interface ImplementationStep {
  description: string;
  files: string[];
  symbols: string[];
  invariants: string[];
}

export interface ArchitecturePlan {
  task_interpretation: string;
  current_behavior: string;
  design: string;
  eli5_summary: string;
  implementation_steps: ImplementationStep[];
  verification: VerificationCheck[];
  documentation: string[];
  acceptance_criteria: string[];
  risks: string[];
}

// ---------------------------------------------------------------------------
// Review (matches the JSON schema from .pi/agents/reviewer.md)
// ---------------------------------------------------------------------------

export interface ReviewIssue {
  severity: "CRITICAL" | "MAJOR" | "MINOR";
  location: string;
  problem: string;
  failure_mechanism: string;
  required_fix: string;
}

export interface ReviewResult {
  verdict: "PASS" | "FIX";
  summary: string;
  eli5_summary: string;
  uncertainty: "LOW" | "MEDIUM" | "HIGH";
  issues: ReviewIssue[];
  candidate_fingerprint?: string;
}

// ---------------------------------------------------------------------------
// Verification result
// ---------------------------------------------------------------------------

export interface SingleCheckResult {
  name: string;
  argv: string[];
  cwd: string;
  env: Record<string, string>;
  required: boolean;
  cost: "cheap" | "expensive";
  status: "PASS" | "FAIL" | "TIMEOUT" | "NOT_RUN_THIS_PHASE";
  returncode: number | null;
  stdout: string;
  duration_ms: number;
}

export interface VerificationReport {
  required_checks_passed: boolean;
  costs_run: string[];
  checks: SingleCheckResult[];
  candidate_fingerprint?: string;
  expensive_gate_enabled?: boolean;
}

// ---------------------------------------------------------------------------
// Escalation decision
// ---------------------------------------------------------------------------

export interface EscalationDecision {
  escalated: boolean;
  reasons: string[];
  candidate_fingerprint: string;
}

// ---------------------------------------------------------------------------
// Artifacts
// ---------------------------------------------------------------------------

export interface CycleCostEntry {
  agent: string;
  model: string;
  cost: number;
  tokens_input: number;
  tokens_output: number;
  tokens_reasoning: number;
  tokens_cache_read: number;
  tokens_cache_write: number;
}

export interface CycleCostSummary {
  per_agent: Record<string, number>;
  total: number;
}

// ---------------------------------------------------------------------------
// Agent role identifiers
// ---------------------------------------------------------------------------

export type CycleRole =
  | "architect"
  | "implementer"
  | "reviewer"
  | "reviewer_escalation";

// ---------------------------------------------------------------------------
// Session state (stored in state.json)
// ---------------------------------------------------------------------------

export interface CycleSessionState {
  state: CycleState;
  taskClass: TaskClass;
  task: string;
  baselineCommit: string;
  baselineFingerprint: string;
  implementationRound: number;
  reviewRound: number;
  solReviewRound: number;
  expensiveRepairs: number;
  confirmedTrivial: boolean;
  escalated: boolean;
  escalationReasons: string[];
  startedAt: string;
  costs: CycleCostSummary;
}
