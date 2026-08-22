---
name: implementation-review
description: Use for independent implementation review, diff review, validation, and auditing of repository changes; not for ordinary implementation tasks.
---

# Implementation review workflow

Use this skill when reviewing, validating, or auditing a repository change
after implementation. For ordinary implementation tasks, follow `AGENTS.md`
without invoking this skill. The default reviewer is independent from the
implementer; do not require the same agent to perform a second broad
self-review.

1. Inspect `git status` first and distinguish pre-existing changes from this
   task. Read `AGENTS.md`, `docs/knowledge-base/CODE_MAP.md`,
   `docs/knowledge-base/operations/agent-context-and-workflow.md`, the relevant
   maintained page, implementation, and tests before editing.
2. Use Serena for semantic code structure when it is configured and attached to
   the active Git worktree: symbol overviews, definitions, implementations,
   references, and targeted refactoring. Otherwise use targeted repository
   search and focused file reads. Avoid whole-file reads when symbol-level
   inspection proves the property.
3. Keep the change minimal and domain-aligned. Do not mix harness migration,
   gameplay, model, or research changes unless explicitly requested.
4. Verify with the cheapest focused check first, then inspect the complete
   `git diff`, `git diff --check`, changed paths, and generated artifacts.
5. Report exact commands and raw outcomes. Judge implementation correctness and
   experimental-design quality separately; identify unresolved uncertainty.
6. Review the evidence packet in the draft PR: baseline, reviewed SHA, changed
   paths, raw checks, omitted checks, and uncertainty. Separate implementation
   correctness from scientific-design quality. Minor corrections may continue
   the same Codex session; conceptual redesigns or new hypotheses require a
   new session. After repeated failures or conceptual ambiguity, stop and
   report the blocker.
7. Before completion, stage only task-scoped files when the user requested a
   commit. Follow `AGENTS.md` for commit/push provenance and never use
   destructive Git commands or unrestricted auto-approval. Freeze the reviewed
   SHA before expensive scientific runs.

`AGENTS.md` remains authoritative for project policy; this skill is a reusable
procedure, not a replacement for that file.
