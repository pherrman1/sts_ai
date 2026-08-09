/**
 * StS Cycle - Deterministic policy
 *
 * Pure functions for all deterministic safety and classification decisions.
 * Ported from tools/ai_cycle.py. No LLM calls, no I/O.
 *
 * This is the AUTHORITATIVE source for:
 *   - MAX_AUTOMATED_SEEDS = 128
 *   - seed-sweep argument maps
 *   - verification executable allowlist
 *   - protected paths
 *   - high-risk path rules
 *   - high-risk plan terms
 *   - task fast-path classification
 *   - deterministic trivial-diff confirmation
 *   - escalation decision logic
 *   - verification command validation
 */

import type {
  ArchitecturePlan,
  ReviewResult,
  VerificationCheck,
  VerificationReport,
} from "./types.ts";

// ============================================================================
// Numeric constants
// ============================================================================

export const MAX_IMPLEMENTATION_RETRIES = 2;
export const MAX_REVIEW_ROUNDS = 2;
export const MAX_SOL_REVIEW_ROUNDS = 3;
export const MAX_EXPENSIVE_REPAIRS = 2;

export const FAST_PATH_MAX_FILES = 2;
export const FAST_PATH_MAX_LINES = 50;

export const MAX_CHEAP_TIMEOUT_SECONDS = 3600;
export const MAX_EXPENSIVE_TIMEOUT_SECONDS = 6 * 3600;

/** Absolute ceiling for any automated agent-driven seed sweep. */
export const MAX_AUTOMATED_SEEDS = 128;

// ============================================================================
// Source extensions recognised for comment-only checks
// ============================================================================

const SOURCE_EXTENSIONS = new Set([
  ".py", ".cpp", ".h", ".hpp", ".c", ".cc", ".cxx",
  ".ts", ".js", ".mjs", ".java", ".rs", ".go", ".swift",
  ".kt", ".scala", ".rb", ".sh", ".bash",
]);

const C_FAMILY_EXTENSIONS = new Set([
  ".c", ".cpp", ".cc", ".cxx", ".h", ".hpp",
  ".java", ".js", ".mjs", ".ts", ".jsx", ".tsx",
  ".rs", ".swift", ".kt", ".scala", ".go", ".m", ".mm",
]);

const DOC_EXTENSIONS = new Set([".md", ".txt", ".rst", ".adoc"]);

// ============================================================================
// Fast-path task classification keywords
// ============================================================================

const TRIVIAL_TASK_KEYWORDS = [
  "comment",
  "comments",
  "explanatory comment",
  "explanatory comments",
  "docstring",
  "docstrings",
  "typo",
  "spelling",
  "grammar",
  "wording",
  "wording-only",
  "documentation",
  "documentation-only",
  "formatting",
  "formatting-only",
];

const SEMANTIC_TASK_KEYWORDS = [
  "implement",
  "add feature",
  "add behavior",
  "add behaviour",
  "remove behavior",
  "remove behaviour",
  "bug fix",
  "fix bug",
  "fix the bug",
  "refactor",
  "restructure",
  "rewrite",
  "redesign",
  "model architecture",
  "training pipeline",
  "train",
  "inference",
  "rng seed handling",
  "fairness evaluation",
  "benchmark methodology",
  "schema change",
  "interface change",
  "build system",
  "cmake",
  "configuration",
  "generated",
  "artifact",
  "export",
  "deploy",
  "optimize",
  "optimise",
  "performance",
  "encoding",
  "mask",
  "masking",
  "action space",
  "leakage",
  "parity",
];

// ============================================================================
// Seed-sweep argument maps
// ============================================================================

