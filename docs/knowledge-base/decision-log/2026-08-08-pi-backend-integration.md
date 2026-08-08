# 2026-08-08 — Pi backend for the AI cycle (migration phase 1-6)

Date: 2026-08-08
Session/task: Implement the Pi coding-agent integration described in
`PI_INTEGRATION_HANDOFF.md`: install the `.pi` starter resources, add a
provider-neutral agent backend abstraction to `tools/ai_cycle.py`, implement a
Pi child-process backend in JSON mode, keep the OpenCode backend as the
rollback path, and extend `tools/test_ai_cycle.py` so the Pi backend is
covered without API calls.

## Decision

- `tools/ai_cycle.py` now dispatches every agent invocation through an
  `AgentBackend` abstraction (`AgentBackend` / `OpenCodeBackend` /
  `PiBackend` in `tools/ai_cycle.py`). `run_agent()` keeps its signature and
  forwards to `ACTIVE_BACKEND`.
- Default backend stays `opencode` (`DEFAULT_BACKEND = "opencode"`); `pi` is
  opt-in via `--backend pi`. The default is flipped only after the live
  end-to-end bake-off (handoff Phase 7-8) passes.
- The Pi backend launches `pi --mode json -p --no-session --approve
  --model <role-model> [--tools read,grep,find,ls,sts_git,sts_inspect]
  --append-system-prompt <role-prompt-body> @<files...> "Task: ..."` and
  parses the JSONL event stream (`message_end` assistant messages). It
  enforces: role model routing (architect `deepseek/deepseek-v4-pro:high`,
  implementer/reviewer `deepseek/deepseek-v4-flash:high`,
  reviewer_escalation `deepseek/deepseek-v4-pro:xhigh`); read-only tool
  allowlists for architect/reviewer/reviewer_escalation (no bash); optional
  timeout with SIGTERM then SIGKILL; non-zero exit and
  `stopReason`-error/aborted treated as failure; cost/usage recorded from the
  event stream into the same `costs.json` schema; sts-safety block reasons
  recorded in `denied-tool-calls.md`.
- Pi session logs keep the raw JSONL stream and append the extracted final
  response as the last content after `===== PI FINAL RESPONSE BEGIN =====`,
  so the existing log-based recovery paths (`parse_json_response` on paid
  transcripts, `recover_completed_implementer_summary`) work unchanged for
  Pi runs.
- Prompt bodies are read from `.pi/agents/*.md` with YAML frontmatter
  stripped (`pi_agent_prompt_body`); `reviewer_escalation` uses the stronger
  `reviewer-pro.md` body. The `.opencode/prompts/*.md` files remain
  authoritative for the OpenCode rollback path.
- The `.pi/` control plane (agents, extensions, prompts) was added to
  `PROTECTED_WORKFLOW_PATHS` and is restored byte-for-byte after every
  implementer invocation, mirroring `PROTECTED_PATHS` in
  `.pi/extensions/sts-safety.ts`.
- The starter `.pi` resources were installed as supplied: five agent files
  (architect, implementer, investigator, reviewer, reviewer-pro), custom
  tools `sts_git`/`sts_inspect` (`sts-tools.ts`), the defense-in-depth
  `sts-safety.ts` hook, the `sts-investigate.md` prompt template, and the two
  setup scripts. The vendored reference subagent extension
  (`.pi/extensions/subagent/`) already matched the pinned Pi commit
  `c185d412382581860a489b4959737bad1d119492` byte-for-byte.

## Rationale

- Backend refactor, not rewrite: all orchestration semantics (retry limits,
  escalation, ELI5, seed cap, dirty-tree refusal, recovery, verification
  allowlisting) live in the same functions as before; only the agent process
  invocation is behind the backend seam. This preserves the deterministic
  STS policy layer, which must not move into prompts (handoff Phase 5).
- JSON mode over RPC: the official reference subagent extension already
  proves `--mode json -p --no-session` streams parseable `message_end`/
  `tool_result_end` events; JSON mode keeps streaming, timeout, abort, and
  final-response parsing in one place without a new lifecycle protocol
  (handoff Phase 4).
