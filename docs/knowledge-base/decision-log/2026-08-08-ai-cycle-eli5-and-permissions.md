# 2026-08-08 — Per-agent ELI5 summaries in the AI cycle + permission-rule audit

Date: 2026-08-08
Session/task: (a) add a plain-language (ELI5) summary for every agent call in
`tools/ai_cycle.py` — architect, implementer (each call, including fixes), and
reviewer — plus a final cycle wrap-up with verdict and next steps; (b) audit
all recorded denied tool calls in `.ai/*/denied-tool-calls.md` and decide
whether the permission rules in `opencode.json` should change.

## Decision (a): ELI5 everywhere

- Architect must return `eli5_summary` in its plan JSON
  (`validate_plan` requires it; `upgrade_legacy_eli5` backfills a placeholder
  for pre-change plans so resume works). It is printed right after the
  architecture phase and persisted as `<session>/plan-eli5.md`.
- Implementer must end its final response with an `ELI5` section
  (`implementer.md`); `extract_eli5_section` pulls it from the final markdown,
  `save_summary_with_eli5` stores `<stem>-eli5.md` beside every implementer
  summary (initial implementation, verification fixes, review fixes,
  recovery fixes, expensive fixes) and prints it.
- Reviewer already had `eli5_summary`; unchanged.
- `print_final_eli5` composes a cycle wrap-up from the stored artifacts
  ("what we wanted / what was built / what the reviewer found / verdict /
  what to do next") at ACCEPTED and at semantic-limit rejection.
- Reviewer `eli5_summary` was already validated; the new plan validation
  mirrors the same non-empty-string rule.

## Decision (b): permission-rule audit — two gaps fixed, rest kept

Audited all 6 `.ai/*/denied-tool-calls.md` (28 recorded denials):

- **Warranted, no change (~24):** pipes on already-allowed commands
  (`git diff X | head`, `git grep X | head`, `git show X | head`), `ls`/`wc`
  file inspection, python execution (`py_compile`, `paired_analysis
  --self-test`), chained commands (`git diff ... && git ls-files`).
  The prompts already say output is auto-truncated and bash is
  read-only-git-only; the denials are the rule working.
- **Fixed (2 gaps):**
  1. `git blame *` — the reviewer prompt lists it as allowed but the
     `reviewer`/`reviewer_escalation` permission blocks did not; now allowed
     (prompt/config mismatch resolved in favor of the read-only command).
  2. `git check-ignore *` — read-only, safe, and genuinely needed (the §136
     smoke-.native hygiene review wanted it); now allowed for all three
     read-only agents. Prompt command lists updated to match.
- Rationale: only read-only git inspection is widened; no execution, no
  writes, no network.

## Alternatives considered

- Compose the final ELI5 from an extra cheap model call — rejected: the
  artifacts are already stored; deterministic assembly is free and auditable.
- Add `wc`/`ls` to the allowlists — rejected: built-in read/glob tools cover
  file inspection; widening would invite more chained commands.

## Evidence

- `tools/ai_cycle.py`: `extract_eli5_section`, `save_summary_with_eli5`,
  `save_plan_eli5`, `print_architect_eli5`, `print_final_eli5`,
  `upgrade_legacy_eli5`, `validate_plan` requirement.
- `tools/test_ai_cycle.py`: 11 new tests (`Eli5ArtifactTests` + plan-ELI5
  validation + legacy backfill) — 48 tests pass; `ctest` 9/9; `git diff
  --check` clean.
- `opencode.json` + `.opencode/prompts/{architect,implementer,reviewer}.md`.
- `.ai/*/denied-tool-calls.md` audit (6 sessions, 28 denials).

## Status and follow-up

- Implemented and tested. Next cycle will exercise the new ELI5 output paths.
- Open question: whether the implementer reliably emits the `ELI5` section —
  the fallback text ("No ELI5 section was recorded…") will surface any
  non-compliance.
