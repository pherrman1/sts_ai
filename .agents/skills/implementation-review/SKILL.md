---
name: implementation-review
description: Independently review implemented repository changes and their evidence; not for ordinary implementation checks.
---

# Implementation review workflow

Use this skill when reviewing, validating, or auditing a repository change
after implementation. For ordinary implementation tasks, follow `AGENTS.md`
without invoking this skill. The default reviewer is independent from the
implementer; do not require the same agent to perform a second broad
self-review.

1. Inspect `git status` first and distinguish pre-existing changes from this
   task. Follow `AGENTS.md` and inspect the changed implementation and tests.
   Use `docs/knowledge-base/CODE_MAP.md` for unfamiliar code or subsystem
   boundaries; read maintained pages for the contracts and procedures needed
   to assess the change. The review and Git procedures are in
   `docs/knowledge-base/operations/agent-context-and-workflow.md`.
2. Use Git, `rg`, focused file reads, compiler diagnostics, and focused tests.
   No repository MCP server is required. Avoid whole-file reads when focused
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
   new session. Follow the completion and blocker criteria in `AGENTS.md`.
7. Treat missing knowledge-impact classification as a defect. Also report a
   defect when a durable fact appears only in a chronological ledger although
   a canonical KB page needs updating, `Knowledge impact: none` contradicts the
   diff, or new documentation duplicates a canonical fact instead of updating
   its authoritative location.
8. Before completion, stage only task-scoped files when the user requested a
   commit. Follow `AGENTS.md` for commit/push provenance and never use
   destructive Git commands or unrestricted auto-approval. Freeze the reviewed
   SHA before expensive scientific runs.

`AGENTS.md` remains authoritative for project policy; this skill is a reusable
procedure, not a replacement for that file.