export const KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX: Record<string, number> = {
  allbench: 3,
  bench: 3,
  bestbench: 3,
  cardbench: 3,
  causalgen: 2,
  combatgen: 2,
  combobench: 3,
  cpsictr: 3,
  datagen: 2,
  datagen2: 2,
  datagen3: 2,
  distgen: 2,
  draftbench: 3,
  evalcombat: 3,
  evalrun: 3,
  fairgen: 2,
  fightgen: 2,
  oocnextgen: 2,
  pathbench: 3,
  pathcfgen: 2,
  policygen: 2,
  restbench: 3,
  runbench: 3,
  searchdiag: 2,
  shopbench: 3,
  skipbench: 3,
  strategicgen: 2,
  strategicgen2: 2,
};

export const KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX: Record<string, number> = {
  "check_replay.py": 3,
};

// ============================================================================
// Verification allowlists
// ============================================================================

export const ALLOWED_VERIFICATION_EXECUTABLES = new Set([
  "cmake",
  "ctest",
  "git",
  "python",
  "python3",
  "pytest",
]);

export const ALLOWED_GIT_VERIFICATION_SUBCOMMANDS = new Set([
  "blame",
  "diff",
  "grep",
  "log",
  "rev-parse",
  "show",
  "status",
]);

// ============================================================================
// Protected workflow paths
// ============================================================================

export const PROTECTED_WORKFLOW_PATHS = new Set([
  "opencode.json",
  ".opencode/prompts/architect.md",
  ".opencode/prompts/implementer.md",
  ".opencode/prompts/reviewer.md",
  ".opencode/prompts/reviewer-escalation.md",
  "tools/ai_cycle.py",
  "tools/ai_inspect.py",
  "tools/test_ai_cycle.py",
  ".pi/agents/architect.md",
  ".pi/agents/implementer.md",
  ".pi/agents/investigator.md",
  ".pi/agents/reviewer.md",
  ".pi/agents/reviewer-pro.md",
  ".pi/extensions/sts-safety.ts",
  ".pi/extensions/sts-tools.ts",
  ".pi/extensions/subagent/agents.ts",
  ".pi/extensions/subagent/index.ts",
  ".pi/prompts/sts-investigate.md",
  ".pi/extensions/sts-cycle/policy.ts",
  ".pi/extensions/sts-cycle/index.ts",
]);

/** Directories whose contents are entirely protected. */
export const PROTECTED_DIRS = [
  ".pi/agents/",
  ".pi/extensions/",
  ".pi/prompts/",
];

// ============================================================================
// High-risk path rules
// ============================================================================

export const HIGH_RISK_PATH_RULES: Record<string, string[]> = {
  "training": ["train_", "training", "selfplay/"],
  "inference": ["inference", "export_", "native_model", "v_server.py"],
  "selfplay": ["selfplay/", "selfplay"],
  "search": ["search", "searcher", "battle_scum"],
  "RNG/seed handling": ["rng", "random", "seed"],
  "VNet/PVNet": ["vnet", "pvnet"],
  "evaluation/benchmark methodology": [
    "paired_analysis.py",
    "benchmark",
    "bestbench",
    "evaluation",
  ],
  "strategic labels/targets": ["strategic", "label", "target"],
  "counterfactual generation": ["counterfactual", "causalgen"],
  "action masking/state encoding": ["action_mask", "masking", "encoder"],
};

export const HIGH_RISK_PLAN_TERMS: Record<string, string[]> = {
  "training": ["training", "trainer", "retrain"],
  "inference": ["inference", "model loading", "model export", "model use"],
  "selfplay": ["selfplay", "self-play"],
  "search": ["search semantics", "searcher", "tree search"],
  "RNG/fairness": ["rng", "fairness", "known-rng", "known rng", "seed handling"],
  "VNet/PVNet": ["vnet", "pvnet"],
  "evaluation methodology": ["evaluation validity", "benchmark methodology"],
  "labels/targets/bootstrap": [
    "label semantics",
    "target semantics",
    "bootstrap semantics",
  ],
  "counterfactual generation": ["counterfactual generation"],
  "action masking/state encoding": ["action masking", "state encoding"],
  "leakage/parity mismatch": [
    "leakage",
    "training/inference parity",
    "offline/online mismatch",
    "model-use parity",
  ],
};

// ============================================================================
// Task classification
// ============================================================================

