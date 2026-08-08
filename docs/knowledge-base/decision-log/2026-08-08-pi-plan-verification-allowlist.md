# 2026-08-08 — Pi plan verification allowlist: failed session salvage + prompt gap fix

Date: 2026-08-08
Session/task: Diagnose the failed AI-cycle session `.ai/20260808-204227`
(architect completed, cycle aborted with `ERROR: Verification executable is
not allowed: grep`), salvage the paid plan, and fix the root cause so
plans stop proposing disallowed executables.

## Decision

- **Root cause**: the architect's plan used `["grep", ...]` checks for a
  read-only docs task. `validate_plan` (`tools/ai_cycle.py`,
  `ALLOWED_VERIFICATION_EXECUTABLES = {cmake, ctest, git, python, python3,
  pytest}`) rejects any other argv[0]; the fresh-session path aborts there
  (no plan retry loop), and `--resume` would fail identically because
  `recover_or_load_plan` re-validates the same plan.
- **Salvage**: wrote `.ai/20260808-204227/plan.json` from the paid
  `architect.log` transcript, rewriting the two checks'
  `["grep", ...]` argv to the allowed `["git", "grep", ...]` form
  (`ALLOWED_GIT_VERIFICATION_SUBCOMMANDS` includes `grep`), then ran
  `validate_plan(plan, allow_legacy_sweeps=True)` and wrote `plan-eli5.md`.
  The raw transcript stays untouched as the forensic record; the session is
  resumable with `--resume .ai/20260808-204227` (verified via
  `recover_or_load_plan`).
- **Prompt gap fix**: `.pi/agents/architect.md` and
  `.opencode/prompts/architect.md` verification rules now state that
  argv[0] must be one of `cmake, ctest, git, python, python3, pytest` (or a
  repository-relative `./executable`), that standalone grep/find/sed/awk
  are not allowed (`git grep <pattern> <file>` instead), and that git
  checks are limited to `status, diff, log, show, grep, blame, rev-parse`.
  Both prompts stay in sync with the code allowlist, enforced by a new
  sync test.

## Rationale

- Salvage over rerun: the plan was complete and the only defect was the
  two argv arrays; a human-approved, validator-checked rewrite preserves
  the paid architect answer instead of spending another ~$0.02 and
  re-rolling the plan.
- Prompt fix over allowlist widening: the policy allowlist is deliberately
  narrow (verification is the last deterministic gate before an
  implementer touches the tree); `git grep` already covers the read-only
  need. The gap was that the policy was not communicated to the planner.
- Sync test: a cheap `BackendSafetySyncTests` assertion keeps the
  executable set, the git subcommand set, and the prompt text from
  drifting apart.

## Alternatives considered

- Add `grep` to `ALLOWED_VERIFICATION_EXECUTABLES` — rejected: widens the
  deterministic gate without need; the correct read-only spell is already
  allowed as `git grep`.
- Rerun the architect fresh — rejected: costs tokens and rolls the plan;
  salvage plus a prompt fix addresses both the session and the class of
  failures.
- Edit the paid `architect.log` in place — rejected: corrupts the forensic
  record; the corrected plan lives in `plan.json`, which is the artifact
  the workflow actually consumes.

## Evidence

- `.ai/20260808-204227/`: `architect.log` (paid transcript, untouched),
  `plan.json` (salvaged, `git grep` checks), `plan-eli5.md`, `costs.json`.
- `tools/ai_cycle.py`: `ALLOWED_VERIFICATION_EXECUTABLES`,
  `ALLOWED_GIT_VERIFICATION_SUBCOMMANDS`, `validate_plan`,
  `recover_or_load_plan`.
- `.pi/agents/architect.md`, `.opencode/prompts/architect.md`:
  "Rules for verification" now enumerate the allowlist.
- `tools/test_ai_cycle.py`: `BackendSafetySyncTests::test_architect_prompt_documents_verification_allowlist`;
  85 tests pass (`python3 -m unittest tools.test_ai_cycle`).

## Status and follow-up

- Implemented; session `.ai/20260808-204227` is resumable. Resume runs the
  implementer on top of the current working tree (which contains the
  uncommitted live-observability change) — acceptable for this docs-only
  task; the human decides when to resume.
- Open: the fresh-session path still hard-aborts on an invalid architect
  plan (by design; no auto-retry). The prompt fix should make the failure
  rare; if it recurs, consider an explicit one-shot plan-fix retry with
  the validator's message fed back.
