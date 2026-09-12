---
name: codex-implementation
description: Implement, debug, test, and prepare draft PRs in sts_ai when no specialized research or review skill applies.
---

# Codex implementation workflow

Follow `AGENTS.md` for universal policy, task-dependent documentation routing,
and completion boundaries. Start localized work from the relevant code, tests,
or docs; use `docs/knowledge-base/CODE_MAP.md` for unfamiliar code or subsystem
boundaries and maintained KB pages for affected contracts and procedures.

Reuse existing scripts, presets, tests, and known solutions before creating new
machinery. For build and verification commands, consult
`docs/knowledge-base/operations/build-and-debugging.md`; for worktree, Git, and
draft-PR procedures, use
`docs/knowledge-base/operations/agent-context-and-workflow.md`.

## Learned guidance

<!-- The pilot preference targets this section; reject any staged SkillOpt-Sleep
diff that changes content outside it. Keep at most
12 short, stable, evidence-backed rules. Consolidate or replace old rules rather
than growing the section indefinitely. Never store branch names, current SHAs,
line numbers, transient failures, or duplicated KB facts here. -->

- After an evidence-relevant correction, reconcile the draft PR's scope,
  changed paths, checks and counts, provenance, conclusions, reviewed SHA, and
  remaining uncertainty against the final commit and raw results.
- On local Linux when `ccache` is available, use the matching checked-in
  `*-ccache` configure, build, and CTest presets. During iteration, build only
  the affected focused targets.
- Before running the full CTest preset, build the preset's complete default
  target set. A focused executable build does not provide all registered test
  executables.