/**
 * Deterministically decide whether task is a fast-path candidate.
 * Returns (isCandidate, reasons). Never calls an LLM.
 */
export function classifyTask(task: string): {
  isCandidate: boolean;
  reasons: string[];
} {
  const taskLower = task.trim().toLowerCase();
  if (!taskLower) {
    return { isCandidate: false, reasons: ["empty task"] };
  }

  const sourceKeywords = new Set([
    "comment", "comments", "docstring", "docstrings",
    "explanatory comment", "explanatory comments",
  ]);
  const wordingKeywords = new Set([
    "typo", "spelling", "grammar", "wording",
    "wording-only", "formatting", "formatting-only",
    "documentation", "documentation-only",
  ]);
  const noBehaviourKeywords = new Set([
    "do not change behavior", "no behavior change",
    "not change behaviour", "non-behavioral",
    "non behavioral", "without changing behavior",
    "without changing behaviour",
  ]);

  const matchedTrivial: string[] = [];

  for (const kw of [...TRIVIAL_TASK_KEYWORDS].sort((a, b) => b.length - a.length)) {
    if (taskLower.includes(kw)) {
      matchedTrivial.push(kw);
    }
  }

  // Reject if any semantic keyword is present.
  for (const kw of SEMANTIC_TASK_KEYWORDS) {
    if (taskLower.includes(kw)) {
      return { isCandidate: false, reasons: [`semantic keyword present: ${kw}`] };
    }
  }

  if (matchedTrivial.length === 0) {
    return { isCandidate: false, reasons: ["no fast-path keyword matched"] };
  }

  // If the task mentions source-code comments or docstrings, it must
  // also explicitly forbid behaviour changes.
  const hasSourceTrivial = matchedTrivial.some((kw) => sourceKeywords.has(kw));
  const hasNoBehaviour = [...noBehaviourKeywords].some((kw) => taskLower.includes(kw));

  if (hasSourceTrivial && !hasNoBehaviour) {
    return {
      isCandidate: false,
      reasons: [
        "source-code comment/docstring task without explicit no-behavior-change constraint",
      ],
    };
  }

  return { isCandidate: true, reasons: matchedTrivial };
}

/**
 * Classify the full task, returning HIGH_RISK if the architect's plan
 * identifies semantic risk.
 */
export function classifyTaskFull(
  task: string,
  plan?: ArchitecturePlan,
): { class: "TRIVIAL_CANDIDATE" | "NORMAL" | "HIGH_RISK"; reasons: string[] } {
  const { isCandidate, reasons } = classifyTask(task);

  if (isCandidate) {
    return { class: "TRIVIAL_CANDIDATE", reasons };
  }

  // A task can only be HIGH_RISK after the architect identifies risk.
  // For now, classification alone never returns HIGH_RISK.
  return { class: "NORMAL", reasons };
}

// ============================================================================
// Trivial diff confirmation
// ============================================================================

function isSourceFile(relativePath: string): boolean {
  const ext = relativePath.substring(relativePath.lastIndexOf("."));
  return SOURCE_EXTENSIONS.has(ext);
}

function isDocFile(relativePath: string): boolean {
  const ext = relativePath.substring(relativePath.lastIndexOf("."));
  return DOC_EXTENSIONS.has(ext);
}

function isConfigOrBuildPath(relativePath: string): boolean {
  const parts = relativePath.split("/");
  const name = parts[parts.length - 1];
  if ([
    "CMakeLists.txt", "Makefile", "meson.build", "Dockerfile",
    ".gitignore", ".gitmodules", ".gitattributes",
  ].includes(name)) {
    return true;
  }
  if (parts[0] === "build") return true;
  const ext = relativePath.substring(relativePath.lastIndexOf("."));
  if ([
    ".json", ".yaml", ".yml", ".toml", ".cfg", ".ini",
    ".cmake", ".proto", ".xml",
  ].includes(ext)) {
    return true;
  }
  return false;
}

