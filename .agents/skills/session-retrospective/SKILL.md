---
name: session-retrospective
description: Review a few recent Codex sessions for recurring waste, failure, or rediscovery and route the smallest evidence-backed repository maintenance remedy.
---

# Session retrospective

Use this skill when the user asks to review recent Codex sessions for repeated
inefficiency, rediscovery, failure, or workflow improvement. It complements the
current-session `workflow-retrospective` skill and is not another agent
framework.

Before reviewing, read `AGENTS.md`, `docs/knowledge-base/CODE_MAP.md`,
`docs/knowledge-base/operations/agent-context-and-workflow.md`,
`docs/knowledge-base/operations/skillopt-sleep.md`, and
`docs/knowledge-base/operations/session-retrospective-lessons.md`. Inspect only
the requested small set of recent sessions (normally 3–8); use
`python tools/agent/recent_codex_sessions.py --project . --limit 5 --json` to
select them when needed.

## Method

1. Find repeated waste, failure, or rediscovery—not isolated stylistic
   preferences. Record exact session, PR, commit, command, or outcome evidence
   without copying long transcript excerpts or secrets.
2. Check source, tests, `CODE_MAP.md`, the canonical KB, scripts, presets, skills,
   decisions, and lessons before claiming a gap. Merge duplicate lessons and
   mark resolved history; never treat the lessons file as project truth.
3. Classify each candidate as `SKILL`, `KB`, `CODE_MAP`, `WORKFLOW`, `TOOLING`,
   `EVALUATOR`, `DELETE_SIMPLIFY`, or `NO_ACTION`.
4. Propose a repository change only when the issue is recurring or high-cost,
   session evidence is concrete, it is not already solved or documented, and a
   small durable intervention exists. One occurrence is usually `NO_ACTION`;
   two are a candidate only when expensive or risky; three or more similar
   occurrences are a strong candidate. These are defaults, not statistics.
5. Prefer `NO_ACTION` when evidence is weak. Before creating anything, ask
   whether the remedy is: (1) point to an existing KB page, (2) update one KB
   paragraph, (3) add one short skill rule, (4) reuse a script or preset, or
   (5) delete obsolete machinery. Only then consider (6) a new helper or
   abstraction.
6. Make at most three tightly related maintenance changes in one run, and only
   when the user asked for implementation. Run checks relevant to those exact
   changes and report exact evidence plus knowledge impact.

SkillOpt-Sleep remains responsible for bounded, held-out-validated proposals to
`codex-implementation/SKILL.md`. When the remedy is a learned procedural rule
for that skill, recommend SkillOpt-Sleep instead of hand-editing `## Learned
guidance`, unless the user explicitly requests a manual edit. Adoption remains
human-reviewed Git/PR work.

Do not make gameplay or model changes from retrospective evidence alone. Do not
perform broad refactors, automatically reinterpret experiments, build
speculative infrastructure, auto-merge, automatically adopt SkillOpt proposals,
or create schedulers, daemons, hooks, databases, retrieval systems, or agent
orchestration.

Report the sessions reviewed, occurrence count and evidence for each pattern,
existing canonical coverage, classification, recommended smallest action or
`NO_ACTION`, checks run, and knowledge impact. Do not modify files during an
assessment unless the user explicitly asked to implement its recommendations.
