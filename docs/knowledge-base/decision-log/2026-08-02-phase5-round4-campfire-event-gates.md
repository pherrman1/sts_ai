# 2026-08-02 — Phase 5 round 4: one-ply Q gates for campfires and events (5.5.2/5.5.3)

Date: 2026-08-02
Session/task: Extend the §73 one-ply Q gate from card rewards to campfires
(rest options + smith upgrade targets) and events (incl. Neow); evaluate the
deployed OOC_STRAT_V3 net; no new datagen or retrain.

## Decision

Added `oocOnePlyRestPolicy`, `oocOnePlyUpgradeSelectPolicy`, and
`oocOnePlyEventPolicy` to `apps/one_combat.cpp`, each scoring every legal
action directly with `OocStrategicNet::predictActionValue` on the pre-decision
state and executing the argmax only when its margin over the runner-up meets
the shared `STS_OOC_STRATEGIC_MARGIN` gate; otherwise the default layer runs
(win-rate rest, win-rate upgrade target, heuristic events). New knobs
`STS_OOC_STRATEGIC_REST=1` and `STS_OOC_STRATEGIC_EVENT=1`, default **off** so
the §73 card-only configuration stays bit-reproducible and layer ablations are
possible. Wired into both `runFullRunOOC` and `runTraceRun`.

## Rationale

- **Inference:** round 3's sample-all Tier-B labels already cover every
  REST/upgrade/event decision with the same Q contract as cards, so no new
  datagen or retrain is needed — the round is a pure C++ extension +
  evaluation of the deployed net.
- **Inference:** events were the default heuristic's weakest screen (§71 EVENT
  value MAE 5.21; §73 Q MAE 13.3 but per-action labels), and the card gate
  showed Q works where the state-value head did not — so events are the
  highest-upside screen. The margin gate bounds any damage.
- **Inference:** the plan's 5.5.3 "sample stochastic outcomes via RNG clones"
  is superseded by the label design: each Tier-B action label is the concrete
  branch outcome (CRN, K=3 battles + bootstrap), so direct Q scoring at
  deployment already averages the stochastic continuation. Documented
  deviation, not a loss of mechanism.
- **Inference:** default-off flags keep the §73 card-only benchmark
  reproducible and give clean layer-wise attribution (the round's ablations).

## Alternatives considered

- Successor-value scoring (`predictValue` on cloned successors, the V2 path)
  — rejected: Q direct scoring is the round-3 winner and the Q input
  resolution (`strategicCands`) is input-identical to the training rows.
- Per-screen margin knobs — rejected: one shared margin plus margin probes
  keeps the gate semantics uniform; §74 found the combined stack peaks at
  margin 1.0 anyway.
- Always-on rest/event gates when the net loads — rejected: would conflate
  layers and break §73 comparison.
- Gating shop/TREASURE/boss-relic too — deferred (plan 5.5 remaining);
  keep this round to campfires + events per the user's scope.

## Evidence

- EXPERIMENTS.md §74: paired fair 128-seed gates (1,000 sims, seeds
  126700–126827, bit-identical baseline). cards+rest+event at margin 1.0:
  **36 wins (28.1%, +7.0pp)**, floor +1.38, score +2.09 (CIs span zero);
  margin 0.5: +3.1pp; margin 5.0: +2.3pp. Ablations at m1: event-only
  **+5.5pp** (main contributor), rest-only +1.6pp, cards-only +2.2pp — roughly
  additive.
- `apps/one_combat.cpp::oocOnePlyRestPolicy/UpgradeSelectPolicy/EventPolicy`,
  `runFullRunOOC`, `runTraceRun`; knobs in `main` env parsing.
- Smoke: 8 seeds with the flags on differ from off (1 seed flipped to a win),
  gates fire.

## Status and follow-up

Implemented; recorded in EXPERIMENTS.md §74. Best Phase-5 result so far, not
yet statistically established (win CI [−1.2, +15.2]pp at m1). Follow-ups:
(1) shop/TREASURE/boss-relic one-ply gates (plan 5.5.1/5.5.4 remaining
screens); (2) a dedicated event-Q retrain with more event labels if the event
gate stays the main driver; (3) a larger paired block (e.g. 256–512 seeds) or
lower sim budget to tighten the CIs on the +7.0pp point; (4) consider
`decisions/` records once the one-ply Q gate stabilizes.