function isCommentOrBlankLine(line: string, filePath: string): boolean {
  const stripped = line.trimStart();
  if (!stripped) return true;

  const ext = filePath.substring(filePath.lastIndexOf("."));
  const isCFamily = C_FAMILY_EXTENSIONS.has(ext);

  if (isCFamily) {
    if (stripped.startsWith("//")) return true;
    if (stripped.startsWith("/*")) return true;
    if (stripped === "*/") return true;
    return false;
  }

  if (stripped.startsWith("#")) return true;

  if (ext === ".py") {
    if (stripped.startsWith('"""') || stripped.startsWith("'''")) return true;
  }

  return false;
}

export interface DiffConfirmationResult {
  confirmed: boolean;
  reasons: string[];
}

/**
 * Validate that a git diff is conservatively trivial.
 * pathStats: { paths: string[], changedLines: number, trackedFiles: number }
 * diffText: the full `git diff HEAD` output
 */
export function confirmTrivialDiff(
  pathStats: { paths: string[]; changedLines: number; trackedFiles: number },
  diffText: string,
): DiffConfirmationResult {
  const { paths, changedLines, trackedFiles } = pathStats;
  const reasons: string[] = [];

  if (trackedFiles > FAST_PATH_MAX_FILES) {
    reasons.push(
      `Too many changed files: ${trackedFiles} (max ${FAST_PATH_MAX_FILES})`,
    );
    return { confirmed: false, reasons };
  }

  if (changedLines > FAST_PATH_MAX_LINES) {
    reasons.push(
      `Too many changed lines: ${changedLines} (max ${FAST_PATH_MAX_LINES})`,
    );
    return { confirmed: false, reasons };
  }

  for (const p of paths) {
    if (isProtectedPath(p)) {
      reasons.push(`Changed protected workflow path: ${p}`);
      return { confirmed: false, reasons };
    }
  }

  for (const p of paths) {
    if (isConfigOrBuildPath(p)) {
      reasons.push(`Changed config / build / schema path: ${p}`);
      return { confirmed: false, reasons };
    }
  }

  // Parse git diff hunks line-by-line.
  let currentFile: string | null = null;
  let inSourceFile = false;
  let inDocFile = false;
  let inHunk = false;

  for (const rawLine of diffText.split("\n")) {
    const line = rawLine;

    if (line.startsWith("diff --git ")) {
      inHunk = false;
      currentFile = null;
      continue;
    }
    if (line.startsWith("--- ") || line.startsWith("+++ ")) {
      const fname = line.substring(line.indexOf("/") + 1);
      currentFile = fname;
      inSourceFile = isSourceFile(fname);
      inDocFile = isDocFile(fname);
      continue;
    }
    if (line.startsWith("@@ ")) {
      inHunk = true;
      continue;
    }
    if (!inHunk) continue;
    if (line.startsWith("diff --git ")) {
      inHunk = false;
      currentFile = null;
      continue;
    }

    if (line.startsWith("+") || line.startsWith("-")) {
      const content = line.substring(1);
      if (inDocFile) continue;
      if (inSourceFile) {
        if (!isCommentOrBlankLine(content, currentFile!)) {
          reasons.push(
            `Non-comment change in source file ${currentFile}: ${content.substring(0, 80)}`,
          );
          return { confirmed: false, reasons };
        }
      } else if (currentFile !== null) {
        reasons.push(`Unrecognised file type changed: ${currentFile}`);
        return { confirmed: false, reasons };
      }
    }
  }

  if (paths.length === 0) {
    reasons.push("Empty diff (no-op)");
  }

  return { confirmed: true, reasons };
}

// ============================================================================
// Protected path check
// ============================================================================

export function isProtectedPath(relativePath: string): boolean {
  if (PROTECTED_WORKFLOW_PATHS.has(relativePath)) return true;
  for (const dir of PROTECTED_DIRS) {
    if (relativePath === dir.slice(0, -1) || relativePath.startsWith(dir)) {
      // Exception: the sts-cycle extension itself may be modified
      // during migration but is protected during ordinary tasks.
      if (relativePath.startsWith(".pi/extensions/sts-cycle/")) {
        return false;
      }
      return true;
    }
  }
  return false;
}

