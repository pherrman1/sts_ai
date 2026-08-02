# 2026-08-02 — OOC guideline adopted as spec of record; new action plan; KB distillation

Date: 2026-08-02
Session/task: Decide how to use the external out-of-combat model guideline
(pasted into the session) relative to the archived Phase-5 plan and the
knowledge base.

## Decision

Created a new active action plan `docs/archive/ooc-action-plan-2026-08.md`
that supersedes Phase 5 of `docs/archive/combat-action-plan-2026-07.md` and
attaches the full guideline verbatim as Appendix A (spec of record).
Distilled the now-evidence-backed architecture into a durable decision
record (`docs/knowledge-base/decisions/2026-08-02-semi-markov-strategic-model.md`)
and a "Strategic model design" section in
`docs/knowledge-base/architecture/out-of-combat.md`. Marked the archived
plan's Phase 5 as superseded in its header.

## Rationale

- **Inference:** the pasted guideline is the original source of the
  archived plan's Phase 5 (a condensed version), and rounds 1–3
  (EXPERIMENTS.md §70–§73) have already implemented a large part of it, so
  neither the archive copy (stale checkboxes) nor the raw guideline alone
  is a usable follow-along plan.
- **Inference:** per AGENTS.md, dated archive plans are not current
  instructions and the knowledge base owns stable current understanding, so
  the guideline's stable architecture belongs in `decisions/` + the
  architecture page, while the checklist lives in the plan.

## Alternatives considered

- Use the archived Phase 5 as-is (add a status header only) — rejected: it
  does not record delivered rounds 1–3, the margin-gate lesson, the V2
  head-interleave bug, or the §73 Q-gate verdict.
- Guideline into the KB only, plan later — rejected by user choice in favor
  of plan + distillation together.
- Plan only, no KB/decisions work — rejected by user choice.

## Evidence

- `docs/archive/ooc-action-plan-2026-08.md` (new; rounds 1–3 checklist,
  divergences, phases A–F, evaluation protocol, Appendix A spec)
- `docs/archive/combat-action-plan-2026-07.md` (header updated: Phase 5
  superseded)
- `docs/knowledge-base/decisions/2026-08-02-semi-markov-strategic-model.md`
  (new)
- `docs/knowledge-base/architecture/out-of-combat.md` (new "Strategic model
  design" section; relevant-code additions; verified symbols
  `runStrategicGenSeed`, `runStrategicGenSeed2`, `oocOnePlyCardRewardPolicy`,
  `runFullRunOOC` in `apps/one_combat.cpp`)
- `docs/knowledge-base/decisions/README.md` (index updated)

## Status and follow-up

Implemented (documentation only; no code changes). Follow-up: the plan's
remaining phases A–F become the working checklist; the PPO vs. Tier-B Q
label A/B (§4.1 of the plan) is the next open design decision.
