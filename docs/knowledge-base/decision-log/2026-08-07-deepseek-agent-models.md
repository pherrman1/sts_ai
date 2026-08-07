# 2026-08-07 — DeepSeek-only agent models

Date: 2026-08-07
Session/task: Switch the workflow's review agents from OpenAI models to DeepSeek.

## Decision

- architect and reviewer (Luna role): `deepseek/deepseek-v4-pro` with `reasoningEffort: high`.
- reviewer_sol (Sol role): `deepseek/deepseek-reasoner` with no explicit reasoning effort, so it runs at its native full-reasoning mode.
- implementer: unchanged `deepseek/deepseek-v4-flash`.

## Rationale

`opencode/gpt-5.6-luna` and `opencode/gpt-5.6-sol` do not resolve in this
setup (`Model not found`, `opencode models` lists them only as
`openai/gpt-5.6-*`); the user decided to use DeepSeek for everything for now.

## Alternatives considered

- `openai/gpt-5.6-luna` + `openai/gpt-5.6-sol` — rejected by the user's choice to move to DeepSeek.
- `reasoningEffort: "max"` on reviewer_sol — rejected because opencode's valid effort values are `minimal|low|medium|high`; the reasoner model already provides max-strength reasoning natively.

## Evidence

- `opencode.json` + `architect`, `reviewer`, `reviewer_sol` agent configuration.
- `opencode models` + resolution check of the three model IDs.
- `opencode debug config` + merged configuration output.

## Status and follow-up

- Implemented. Session `.ai/20260807-211018` can resume `--continue-rejected` with the DeepSeek Sol adjudicator.

## Superseded (same day)

- reviewer_sol changed from `deepseek/deepseek-reasoner` to `deepseek/deepseek-v4-pro` with `reasoningEffort: max`.
- reviewer changed from `deepseek/deepseek-v4-pro` to `deepseek/deepseek-v4-flash` with `reasoningEffort: high`.
- implementer now sets `reasoningEffort: high` on the unchanged `deepseek/deepseek-v4-flash`.
- Final mapping: architect `deepseek-v4-pro` high; implementer `deepseek-v4-flash` high; cheap reviewer `deepseek-v4-flash` high; escalation reviewer (Sol) `deepseek-v4-pro` max. "Flash 0731" refers to the `deepseek-v4-flash` model itself, not a separate dated id.

## Addendum (same day)

- Agent renamed from `reviewer_sol` to `reviewer_escalation` (config key, prompt file `reviewer-escalation.md`, spawn name, and user-facing labels/help); the "Luna"/"Sol" terminology is dropped from prompts and prints. Legacy artifact stems (`sol-review-*.json`, `recovery-sol-review`) and internal identifiers remain for resume compatibility.
- `ai_cycle.py` now records per-agent-call cost by reading opencode's session database (`~/.local/share/opencode/opencode.db`, `session` rows for this repository directory created during each call). It prints per-call cost, accumulates a `costs.json` in the session directory, and prints an end-of-run cost summary even on failure (e.g. token-outage aborts).

## Addendum 2 (same day)

- Diagnosed the 23:49 "recovery-sol-review call failed" exhaustion: it was NOT a DeepSeek token/money outage. The call billed `$0.0464` on `deepseek-v4-pro` (69k input tokens) and the model completed a full PASS verdict; `opencode run` still exited nonzero (permission denials were repeatedly hit) and the single-attempt guard discarded the paid answer. The 23:33 incident with 0 tokens and `gpt-5.6-luna` was a separate ChatGPT-side failure before the DeepSeek-only switch.
- Fixes: `parse_json_response` now accepts ` ```json `-fenced answers; `obtain_review` recovers a valid review from the transcript of a failed run before writing `recovery-exhausted.json` (a nonzero exit no longer throws away a completed paid review).
- Added denied-tool-call collection: each agent run scans its transcript for permission-blocked attempts and appends them to the session's `denied-tool-calls.md` (aggregated per agent), with counts printed per call and in the end-of-run summary, so rules in `opencode.json` can be reviewed and adjusted after a few cycles.

## Addendum 3 (same day)

- Permission-awareness fix: reviewer/escalation/architect prompts now state exactly which bash commands are allowed (`git status/diff/log/show/grep/blame/ls-files`, one at a time), forbid chaining/pipes/redirection, forbid running tests/builds/`py_compile`/self-tests (verification belongs to the orchestrator), and point to the built-in read/grep/glob tools. `git ls-files *` was added to the allow rules for the three read-only agents. The orchestrator also injects the changed-file list into every review prompt so reviewers do not need `git status`/`git diff --name-only`/`git ls-files` for discovery. Rationale: 11 denied calls in one run (mostly `git diff | grep`, `git ls-files`, `python3 -m py_compile`) showed agents learn rules only from error messages; prompting them up front is cheaper than denial-and-retry loops.