// ============================================================================
// Verification command validation
// ============================================================================

export function validateVerificationCheck(
  check: VerificationCheck,
  index: number,
  allowLegacySweeps: boolean = false,
): string | null {
  if (!check.name || !check.name.trim()) {
    return `verification[${index}].name must be a non-empty string`;
  }

  if (!Array.isArray(check.argv) || check.argv.length === 0) {
    return `verification[${index}].argv must be a non-empty string array`;
  }

  const executable = check.argv[0];
  const projectLocal = executable.startsWith("./");

  if (!projectLocal && !ALLOWED_VERIFICATION_EXECUTABLES.has(executable)) {
    return `Verification executable is not allowed: ${executable}`;
  }

  if (executable === "git") {
    if (check.argv.length < 2 || !ALLOWED_GIT_VERIFICATION_SUBCOMMANDS.has(check.argv[1])) {
      return `verification[${index}] uses a disallowed git command: ${JSON.stringify(check.argv)}`;
    }
  }

  if (check.cost !== "cheap" && check.cost !== "expensive") {
    return `verification[${index}].cost must be 'cheap' or 'expensive'`;
  }

  if (check.seed_count !== undefined) {
    if (!Number.isInteger(check.seed_count) || check.seed_count <= 0) {
      return `verification[${index}].seed_count must be a positive integer`;
    }
    if (check.seed_count > MAX_AUTOMATED_SEEDS) {
      return `verification[${index}].seed_count=${check.seed_count} exceeds the automated maximum of ${MAX_AUTOMATED_SEEDS}`;
    }
  }

  const seedArgIndex = knownSeedSweepArgIndex(check.argv);
  if (seedArgIndex !== null) {
    if (check.seed_count === undefined && !allowLegacySweeps) {
      return `verification[${index}] is a known game-seed sweep and must declare seed_count`;
    }
    if (check.seed_count !== undefined) {
      if (check.argv.length <= seedArgIndex) {
        return `verification[${index}] omits the known seed-count argv`;
      }
      const argvSeedCount = parseInt(check.argv[seedArgIndex], 10);
      if (isNaN(argvSeedCount)) {
        return `verification[${index}] has a non-integer seed-count argv`;
      }
      if (argvSeedCount !== check.seed_count) {
        return `verification[${index}].seed_count=${check.seed_count} does not match argv seed count ${argvSeedCount}`;
      }
    }
  }

  const timeout = check.timeout_seconds || 300;
  if (!Number.isInteger(timeout) || timeout <= 0) {
    return `Invalid timeout for verification[${index}]`;
  }

  const maxTimeout = check.cost === "expensive"
    ? MAX_EXPENSIVE_TIMEOUT_SECONDS
    : MAX_CHEAP_TIMEOUT_SECONDS;

  if (timeout > maxTimeout) {
    return `verification[${index}] asks for timeout_seconds=${timeout}, but the maximum for cost='${check.cost}' is ${maxTimeout} seconds`;
  }

  return null; // valid
}

export function validatePlan(
  plan: ArchitecturePlan,
  allowLegacySweeps: boolean = false,
): string | null {
  const requiredKeys = [
    "task_interpretation",
    "current_behavior",
    "design",
    "eli5_summary",
    "implementation_steps",
    "verification",
    "documentation",
    "acceptance_criteria",
    "risks",
  ];

  for (const key of requiredKeys) {
    if (!(key in plan)) {
      return `Architecture plan is missing key: ${key}`;
    }
  }

  if (!plan.eli5_summary || !plan.eli5_summary.trim()) {
    return "Architect eli5_summary must be a non-empty string";
  }

  if (!Array.isArray(plan.implementation_steps)) {
    return "plan.implementation_steps must be a list";
  }

  if (!Array.isArray(plan.verification)) {
    return "plan.verification must be a list";
  }

  for (let i = 0; i < plan.verification.length; i++) {
    const err = validateVerificationCheck(plan.verification[i], i + 1, allowLegacySweeps);
    if (err) return err;
  }

  return null;
}

