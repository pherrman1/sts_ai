# 2026-08-11 — Pi/sts-cycle superseded by built-in OpenCode Build + per-handoff model selection

Date: 2026-08-11
Session/task: Documentation/config hygiene after the interactive-OpenCode
simplification: align `opencode.json` and the implementer prompt with the
documented Build/Plan workflow, close the pre-push provenance hole, fix the
README submodule claim, and make canonical issue IDs unique.

## Decision

- The old Pi / sts-cycle / ai_cycle orchestration workflow is **superseded**.
  Its historical decision-log entries remain evidence of what was decided at
  the time, not current instructions.
- The current standard workflow is: external research/design + independent
  external review (ChatGPT), implementation by the built-in OpenCode `build`
  agent, model and reasoning effort selected per handoff (not encoded as
  agent identities), focused verification, task-scoped commit, plain `git
  push`.
- OpenCode `plan` is an optional genuinely read-only planning mode: `edit`,
  `task`, and all but an explicit read-only git-inspection bash subset are
  denied in `opencode.json`.
- `opencode.json` no longer defines custom `default`/`strong` model-role
  primary agents and hard-codes no model or reasoning effort; it overrides the
  built-in agents `build` and `plan` by name.
- Pre-push provenance guard: before editing, the agent records the starting
  `git log --oneline @{upstream}..HEAD` set; before `git push` it re-inspects
  that set, and automatic push is allowed only when it would publish this
  handoff's commits plus any pre-existing ahead commits the user explicitly
  authorized. Unrelated pre-existing ahead commits are never pushed
  automatically.
- The duplicate historical issue IDs #50/#51 (August 10 records that reused
  the August 9 canonical IDs) are renumbered: the August 10 Thorns and
  Awakened One records are now canonical #85 and #86, with provenance notes
  preserving the legacy aliases.

## Rationale

- The Pi orchestration was removed in commit `a5e415b`; the research-routing
  cleanup in `806617d` consolidated current research into
  `docs/knowledge-base/evaluation/current-research.md`. AGENTS.md now
  documents built-in Build + per-handoff model selection, so the remaining
  custom model-role agents in `opencode.json` and the "strong agent" wording
  in the implementer prompt were contradictions, not design.
- Commit `9231254` had already removed the `default`/`strong` model-role
  agents from `opencode.json`; this session completed the alignment (read-only
  `plan`, prompt wording, prompt-side pre-push mirror) and documented it.
- The AGENTS.md commit/push contract protected unrelated dirty working-tree
  files but not unrelated commits already ahead of upstream; the new
  provenance rule closes that hole without loosening the plain-`git push`
  requirement or any destructive-command deny.
- README's "current checkout limitation" claimed `json/`/`pybind11/` are not
  tracked gitlinks; `git ls-files --stage json pybind11` shows both at mode
  160000 and `.gitmodules` names them, so the claim was stale.
- Issues #50/#51 were first assigned to the August 9 ActionQueue/CardQueue
  records; the August 10 records duplicated them. Highest observed canonical
  ID at baseline was #84, so #85/#86 are the next unused IDs (verified: no
  project issue #85/#86 exists).

## Alternatives considered

- Keeping `default`/`strong` custom agents and editing AGENTS.md to match —
  rejected: AGENTS.md's per-handoff model selection is the intended design
  ("Do not create separate primary agents merely to represent stronger or
  cheaper models").
- Rewriting the old Pi decision-log entries to mark them obsolete — rejected:
  decision history must not be rewritten; a superseding entry is appended
  instead.
- Leaving the README limitation paragraph — rejected: it contradicts the
  maintained build docs and the actual gitlink state.
- Renumbering the August 9 records instead of the August 10 ones — rejected:
  the August 9 records came first and keep canonical #50/#51.

## Evidence

- `opencode.json` (built-in `build`/`plan` overrides; no model/reasoningEffort;
  seed-guard and destructive-git rules preserved; plan read-only).
- `.opencode/prompts/implementer.md` (no separate-strong-agent concept;
  pre-push provenance mirror).
- `AGENTS.md` "Default completion: commit and push" (starting ahead-of-upstream
  capture, pre-push re-inspection, blocked-push reporting rule).
- `README.md` Quick Start (json/pybind11 tracked gitlinks, `git submodule
  update --init`).
- `docs/knowledge-base/issues/README.md` + renamed records
  `2026-08-10-issue-85-thorns-retaliation-flips-win.md`,
  `2026-08-10-issue-86-awakened-one-premature-victory.md` (canonical IDs
  unique; provenance notes preserve legacy #50/#51 aliases; historical
  `2026-08-10-thorns-retaliation-and-awakened-one-outcome-fix.md` untouched).
- Removals: `a5e415b` (Pi infrastructure), `806617d` (research docs
  consolidation), `9231254` (opencode model-role removal), this commit.

## Status and follow-up

Implemented. `docs/knowledge-base/evaluation/current-research.md` and the
`docs/archive/research/` organization from `806617d` are intentionally left
alone. No gameplay/search/ML/training/benchmark behavior changed.
