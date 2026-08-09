# AI cycle and agent backends

Last verified: 2026-08-09 against the current working tree.

## Purpose

Pi-native `/sts-cycle` in `.pi/extensions/sts-cycle/` is the authoritative
deterministic orchestrator. It runs the architect → implementer → cheap
verification → reviewer → optional escalation audit → final expensive
verification workflow. Repository safety and review policy stays in code, not
prompts or the parent LLM. `tools/ai_cycle.py` remains the legacy rollback.

## Current implementation

Pi-native invocations go through `invokeAgent()` in
`.pi/extensions/sts-cycle/index.ts`. It launches:

`pi --mode json -p --no-session --approve --no-extensions --extension
.pi/extensions/sts-tools.ts --extension .pi/extensions/sts-safety.ts --model
<role-model> [--tools read,grep,find,ls,sts_git,sts_inspect]
--append-system-prompt <role-prompt-body> @<attached files> "Task: ..."`

`--no-extensions` prevents unrelated discovered extensions from changing a
child's behavior; the two required extensions still load explicitly. The
shared runner parses JSONL stdout. Assistant `message_end` events provide the
final response and cost; lifecycle deltas drive the progress widget.

Agent definitions and role models are loaded from `.pi/agents/*.md`
frontmatter, which is the Pi-native source of truth:

| Role | Model | Tools |
| --- | --- | --- |
| architect | `deepseek/deepseek-v4-pro:high` | read, grep, find, ls, sts_git, sts_inspect |
| implementer | `deepseek/deepseek-v4-flash:high` | normal tools; destructive commands denied by `sts-safety.ts` |
| reviewer | `deepseek/deepseek-v4-flash:high` | read, grep, find, ls, sts_git, sts_inspect |
| reviewer_escalation | `deepseek/deepseek-v4-pro:xhigh` | read, grep, find, ls, sts_git, sts_inspect |

The read-only roles never receive Bash. Prompt frontmatter is stripped before
the body is passed as the appended system prompt.

The legacy `tools/ai_cycle.py` selects an `AgentBackend`:

- `OpenCodeBackend` — launches `opencode run --auto --agent <role> --dir
  <root> [--file ...] -- <prompt>`; the legacy runtime, kept as the rollback
  path. Permission rules for it live in `opencode.json`; prompts in
  `.opencode/prompts/*.md`.
- `PiBackend` — launches
  `pi --mode json -p --no-session --approve --extension
  .pi/extensions/sts-tools.ts --extension .pi/extensions/sts-safety.ts
  --model <role-model> [--tools read,grep,find,ls,sts_git,sts_inspect]
  --append-system-prompt <role-prompt-body> @<attached files> "Task: ..."`
  and parses the JSONL event stream on stdout. `message_end` events with
  role `assistant` supply the final response and usage/cost; tool blocks
  surface as error `tool_result_end` events whose text is the
  sts-safety reason and are recorded in the session's
  `denied-tool-calls.md`.
- `AgentBackend` — abstract base; `select_backend(name)` constructs either
  concrete backend.

Interactive Pi observability: `.pi/extensions/subagent/index.ts` is an
**STS-local fork** of Pi's reference subagent extension (base commit
`c185d412382581860a489b4959737bad1d119492`, see the `STS-LOCAL FORK` header
comment). The fork adds live activity to the subagent tool's collapsed and
expanded rendering — agent + model, current turn,
waiting/thinking/responding/running-a-tool status, the current tool with
concise args, recent completed tool calls, and usage so far — driven by Pi's
JSON lifecycle events (`turn_start`, `message_update`,
`tool_execution_start/end`, `agent_end`). `message_update` refreshes are
throttled to ~150 ms; tool start/end are immediate; `message_end` remains
authoritative. Reasoning/thinking contents are never displayed.
`scripts/install_pi_subagent.sh` refuses to overwrite the fork unless
`STS_FORCE_PI_SUBAGENT=1`; `scripts/check_pi_setup.sh` detects the fork
marker and does not claim byte-identity.

Pi-native `/sts-cycle` and the interactive `subagent` tool share
`.pi/extensions/subagent/runner.ts::runPiChild`. The runner always drains and
parses the child's JSONL stdout through completion. To bound memory, it may
stop retaining high-volume `message_update` deltas after 1 MiB, but it still
forwards every parsed event to live progress and always retains lifecycle and
completed-message events. This distinction is required because Pi emits one
JSON event per thinking/text delta; stopping stdout processing at the retention
limit previously hid final `message_end` and `agent_end` events and made long
architect runs appear frozen. Role-specific idle timeouts are measured between
parsed events and are armed at process start; hard timeouts remain independent.
`/sts-cycle` writes `ARCHITECT` to `state.json` before invoking the child, and
its one-second UI heartbeat advances elapsed time without affecting idle
detection.

