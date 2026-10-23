# Leaf evaluation in combat search

Last verified: 2026-10-23 for the native Silver learned leaf head (§TBD-leaf, §TBD-leafab) and the exact endgame study (§TBD-endgame); 2026-10-18 for the native Silver prior-playout headroom pilot (§540); 2026-10-17 for the native Silver blended-leaf gate (§525); 2026-08-11 otherwise.

## Purpose / research question

How should Searcher3 evaluate leaf nodes in the search tree? What works, what
doesn't, and why does a learned end-HP value net beat direct utility regression?

## Current conclusion

**Learned end-HP value (V_combat) blended at α=0.3 is the deployed leaf
evaluator in the fair-S3 path.** It provides +12.5pp win at ~2-2.4× cpu over
rollout-only search. The honest-data model (§126) was superseded by the
hyperparameter-tuned 7k model (§148).

Direct utility-R regression (won ? 50+endHp : 0) has better offline metrics
(EV-MAE 10.10 vs 45.9) but is **significantly worse online** (−12.1pp at
α=0.1, §134). This is the third instance of offline≠online transfer
(§124c/§127/§133).

The gap mechanism is PUCT value-scale dynamics: the utility-R model's predictions
have much smaller variance (~0-55 vs ~0-85 for end-HP), which interacts poorly
with PUCT's exploration bonus at the direct-eval leaf sites where most
simulations end (§142).

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-08-04 | [§97 Combat value under gate stack](../../../../docs/experiments/ledger-03.md) | Old-era vnet rejected at α0.3 −3.1pp |
| 2026-08-07 | [§125 Wave-1/2 leaf gates](../../../../docs/experiments/ledger-05.md) | cPUCT, TERM_WIN+cpsi, and on-no-valid-edge all null/negative; honest-data vnet flips positive |
| 2026-08-07 | [§126 Honest-data V_combat promoted](../../../../docs/experiments/ledger-05.md) | Three significant gates +12.5/+12.1/+12.5pp; promoted to default ON |
| 2026-08-07 | [§132/§133 Quantile-R GBM](../../../../docs/experiments/ledger-05.md) | Offline EV calibration does not transfer; falsified at every α |
| 2026-08-07 | [§134 Same-recipe direct-R ablation](../../../../docs/experiments/ledger-05.md) | Same-recipe direct-R also significantly negative; confirms target not data is the issue |
| 2026-08-08 | [§135-§135a Leaf diagnostics](../../../../docs/experiments/ledger-05.md) | Infrastructure to measure gap on actual S3 leaf states |
| 2026-08-08 | [§142 Scale-controlled utility-R gate](../../../../docs/experiments/ledger-06.md) | PUCT value-scale dynamics confirmed as the gap mechanism |
| 2026-08-09 | [§148 V_combat hyperparameter tuning](../../../../docs/experiments/ledger-06.md) | +10.9pp at matched tree count; new default vnet |
| 2026-08-07 | Decision: VNet promotion | Three gates → promotion |
| 2026-08-09 | [§150 Per-encounter specialization](../../../../docs/experiments/ledger-06.md) | Gate negative, line closed |

## Rejected / falsified approaches

- **Direct utility-R regression as leaf target** — significantly negative online despite good offline EV metrics (§133/§134)
- **Quantile distribution leaf** — falsified at every α (§133)
- **TERM_WIN terminal-leaf bonus** — null on win rate, 3.1× cost (§116)
- **C_psi counter-sensitivity as leaf bonus** — −8.6pp (§125)
- **Boss-only VNet conditioning** — flat (§126)
- **Per-encounter XGBoost specialization + Reptile meta-learner** — gate negative (§150)
- **Covariate-shift mixture retrain** — does not improve held-out search-leaf ranking (§137)
- **K-rollout leaf estimators (A1)** — null
- **One-turn bootstrap rollout (A4)** — falsified at gates (§133)
- **Policy-filtered rollouts (A3)** — pending
- **Prior-guided rollouts** — significantly negative (−7.0pp, §124c)
- **Native Silver: learned leaf replacing or mixed with one rollout** — replacement fails (§180 GBM VNet −12.8 floors; §397 Gate A); a blend `(1−α)·R1 + α·V` on the §397 corpus does not beat one rollout, regret −0.017 [−0.436, +0.377], FAIL; its point estimate sits at a second rollout but "at least as good as R2" is not shown (§525)
- **Native Silver rollout block check against the worst facing under Surrounded** — +2.0 HP lost [−0.2, +4.3] on 192 paired A20 Shield-and-Spear fights, 1.12× CPU; over-blocking is an inference (§528, Shield and Spear rollout facing)
- **Native Silver tree reuse off** — −2.6 HP lost [−5.4, −0.1] pooled on the same fights but did not replicate on the second seed block (+0.5), Heart 0 pp; not adopted (§528, same entry)
- **Native Silver rollout attack targeting under Surrounded** — keep the faced monster +2.8 HP lost [+0.3, +5.6], face the bigger intent +0.7 [−2.5, +3.8] on 192 paired A20 Shield-and-Spear fights (§530, Shield and Spear search gap)
- **Native Silver: OOC-label difference leaf** — gen 1b's value head prices end-state differences no better than the formula (per-type potion r = 0.02 vs §510, max HP negative), and CRN paired continuations to the act end are too noisy (HP slope CI includes 0, ~14,600 core-h projected for usable prices) (§607, CRN act-end pilot)
- **Native Silver: learned leaf head fit to Silver's own end scores** (`STS_SILVER_LEAF_HEAD`, 128-64-1 on the frozen g7f_E trunk, half head and half playout) — on exact A20 first fights it stalls alone, and with a 1-point-per-turn penalty it matches a perfect leaf (§TBD-leaf). In long fights it values a running fight above any ending, so the fight-level candidate was capped at the win-now value; against CPU-matched production it is NOT_SHOWN, score −1.31 [−2.78, +0.14] per fight, better in normal fights, worse in elites and Acts 3–4; step-3 gate FAIL, line paused (§TBD-leafab). A shortfall head and a net-free win-now blend did not replace it (§TBD-leaf)