- `--approve` plus explicit `--extension` paths for the two STS extensions
  make child processes deterministic even before a project-trust decision is
  recorded; Pi dedupes the same paths when trust discovery also loads them
  (`mergePaths` in `resource-loader.ts`). Read-only roles never receive
  bash, so a loading failure cannot weaken them to arbitrary Bash (handoff
  Phase 4 fallback rule).
- `--backend pi` before dirty-tree refusal means `ensure_safe_start()` still
  runs before any LLM invocation in both backends (verified).
- xhigh on DeepSeek: the Pi catalog maps DeepSeek thinking levels to
  high/max only; `:xhigh` parses and clamps to `max` at request time
  (`clampThinkingLevel` in pi-ai `models.ts`), matching the handoff's
  "xhigh/max-equivalent" routing. **Inference**: no live API run was
  possible in this session (no `DEEPSEEK_API_KEY` in the environment), so
  the clamp behaviour is verified from source only.

## Alternatives considered

- RPC mode — rejected: JSON mode is sufficient and matches the reference
  subagent implementation; RPC adds a protocol dependency without benefit
  here.
- Parse `.pi/agents/*.md` frontmatter for model/tools inside `ai_cycle.py`
  — rejected: the deterministic cycle keeps an explicit routing table
  (`PI_MODEL_BY_ROLE`, `PI_READONLY_TOOLS`) so its configuration is
  inspectable and testable; the markdown files stay the prompt source of
  truth for both interactive Pi and the deterministic cycle.
- Write the prompt body into the session directory — rejected: a temp file
  avoids polluting the durable session artifacts and is removed in
  `finally`.
- Appending a trailing `===== PI FINAL RESPONSE END =====` marker to Pi
  logs — rejected after tests: the trailing-object scan in
  `parse_json_response` needs the model's JSON answer to be the last
  content in the file, so the extracted response runs from the BEGIN marker
  to end of file.

## Evidence

- `tools/ai_cycle.py`: `AgentBackend`, `OpenCodeBackend`, `PiBackend`,
  `select_backend`, `run_agent`, `pi_final_response`,
  `pi_cost_entries_from_events`, `extract_pi_denied_calls`,
  `pi_agent_prompt_body`, `PROTECTED_WORKFLOW_PATHS`, `--backend`.
- `tools/test_ai_cycle.py`: 25 new tests (`PiBackendUnitTests`,
  `PiBackendCycleTests`, `BackendSafetySyncTests`) using a fake
  `subprocess.Popen`; 73 tests total pass with `python3 tools/test_ai_cycle.py`.
- `.pi/agents/*.md`, `.pi/extensions/{sts-tools,sts-safety}.ts`,
  `.pi/extensions/subagent/` (verified identical to Pi commit
  `c185d4123`), `.pi/prompts/sts-investigate.md`, `scripts/install_pi_subagent.sh`,
  `scripts/check_pi_setup.sh`.
- Pi API surface verified against the installed Pi 0.84.1 source at
  `/home/philippherrmann/Documents/pi-source` (pinned commit `c185d4123`):
  JSONL event format (`modes/print-mode.ts`), `message_end` message shape,
  `--append-system-prompt` file resolution (`core/resource-loader.ts`),
  `--tools` allowlist semantics, blocked tool calls as error tool results
  (`agent-loop.ts`), `@file` attachments and the absence of a `--` terminator
  (`cli/args.ts`), extension dedupe (`mergePaths`).
- The model catalog in the installed Pi contains `deepseek-v4-pro` and
  `deepseek-v4-flash` (thinking map high/max only).

## Status and follow-up

- Implemented; tests green. OpenCode remains the default backend.
- Open: live verification requires the human to export `DEEPSEEK_API_KEY`,
  run handoff Phase 1 (`pi --list-models deepseek`, one read-only probe),
  Phase 3 interactive agent tests, and the Phase 7 bake-off; then flip
  `DEFAULT_BACKEND` to `pi`, re-run tests, and update this entry plus the
  knowledge-base page.
- Open: `scripts/check_pi_setup.sh` reports a failure when no provider auth
  is configured (Pi hides unauthenticated models from `--list-models`); it
  is intended for post-key runs.
