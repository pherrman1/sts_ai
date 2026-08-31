# Session retrospective

Last verified: 2026-08-31 against the current working tree.

## Purpose

Review a few recent Codex sessions for recurring waste, failure, or rediscovery,
then route only the smallest evidence-backed repository maintenance. Raw
sessions remain raw evidence; compact recurring lessons live in
[`session-retrospective-lessons.md`](session-retrospective-lessons.md); canonical
project truth remains in source, tests, `CODE_MAP.md`, the maintained KB,
experiment ledgers, and decision records.

This is a manual maintenance workflow, not an agent framework:

```text
3–8 substantial Codex sessions
        ↓
user asks: "review my last few sts_ai sessions"
        ↓
Codex invokes session-retrospective
        ↓
read recent sessions + existing lessons
        ↓
find recurring problems; check whether already solved
        ↓
classify remedy
        ↓
small maintenance diff → focused verification → normal draft PR
```

There is no scheduler, automatic session-end execution, daemon, automatic
rewrite, adoption, commit, or merge.

## Session selection

Codex stores normal sessions below `~/.codex/sessions/` and archived sessions
below `~/.codex/archived_sessions/`. The installed CLI has interactive history
pickers but no supported metadata-only JSON listing. Use:

```bash
python tools/agent/recent_codex_sessions.py --project . --limit 5 --json
```

The helper reads only the first `session_meta` record, searches both locations,
prefers sessions whose recorded working directory belongs to this checkout,
deduplicates session IDs, sorts newest first, and emits selection metadata—not
transcript bodies. It performs no network access. Review only the requested
small set and avoid secrets or unnecessary transcript excerpts in reports.

## Decision and routing rule

Propose a repository change only for a recurring or high-cost issue with
concrete session evidence that is not already solved or documented and has a
small durable intervention. One occurrence is usually `NO_ACTION`; two are a
candidate only when expensive or risky; three or more similar occurrences are
a strong candidate. This guides judgment rather than acting as a statistical
test.

Classify remedies as `SKILL`, `KB`, `CODE_MAP`, `WORKFLOW`, `TOOLING`,
`EVALUATOR`, `DELETE_SIMPLIFY`, or `NO_ACTION`. Prefer pointing to existing
knowledge, one paragraph or short rule, reusing a script or preset, or deleting
obsolete machinery before creating a helper. Update the lessons file only for
patterns that are repeated, costly, or clearly high-impact; route durable facts
to their canonical destination in the same change.

## SkillOpt-Sleep boundary

```text
SkillOpt-Sleep:        optimize codex-implementation/SKILL.md
                       bounded proposal + held-out internal validation
Session retrospective: decide whether the durable remedy belongs in a skill,
                       KB, routing, helper, evaluator, or deletion/simplification
```

When the remedy is specifically a learned procedural rule for
`codex-implementation/SKILL.md`, recommend running SkillOpt-Sleep rather than
manually editing `## Learned guidance`, unless the user explicitly requests the
manual edit. Neither path adopts changes automatically.

## Concise report example

```text
Reviewed: 5 sessions

Pattern A — Observed: 3/5
Issue: rediscovered the same worktree submodule repair.
Existing canonical documentation: yes
Action: NO_ACTION — already documented; improve routing only if recurrence persists.

Pattern B — Observed: 2/5
Issue: full C++ build for Python-only changes.
Action: SKILL — send one candidate learned rule to SkillOpt-Sleep.

Pattern C — Observed: 3/5
Issue: manually reconstructed the same artifact-inspection command.
Action: TOOLING — add a tiny existing-tools wrapper only if none exists.
```

This report is maintenance evidence, not proof of improved agent quality.

## Relevant code

- `.agents/skills/session-retrospective/SKILL.md`
- `docs/knowledge-base/operations/session-retrospective-lessons.md`
- `tools/agent/recent_codex_sessions.py`
- `tests/agent/test_recent_codex_sessions.py`
- `docs/knowledge-base/operations/skillopt-sleep.md`