## Native Silver leaf headroom

- **Prior-argmax playouts at equal simulations (§540, pilot):** playing every playout card by the gen-6 E prior
  instead of the greedy list lowers HP lost by 1.45 [0.31, 2.51] per A20 fight (elites and bosses), fight score
  +3.8 [−2.4, +10.3] INCONCLUSIVE, at 7.6x CPU per simulation. A better playout has some headroom; a deployable
  version would have to be distilled into something about as cheap as the greedy playout.
- **Prior playouts vs production greedy 10k (§541, 768 A20 fights, 8 workers):** priorpl2500 +2.0 [−0.7, +4.7]
  score, HP −0.4 NOT_SHOWN at 1.9x CPU per fight; priorpl10000 +3.3 [−0.6, +7.2] score, HP lost −0.70 [−1.19, −0.22]
  at 7.3x. Bosses carry most of the point estimate (+9.8 / +12.5). At most a small gain. Philipp made prior playouts the
  default for real boss and elite fights (ADR-0050; `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0` restores greedy);
  since ADR-0056 only boss fights, for CPU (`STS_SILVER_PRIOR_PLAYOUT_ELITE=1` restores elites).
- **Exact first fights do not predict long fights (§638, §TBD-leaf, §TBD-leafab):** exact expectimax on the A20
  first fights (§623) prices every leaf change cheaply, but three changes that cut first-fight regret (max backup with
  block-first playouts, the win-now blend, the capped learned head) lost or did not win at A20 fight level, where
  elites, bosses and Acts 3–4 decide. A leaf candidate needs a long-fight check (elites, bosses, Acts 3–4) before a
  fight-level A/B.
- **Endgame (§TBD-endgame):** in the last two turns of A20 elite and boss fights Silver is near-optimal wherever exact
  solves finish (certified loss 0.02–0.04 points per fight); lost fights are already lost when the last turn starts.
- **Budget:** production Silver gains nothing measurable from 12k or 15k simulations over 10k at fight level (§638,
  §TBD-leafab).

## Relationships

- [vnet.md](../combat-models/vnet.md) — full VNet evolution and deployment story
- [pvnet-and-alternatives.md](../combat-models/pvnet-and-alternatives.md) — PVNet as alternative leaf evaluator
- [searcher3.md](searcher3.md) — direct-eval vs rollout-dominant split varies by fight context (§117)
- [belief-state.md](belief-state.md) — leaf evaluator sees determinized world from belief sample

## Current implementation

In the fair-S3 path, leaf evaluation at the blend site is **VNet-first** (if loaded),
falling back to rollout. The PVNet leaf fires at the `else-if` clause. See
`src/sim/search/BattleScumSearcher3.cpp` and the architecture page
[`docs/knowledge-base/architecture/combat-search.md`](../../architecture/combat-search.md).

## Open questions

- Can the value-scale gap be bridged with a VNet-style target that is both
  utility-aware and value-scale compatible?
- Would a value-scale normalization of utility-R (rescaling to end-HP-like range)
  close the online gap?
- Can the all-act checkpoint rollout be distilled into a deployable NN? (§66/§143)
- The tactical turn-beam rollout (B1, §135b) gate is pending.
