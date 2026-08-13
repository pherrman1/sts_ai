---
name: implementation-review
description: Use for independent implementation review, diff review, validation, and auditing of repository changes; not for ordinary implementation tasks.
---

# Implementation review workflow

Use this skill when independently reviewing, validating, or auditing a
repository change after or alongside implementation. For ordinary
implementation tasks, follow `AGENTS.md` without invoking this skill.

1. Inspect `git status` first and distinguish pre-existing changes from this
   task. Read `AGENTS.md`, `docs/knowledge-base/CODE_MAP.md`, the relevant
   maintained page, implementation, and tests before editing.
2. Use Serena for semantic code structure: symbol overviews, definitions,
   implementations, references, and targeted refactoring. Avoid whole-file
   reads when symbol-level inspection proves the property.
3. Keep the change minimal and domain-aligned. Do not mix harness migration,
   gameplay, model, or research changes unless explicitly requested.
4. Verify with the cheapest focused check first, then inspect the complete
   `git diff`, `git diff --check`, changed paths, and generated artifacts.
5. Report exact commands and raw outcomes. Judge implementation correctness and
   experimental-design quality separately; identify unresolved uncertainty.
6. Before completion, stage only task-scoped files. Follow `AGENTS.md` for
   commit/push provenance and never use destructive Git commands or unrestricted
   auto-approval.

`AGENTS.md` remains authoritative for project policy; this skill is a reusable
procedure, not a replacement for that file.