# SkillOpt-Sleep pilot

Last verified: 2026-08-30 against the current working tree.

## Purpose

Provide a small, on-demand pilot for proposing evidence-backed procedural
improvements to `.agents/skills/codex-implementation/SKILL.md`. SkillOpt is
preview software; proposals remain staged until independent repository
evaluation and human review pass.

## Current implementation

Use `microsoft/SkillOpt` pinned at commit
`db46cd9ae7ce12f1dbd73c945185816aa738751d`. Do not vendor, fork, copy, or add
it as a submodule. The example configuration is
`tools/agent/skillopt_sleep_config.example.json`; replace its absolute target
path only in a local ignored copy.

The pilot is on demand:

```text
3–5 substantial Codex sessions
        ↓
harvest archived Codex sessions
        ↓
inspect and redact mined tasks
        ↓
mock dry-run
        ↓
real Codex-backed SkillOpt run
        ↓
staged skill proposal
        ↓
sts_ai evaluator comparison
        ↓
human review and normal PR
```

There is no cron, hook, session-end trigger, scheduler, or automatic adoption.
Never send unreviewed transcript-derived tasks to a provider-backed run. Keep
the complete staging area and evidence log under ignored local directories
because they can contain transcript-derived content. If useful archived Codex
sessions are unavailable, do not build a harvester: use SkillOpt's reviewed
task-file route or defer the real run.

## Configuration rationale

- `evolve_memory=false` prevents generic `CLAUDE.md` memory creation or edits.
- `edit_budget=1` makes each cycle one attributable procedural proposal.
- `gate_no_regression=true` rejects validation regressions.
- `test_fraction=0.17` supplies diagnostic evidence, not adoption authority.
- `auto_adopt=false` is mandatory for this pilot.
- `recall_k=0` avoids retrieval complexity initially.
- `dream_factor=0` leaves dream augmentation disabled.

Skill evolution targets only the bounded `## Learned guidance` section. The
tracked KB remains authoritative project truth; SkillOpt may not edit it,
`AGENTS.md`, fixed skill workflow text, or other skills.

## Independent evaluation

Follow the two-arm comparison in
[`coding-agent-evals.md`](../evaluation/coding-agent-evals.md). The evaluator
overlays each selected skill into a disposable candidate baseline, removes
hidden `evals/`, and grades repository outcomes independently. The existing
four tasks are only a no-regression smoke.

A proposal is adoptable only when SkillOpt internal validation accepted, the
`sts_ai` evaluator did not regress, human diff review passed, and the change
enters through the normal branch, draft PR, and CI workflow. No KB edit or
skill edit is automatic.

## Known limitations

The pilot does not establish that SkillOpt improves coding quality. Transcript
availability, official Codex integration behavior, provider cost, and the
representativeness of four evaluator tasks remain operational uncertainties.

## Relevant code

- `.agents/skills/codex-implementation/SKILL.md`
- `tools/agent/skillopt_sleep_config.example.json`
- `tools/agent/eval.py`
- `tests/agent/test_agent_eval.py`
- `docs/knowledge-base/evaluation/coding-agent-evals.md`