// ============================================================================
// Review validation
// ============================================================================

export function validateReview(
  review: ReviewResult,
  allowLegacy: boolean = false,
): string | null {
  if (review.verdict !== "PASS" && review.verdict !== "FIX") {
    return "Reviewer verdict must be PASS or FIX";
  }

  if (!review.summary || !review.summary.trim()) {
    return "Reviewer summary must be a non-empty string";
  }

  if (!review.eli5_summary || !review.eli5_summary.trim()) {
    if (!allowLegacy) {
      return "Reviewer eli5_summary must be a non-empty string";
    }
  }

  if (!["LOW", "MEDIUM", "HIGH"].includes(review.uncertainty)) {
    if (!allowLegacy) {
      return "Reviewer uncertainty must be LOW, MEDIUM, or HIGH";
    }
  }

  if (!Array.isArray(review.issues)) {
    return "Reviewer issues must be a list";
  }

  if (review.verdict === "FIX" && review.issues.length === 0) {
    return "Reviewer returned FIX but supplied no issues";
  }

  for (let i = 0; i < review.issues.length; i++) {
    const issue = review.issues[i];
    if (!["CRITICAL", "MAJOR", "MINOR"].includes(issue.severity)) {
      return `Reviewer issue ${i + 1} has invalid severity: ${issue.severity}`;
    }
    for (const key of ["location", "problem", "failure_mechanism", "required_fix"]) {
      if (typeof (issue as any)[key] !== "string") {
        return `Reviewer issue ${i + 1}.${key} must be a string`;
      }
    }
  }

  if (
    review.verdict === "PASS" &&
    review.issues.some((i) => i.severity === "CRITICAL" || i.severity === "MAJOR")
  ) {
    return "Reviewer returned PASS with a CRITICAL or MAJOR issue";
  }

  return null;
}

// ============================================================================
// Seed-sweep argument index
// ============================================================================

export function knownSeedSweepArgIndex(argv: string[]): number | null {
  const exeName = argv[0].split("/").pop()!;
  if (
    exeName === "one_combat" &&
    argv.length >= 2 &&
    argv[1] in KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX
  ) {
    return KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX[argv[1]];
  }
  if (
    (exeName === "python" || exeName === "python3") &&
    argv.length >= 2
  ) {
    const script = argv[1].split("/").pop()!;
    if (script in KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX) {
      return KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX[script];
    }
  }
  return null;
}

/**
 * Validate that a verification command does not exceed MAX_AUTOMATED_SEEDS.
 * Returns the problem description or null.
 */
export function validateSeedCount(argv: string[]): string | null {
  const exeName = argv[0].split("/").pop()!;

  if (exeName === "one_combat" && argv.length >= 2) {
    const relativeIdx = KNOWN_ONE_COMBAT_SEED_SWEEP_ARG_INDEX[argv[1]];
    if (relativeIdx !== undefined && argv.length > relativeIdx) {
      const seeds = parseInt(argv[relativeIdx], 10);
      if (!isNaN(seeds) && seeds > MAX_AUTOMATED_SEEDS) {
        return `${exeName} ${argv[1]} requests ${seeds} seeds; automated maximum is ${MAX_AUTOMATED_SEEDS}`;
      }
    }
  }

  if ((exeName === "python" || exeName === "python3") && argv.length >= 2) {
    const script = argv[1].split("/").pop()!;
    const relativeIdx = KNOWN_PYTHON_SEED_SWEEP_ARG_INDEX[script];
    if (relativeIdx !== undefined && argv.length > relativeIdx + 1) {
      const seeds = parseInt(argv[relativeIdx + 1], 10);
      if (!isNaN(seeds) && seeds > MAX_AUTOMATED_SEEDS) {
        return `${script} requests ${seeds} seeds; automated maximum is ${MAX_AUTOMATED_SEEDS}`;
      }
    }
  }

  return null;
}

