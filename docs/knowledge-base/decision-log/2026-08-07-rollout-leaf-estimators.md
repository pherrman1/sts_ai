# 2026-08-07 — Rollout-leaf estimator experiments A1/A4 (STS_S3_ROLLOUT_K, STS_S3_ROLLOUT_TURN_STOP): implemented opt-in, smoke-verified; gates held for the concurrent leaf-net verdict

Date: 2026-08-07
Session/task: Plan + implement the first wave of the rollout-experiment
program (user's ideas 1 and 7) with the local/GCP split: local implementation
and smoke now, paired gates deferred until the other session's leaf value net
(§131/§132 quantile target experiment) is verified, because both arms modify
the same α-blend leaf the new net would redeploy.

## Decisions

1. **A1 `STS_S3_ROLLOUT_K` (default 1):** K independent rollouts per leaf,
   outcomes averaged, backpropagated once as a single visit. A tree traversal
   stays one PUCT visit — the experiment isolates leaf-estimate noise, not
   exploration. The first rollout's actions feed `actionStack` so
   `bestActionSequence` stays replayable; each rollout runs on its own
   `BattleContext` copy from the pre-rollout state. Implementation:
   `BattleScumSearcher3::multiRollout`, used at both `step()` rollout sites
   (leaf-expansion blend and the fair-illegal-stored-edge fallback).
2. **A4 `STS_S3_ROLLOUT_TURN_STOP=N` (default 0):** rollout stops after N
   completed player turns; the non-terminal endpoint is evaluated by the
   learned leaf → `α·VNet(s0) + (1−α)·VNet(s1)`. Turn boundary detection =
   `bc.turn` increment inside the END_TURN action chain
   (`BattleContext::afterMonsterTurns`), verified against the action-chain
   code before implementing. Distinct from §119 (pre-vnet heuristic endpoint
   on S2) and ranked above the policy-filter line because the §126 vnet
   provides the endpoint estimator §119 lacked.
3. **Sequencing:** A1 K=2 @500 sims (equal rollout budget) → K=2 @1000
   (conditional on the first) → A4 N=1 @1k (+ equal-CPU reinvestment if
   positive). 256-seed paired gates vs `build/vnet_all_a03_1k.csv` (50.4%),
   §126 config, after the §131/§132 verdict: a promoted net re-bases the
   pairing. A3 (policy-filtered rollout) demoted to last on the user's
   reasoning (two prior falsifications of prior-guided rollout quality,
   §124c/§127, at ~2.4× cpu).
4. **Backprop semantics:** averaged eval, visit +1 (user decision; the
   K-visits variant changes exploration and is a separate question).

## Rationale

- **Inference:** with the §126 vnet at α=0.3 the rollout outcome carries 70%
  of the leaf blend; R is a single stochastic continuation with large
  variance (avgRolloutLen ~14), so K-averaging is the cheapest variance
  reduction available and A4 tests whether one concrete turn + bootstrap is
  enough — directly informed by §119's negative gate (cap + heuristic
  endpoint) now that a trained endpoint exists.
- **Inference:** running gates concurrently with the other agent's 256-seed
  arms would contend for GCP threads (muddying cpu-s/run for cpu-trade
  calls) and risk pairing against a stale leaf stack.

## Alternatives considered

- Backprop K evals as K visits — rejected (user decision): changes PUCT
  visit counts, conflating variance reduction with exploration.
- First rollout on `state` in place, rest on copies — implemented first and
  **caught by the smoke test**: the first rollout plays to terminal, so the
  copies inherited a terminal state and K=2 was byte-identical to K=1
  (searchdiag rolloutActions did not double). Reworked to per-rollout copies
  from the pre-rollout state; structural-equality smoke (K=1 == unset) then
  passed, and K=2 rolloutActions ≈ 2.03× control.
- A3 policy-filtered rollout and B1 turn-beam in this wave — deferred: A4
  first (nearly free), B1 needs a scorer decision; A3 last per the user.

## Evidence

- Structural equality: `build/rk_ctl_8.csv` vs `build/rk_k1b_8.csv`
  (`STS_S3_ROLLOUT_K=1`), 8 seeds @300 sims — all game columns identical.
- Fires: `build/rk_k2b_8.csv` differs on 7/8 seeds; searchdiag3
  `build/rk_sd_{ctl,k2b,ts1}.csv` — rolloutActions 1,946,275 → 3,952,264
  (K=2, ≈2.03×), avgRolloutLen 13.94 → 2.50 (turn-stop=1), outcomes differ
  on 8/8 seeds under turn-stop.
- `ctest --test-dir build`: 5/5. Code: `BattleScumSearcher3.cpp::step`,
  `multiRollout`, `playoutRandom`; `include/sim/search/BattleScumSearcher3.h`;
  `apps/one_combat.cpp` env parse + BEST-stack banner. EXPERIMENTS.md §133.

## Status and follow-up

- Implemented, opt-in, default-off, byte-identical unset (smoke-proven).
- **Gate verdicts (2026-08-07, GCP):**
  - **A1 K-rollouts: NULL, line closed.** Paired 256-seed gates on the §126
    config: K=2 @500 sims (equal rollout budget) 49.2% vs 50.4% control
    (−1.2pp, CI [−7.4,+5.1], cpu −59%); K=2 @1000 sims (equal tree size)
    48.4% (−2.0pp, CI [−8.2,+4.7], cpu −21% with 8 more combat deaths);
    user-requested extreme K=10 @100 sims (equal rollout budget, 10× smaller
    tree) 35.5% (**−14.8pp, CI [−21.1,−8.2]**, cpu −81%). Tree size
    dominates: variance reduction does not pay for lost tree traversals at
    any tested ratio, and extra rollout work at equal tree size does not
    pay either; the α0.3 blend's 70% rollout share is not variance-bound
    here. K=4 not run (pre-registered: only if K=2 positive). EXPERIMENTS.md
    §133 (first entry).
  - **A4 one-turn bootstrap: FALSIFIED, line closed.** turn-stop N=1 @1k:
    34.0% vs 50.4% = **−16.4pp (CI [−23.0,−9.4])**, floor −2.4, HP −10.9,
    cpu only −18%. Long-horizon terminal rollout grounding is load-bearing;
    per the user's decision tree, B1 (turn-beam) must play across turns.
    This is the second falsification of the short-rollout family (§119).
  - The §131/§132 leaf-net verdict (quantile-R leaf significantly negative
    at every α; deployed vnet stays) left the pairing baseline unchanged.
- **Next steps (per the plan):** B1 tactical turn-beam rollout (scorer (b),
  complete-turn scoring after END_TURN resolves), then A2 dynamic α by
  rollout length, then A3 policy-filtered rollout (last).
