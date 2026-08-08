# AI cycle and agent backends

Last verified: 2026-08-08 against the current working tree.

## Purpose

`tools/ai_cycle.py` is the deterministic orchestrator that runs the
architect → implementer → cheap verification → reviewer → optional escalation
audit → final expensive verification workflow. It owns the repository-specific
safety and review policy and must not delegate it to prompts or the parent
LLM. This page documents how the cycle invokes agent runtimes and how the
backend is selected.

## Current implementation

Every agent invocation goes through `run_agent()` in
`tools/ai_cycle.py`, which forwards to the active `AgentBackend`:

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

Role routing under Pi (deterministic table `PI_MODEL_BY_ROLE` /
`PI_READONLY_TOOLS` in `tools/ai_cycle.py`):

| Role | Model | Tools |
| --- | --- | --- |
| architect | `deepseek/deepseek-v4-pro:high` | read, grep, find, ls, sts_git, sts_inspect |
| implementer | `deepseek/deepseek-v4-flash:high` | all normal tools; destructive commands denied by `sts-safety.ts` |
| reviewer | `deepseek/deepseek-v4-flash:high` | read, grep, find, ls, sts_git, sts_inspect |
| reviewer_escalation | `deepseek/deepseek-v4-pro:xhigh` | read, grep, find, ls, sts_git, sts_inspect |

The architect/reviewer/escalation roles never receive bash, so a failing
extension cannot weaken them to arbitrary Bash.

Pi prompt bodies are read from `.pi/agents/*.md` with YAML frontmatter
stripped (`pi_agent_prompt_body`); `reviewer_escalation` uses
`reviewer-pro.md`. The same files drive interactive Pi through the vendored
subagent extension (`.pi/extensions/subagent/`); `@file` attachments
substitute for OpenCode's `--file`.

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

## Important data flow

1. `main()` parses `--backend {opencode,pi}` (default `opencode`), selects
   `ACTIVE_BACKEND`, then enforces `ensure_safe_start()` before any agent
   invocation (dirty tracked tree → abort before any LLM call).
2. Architect/reviewer/escalation prompts are role bodies from `.pi/agents/`
   plus per-call task text; implementer calls attach task/plan/report files.
3. Pi runs print a model-bearing banner and stream concise lifecycle status
   lines (`[role] model thinking...`, `[role] tool: read <path>:<range>`,
   `[role] tool done`, `[role] model responding...`) while the full raw
   JSONL stream is written verbatim to the session log. Status is
   lifecycle-only: thinking/text deltas never print content, and the
   thinking/responding transition is printed once per response
   (`pi_live_status_line`, `pi_format_tool_call`). The extracted final
   response is appended to the session log after
   `===== PI FINAL RESPONSE BEGIN =====` as the last content, so
   `parse_json_response`-based recovery on paid transcripts works exactly
   as for OpenCode logs.
4. Cost/usage from Pi `message_end` events is recorded in the session's
   `costs.json` with the same schema OpenCode's sqlite rows produce; denied
   tool calls go to `denied-tool-calls.md`.
5. `run_implementer_agent` snapshots `PROTECTED_WORKFLOW_PATHS` (OpenCode
   config/prompts, `tools/*`, and the `.pi/` control plane) before the call
   and restores byte-for-byte afterwards.

## Invariants and assumptions

- The deterministic Python policy is authoritative for: clean-tree start,
  128-seed cap (`MAX_AUTOMATED_SEEDS`), verification allowlisting and
  cheap/expensive handling, retry limits (`MAX_IMPLEMENTATION_RETRIES`,
  `MAX_REVIEW_ROUNDS`, `MAX_SOL_REVIEW_ROUNDS`, `MAX_EXPENSIVE_REPAIRS`),
  escalation classification, recovery markers, ELI5 artifacts, and
  experiment/decision-log requirements. `sts-safety.ts` is defense in depth
  only.
- `--backend pi` children always pass `--approve` and explicit `--extension`
  paths for `sts-tools.ts` and `sts-safety.ts`; Pi dedupes these with
  trust-discovery paths.
- Pi's `:xhigh` thinking suffix on DeepSeek parses and clamps to `max` at
  request time (DeepSeek supports high/max only) — verified from Pi source,
  not a live run.
- A nonzero Pi exit or an `error`/`aborted` stop reason raises; the log may
  still contain a complete paid answer, which `obtain_review`'s
  failed-run recovery re-parses.
- Pi has no `--` terminator; prompts are prefixed `Task: ` so they are never
  parsed as flags or `@file` attachments.
- Pi terminal output is lifecycle status only; the complete raw JSONL stream
  lives in the session log (`*.log`) for forensic debugging, and the
  extracted final response is appended to it for log-based recovery.

## Relevant code

- `tools/ai_cycle.py`: `AgentBackend`, `OpenCodeBackend`, `PiBackend`,
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

## Known limitations

- `DEFAULT_BACKEND` is still `opencode`; flipping it to `pi` requires the
  live bake-off verification (API key) and a test re-run.
- Pi cost figures come from the model usage reported by Pi itself; OpenCode
  costs come from the opencode session database. The two backends are not
  directly comparable per call.
- `scripts/check_pi_setup.sh` reports failure when no provider auth is
  configured because Pi hides unauthenticated models from `--list-models`.
- `pi update --models` refreshes the model catalog; if the catalog IDs
  change, update only the `model:` lines in `.pi/agents/*.md` and the
  routing table in `tools/ai_cycle.py`.
- `.pi/extensions/subagent/index.ts` diverges from the pinned upstream Pi
  commit (live observability fork). Upstream changes to the reference
  subagent extension must be re-merged by hand; `install_pi_subagent.sh`
  refuses to overwrite the fork without `STS_FORCE_PI_SUBAGENT=1`.

## Open questions

- Whether the model reliably emits single-line JSON for
  `parse_json_response`'s trailing-object scan on Pi logs; multi-line JSON
  is handled only when the answer is the last content of the log.

## Related

- Decision log:
  `docs/knowledge-base/decision-log/2026-08-08-pi-backend-integration.md`,
  `docs/knowledge-base/decision-log/2026-08-08-pi-live-observability.md`