## Important data flow

1. The `/sts-cycle` handler creates `.ai/cycles/<timestamp>/`, writes the task,
   and runs clean-tree preflight before any child LLM call.
2. `runCycle()` performs deterministic state transitions. `policy.ts` owns
   task classification, plan/review validation, escalation, protected paths,
   seed limits, and verification allowlists; `verification.ts` executes checks.
3. `invokeAgent()` loads the role body/model from `.pi/agents/`, attaches cycle
   artifacts, and delegates process lifecycle to `runPiChild()`.
4. JSON lifecycle events update the widget without showing reasoning contents.
   Completed assistant messages supply structured JSON or implementer output;
   costs and cycle artifacts are written into the session directory.
5. The legacy Python entry point separately parses `--backend
   {opencode,pi}` (default `opencode`) and retains transcript recovery and
   backend comparison behavior as the rollback path.

## Invariants and assumptions

- The Pi-native state machine and `policy.ts` are authoritative for: clean-tree start,
  128-seed cap (`MAX_AUTOMATED_SEEDS`), verification allowlisting and
  cheap/expensive handling, retry limits (`MAX_IMPLEMENTATION_RETRIES`,
  `MAX_REVIEW_ROUNDS`, `MAX_SOL_REVIEW_ROUNDS`, `MAX_EXPENSIVE_REPAIRS`),
  escalation classification, ELI5 artifacts, and cycle state persistence.
  `sts-safety.ts` is defense in depth only. Transcript recovery markers and
  some process-level documentation requirements remain legacy/manual concerns.
  The legacy Python policy remains a rollback implementation.
- Plan verification argv[0] must be one of `ALLOWED_VERIFICATION_EXECUTABLES`
  (cmake, ctest, git, python, python3, pytest) or a repository-relative
  `./executable`; git checks are limited to
  `ALLOWED_GIT_VERIFICATION_SUBCOMMANDS`. Both architect prompts enumerate
  this allowlist so plans comply at generation time
  (`BackendSafetySyncTests::test_architect_prompt_documents_verification_allowlist`
  keeps prompt and code in sync).
- `/sts-cycle` children pass `--approve`, `--no-extensions`, and explicit
  `--extension` paths for `sts-tools.ts` and `sts-safety.ts`.
- Pi's `:xhigh` thinking suffix on DeepSeek parses and clamps to `max` at
  request time (DeepSeek supports high/max only) — verified from Pi source,
  not a live run.
- A nonzero Pi exit or an `error`/`aborted` stop reason raises; the log may
  still contain a complete paid answer, which `obtain_review`'s
  failed-run recovery re-parses.
- Pi has no `--` terminator; prompts are prefixed `Task: ` so they are never
  parsed as flags or `@file` attachments.
- The legacy Python Pi backend stores complete raw JSONL in its session log for
  transcript recovery. Pi-native `/sts-cycle` keeps bounded parsed event
  history in memory and writes structured cycle artifacts.
- Child stdout must continue to be parsed after event-history retention reaches
  its cap. `message_end` and `agent_end` are authoritative and must never be
  dropped; `runner.test.mjs` covers a final response after more than 1 MiB of
  token-delta events.

## Relevant code

- `.pi/extensions/sts-cycle/index.ts`: `runCycle`, `invokeAgent`, state handlers,
  progress UI, role-specific timeouts.
- `.pi/extensions/sts-cycle/policy.ts`, `verification.ts`, `artifacts.ts`,
  `git-state.ts`, `types.ts`: deterministic policy, checks, persistence, and
  state schema.
- `.pi/extensions/subagent/runner.ts`: shared child lifecycle and JSONL parser.
- `tools/ai_cycle.py` (legacy rollback): `AgentBackend`, `OpenCodeBackend`, `PiBackend`,
  `select_backend`, `run_agent`, `pi_final_response`,
  `pi_cost_entries_from_events`, `extract_pi_denied_calls`,
  `pi_agent_prompt_body`, `pi_format_tool_call`, `pi_live_status_line`,
  `PI_MODEL_DISPLAY_NAME`, `PROTECTED_WORKFLOW_PATHS`, `--backend`.
