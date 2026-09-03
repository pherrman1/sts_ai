---
name: codex-implementation
description: Use for ordinary implementation, debugging, build, test, Git, and draft-PR tasks in sts_ai when no specialized research or review skill applies.
---

# Codex implementation workflow

1. Verify the worktree, named branch or app-managed detached HEAD, status,
   upstream, origin, and requested scope before editing.
2. Read `AGENTS.md`, `docs/knowledge-base/CODE_MAP.md`, and the maintained page
   routed for the affected subsystem.
3. Search existing scripts, presets, tests, and known solutions before creating
   new machinery.
4. Use native Codex delegation or concurrency only when independent work makes
   execution cheaper or faster. One coordinator owns scope, integration, final
   diff inspection, verification, and PR evidence. Do not parallelize
   overlapping edits or alternative implementations unless the accepted design
   explicitly requires them.
5. Make the smallest conceptual change that satisfies the request.
6. Run the cheapest check that proves the required behavior.
7. Inspect the complete diff, changed paths, status, and untracked files.
8. Classify durable knowledge impact and update the authoritative destination
   required by `AGENTS.md`.
9. Commit, push, and create or update the draft PR only under the existing
   workflow rules.

`AGENTS.md` remains authoritative for universal project policy.

## Learned guidance

<!-- The pilot preference targets this section; reject any staged SkillOpt-Sleep
diff that changes content outside it. Keep at most
12 short, stable, evidence-backed rules. Consolidate or replace old rules rather
than growing the section indefinitely. Never store branch names, current SHAs,
line numbers, transient failures, or duplicated KB facts here. -->

- After an evidence-relevant correction, reconcile the draft PR's scope,
  changed paths, checks and counts, provenance, conclusions, reviewed SHA, and
  remaining uncertainty against the final commit and raw results.