// ============================================================================
// Escalation decision logic
// ============================================================================

export interface EscalationInput {
  changedPaths: string[];
  changedLines: number;
  trackedFileCount: number;
  plan: ArchitecturePlan;
  verificationHistory: VerificationReport[];
  lunaReviews: ReviewResult[];
  latestLunaReview: ReviewResult;
  confirmedTrivial?: boolean;
}

export function shouldEscalate(input: EscalationInput): {
  escalated: boolean;
  reasons: string[];
} {
  const reasons: string[] = [];
  const { changedPaths, changedLines, trackedFileCount, plan, verificationHistory, lunaReviews, latestLunaReview, confirmedTrivial = false } = input;

  if (!confirmedTrivial) {
    for (const [concept, fragments] of Object.entries(HIGH_RISK_PATH_RULES)) {
      if (
        changedPaths.some(
          (path) =>
            !path.startsWith("docs/") &&
            fragments.some((fragment) => path.toLowerCase().includes(fragment)),
        )
      ) {
        reasons.push(`high-risk subsystem changed: ${concept}`);
      }
    }

    const planText = JSON.stringify({
      design: plan.design,
      risks: plan.risks,
      acceptance_criteria: plan.acceptance_criteria,
    }).toLowerCase();

    for (const [concept, terms] of Object.entries(HIGH_RISK_PLAN_TERMS)) {
      if (terms.some((term) => planText.includes(term))) {
        reasons.push(`architect identified high-risk concept: ${concept}`);
      }
    }
  }

  if (changedLines > 300) {
    reasons.push(`change size exceeds 300 lines: ${changedLines}`);
  }

  if (trackedFileCount > 8) {
    reasons.push(`change spans more than 8 tracked files: ${trackedFileCount}`);
  }

  if (
    verificationHistory.some((report) =>
      report.checks.some(
        (check) => check.required && (check.status === "FAIL" || check.status === "TIMEOUT"),
      ),
    )
  ) {
    reasons.push("required verification failed earlier in this session");
  }

  if (
    lunaReviews.some((review) =>
      review.issues.some((issue) => issue.severity === "CRITICAL"),
    )
  ) {
    reasons.push("a cheap review reported a CRITICAL issue");
  }

  if (
    lunaReviews.some(
      (review) =>
        review.issues.filter((issue) => issue.severity === "MAJOR").length >= 2,
    )
  ) {
    reasons.push("a cheap review reported at least two MAJOR issues");
  }

  if (latestLunaReview.uncertainty === "HIGH") {
    reasons.push("reviewer uncertainty is HIGH");
  }

  // Deduplicate while preserving order.
  const unique = [...new Set(reasons)];
  return { escalated: unique.length > 0, reasons: unique };
}

// ============================================================================
// Trivial plan creation
// ============================================================================

export function createTrivialPlan(task: string): ArchitecturePlan {
  const firstLine = task.trim().split("\n")[0].substring(0, 120);
  return {
    task_interpretation: `Non-behavioral change: ${firstLine}`,
    current_behavior: "Unchanged; only comments/docs/formatting are affected.",
    design: "Trivial non-behavioral edit (fast path).",
    eli5_summary:
      "It fixes wording, comments, or formatting without changing what the code actually does.",
    implementation_steps: [
      {
        description: "Implement only the exact non-behavioural edit the task requests.",
        files: [],
        symbols: [],
        invariants: ["Do not alter executable semantics.", "No opportunistic cleanup."],
      },
    ],
    verification: [
      {
        name: "git diff --check",
        argv: ["git", "diff", "--check"],
        cwd: ".",
        env: {},
        required: true,
        cost: "cheap",
        timeout_seconds: 30,
      },
    ],
    documentation: [],
    acceptance_criteria: [
      "git diff --check passes.",
      "Changed lines are comment / docstring / whitespace only.",
      "No behavioural / semantic changes.",
    ],
    risks: [],
  };
}