- `tools/test_ai_cycle.py`: `PiBackendUnitTests`, `PiLiveStreamingTests`,
  `PiBackendCycleTests`, `BackendSafetySyncTests` (fake
  `subprocess.Popen`, no API calls).
- `.pi/agents/*.md`, `.pi/extensions/sts-tools.ts`,
  `.pi/extensions/sts-safety.ts`, `.pi/extensions/subagent/index.ts`
  (STS-local fork of Pi reference, see `STS-LOCAL FORK` header),
  `.pi/prompts/sts-investigate.md`, `scripts/install_pi_subagent.sh`,
  `scripts/check_pi_setup.sh`.
- `.pi/extensions/subagent/runner.test.mjs`: subprocess lifecycle regression
  for JSONL streams larger than the retained-event cap.

## Fast-path workflow (trivial non-behavioral tasks)

Added 2026-08-08.  The orchestrator classifies every new task
*deterministically* (no LLM call) before the architect stage.  Tasks that
are clearly comment / docstring / typo / spelling / grammar /
wording-only / documentation-only / formatting-only changes **and**
(for source-code comment/docstring tasks) explicitly constrain behaviour
may take a reduced path:

```
TRIVIAL_CANDIDATE
  deterministic classification
  -> Flash implementer
  -> post-implementation diff confirmation (comment/docstring/whitespace only)
  -> cheap deterministic verification (git diff --check)
  -> Flash reviewer
  -> PASS => accepted
  -> no architect, no Pro escalation
```

Classification is narrow and conservative.  A task that mentions any
semantic operation (implement, bug fix, refactor, train, inference, RNG,
etc.) is immediately classified NORMAL.  Uncertainty falls back to
NORMAL.

Post-implementation diff confirmation is mandatory: the orchestrator
parses `git diff HEAD` and verifies every changed line in every source
file is a comment, docstring, or blank line (documentation files allow
normal prose).  At most 2 files and 50 changed lines are permitted; any
config / build / schema / protected path change rejects immediately.  If
the diff cannot be confidently proven trivial the fast path aborts and
the task must be rerun through the normal cycle.

`shouldEscalate()` suppresses soft path/name triggers for a confirmed trivial
diff, but retains hard safety rules: required verification failure, CRITICAL
review issues, reviewer uncertainty HIGH, and explicit safety failures still
escalate. The legacy rollback implements the equivalent rule in
`should_escalate_to_sol()`.

Fast-path policy is implemented by `classifyTask()`, `createTrivialPlan()`,
`confirmTrivialDiff()`, `shouldEscalate()`, and the `runCycle()` fast-path
branch. The legacy Python rollback retains corresponding snake_case helpers.

Session artefacts: `task-classification.json`, `diff-confirmation.json`.

## Known limitations

- `tools/ai_cycle.py` still defaults to its OpenCode rollback backend; this does
  not change the authority of the Pi-native `/sts-cycle` command.
- Pi cost figures come from the model usage reported by Pi itself; OpenCode
  costs come from the opencode session database. The two backends are not
  directly comparable per call.
- `scripts/check_pi_setup.sh` reports failure when no provider auth is
  configured because Pi hides unauthenticated models from `--list-models`.
- `pi update --models` refreshes the model catalog; if the catalog IDs
  change, update the `model:` lines in `.pi/agents/*.md`; update the legacy
  routing table in `tools/ai_cycle.py` only while that rollback remains.
- `.pi/extensions/subagent/index.ts` diverges from the pinned upstream Pi
  commit (live observability fork). Upstream changes to the reference
  subagent extension must be re-merged by hand; `install_pi_subagent.sh`
  refuses to overwrite the fork without `STS_FORCE_PI_SUBAGENT=1`.

## Open questions

- Legacy rollback only: whether the model reliably emits single-line JSON for
  `parse_json_response`'s trailing-object scan on Pi logs; multi-line JSON is
  handled only when the answer is the last content of the log.

## Related

- Decision log:
  `docs/knowledge-base/decision-log/2026-08-08-pi-backend-integration.md`,
  `docs/knowledge-base/decision-log/2026-08-08-pi-live-observability.md`,
  `docs/knowledge-base/decision-log/2026-08-08-fast-path-workflow.md`,
  `docs/knowledge-base/decision-log/2026-08-09-pi-runner-stdout-cap.md`
