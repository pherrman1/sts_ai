# Pre-registration: concave-HP Silver victory leaf, paired 3-fight continuations at A20 (2026-10-18)

Written and committed before any cohort seed ran. Philipp, 2026-10-18, thread "end-state formula": 14:06Z asked to
investigate tweaking Silver's evaluation of the final state ("tweek the formula"); 14:16Z on the proposal: "Yes, but
use 16 workers for that. Also think about whether HP is the only thing we want to change".

## Question

Silver scores a won, non-final fight as `53 + h + 11·potions − 0.4·turns + 0.25·Δgold + 2·ΔmaxHP + …`, linear in the
HP `h` left after heals (`SilverSearcher::evaluateEndState`). Re-analysis of the §510 paired continuations (3,523
A20 states, seeds 111110000–111110999; note `/mnt/project-files/silver-leaf-eval/END-STATE-FORMULA.md`) found HP
strongly concave: one HP at < 30% of max is worth ~4x the mean (A20 floor model; 1.44 pp extra deaths in the next
3 fights per HP, model-free) and one HP at ≥ 90% ~0.5x (0.13 pp). Non-Fairy potions are worth ~3x more at low HP
than at high HP, and the formula's implied death price (~110 HP) is below the measured ~200. Does a concave HP
utility in the victory leaf make Silver's fights leave the run in a better state?

## Intervention: research option `STS_SILVER_CONCAVE_HP_LEAF=k` (default unset = today's leaf)

Victory branch only (not the final-fight leaf, not the A0 act-3 binary leaf, not the loss branch):
`h → u(h) = (M/k)·e^{0.75k}·(1 − e^{−k·h/M})`, `M` = root max HP (slope 1 at 75% HP), and the held-potion term ×
`e^{−k(h/M − 0.75)/2}` (= `sqrt(u'(h))`). Every other term is unchanged. Arms are set per continuation copy through a
thread-local override (`g_nativeSilverConcaveHpLeafOverride`); the env option is not set in any unit.

| arm (probe variant) | leaf |
|---|---|
| `base` | today's leaf |
| `leaf:concave=2.7` | k = 2.7, fitted by eye to the §510 floor-model HP slopes (**primary**) |
| `leaf:concave=1.35` | k = 1.35, half the curvature (secondary, dose check) |

## Other terms (Philipp's "is HP the only thing"), measured in the same run

Already tested and not changed here: per-type and level potion weights (§513 NOT_SHOWN), situational terms
(ADR-0035, §466/§468/§474), escape penalty (ADR-0036, §473), a global reweight (§330). Not measured before: the
gold (0.25 per gold) and max-HP (2 per point) rates, and potions under the student policy. The same states therefore
also get `hp:-12`, `gold:-50` (when gold ≥ 50), `maxhp:-5` (current HP capped) and one `pot:<TYPE>` per held type.
These prices are **descriptive** (no decision); a change to those weights would be its own pre-registered test.

## Method (`one_combat potionpriceprobe … 12 3 12 all <EXTRA>`, `apps/one_combat/potion_price_probe.cpp`)

- One unit = one A20 source run (Ironclad, acts 1–3, keys off, `STS_STOP_AFTER_ACT=3`), exact-10k Silver with the
  g6_E root prior (w400, tree prior K=8) and the default rollout root table; OOC decisions by the student_sel
  prior argmax (`ooc=heart1`: `STS_OOC_HEART1=student_sel.bin`, OOC MCTS off; the V4 chain only where the student
  encodes no choice). Exact environment: [run_unit.sh](run_unit.sh).
- Up to 12 battle-start states per run (after the first fight, all states, reservoir-sampled). Every copy of a state
  shares the GameContext RNG, agent seed and policy thread state, plays the next 3 fights, and is valued at the
  following battle by the A20 floor model `v_rich_a20_419` (`altFloor`), else by its terminal floor.
- Cohort: A20 seeds **111197436–111197675** (240), unit i → worker (i mod 16) + 1, 15 units per worker, 4 at a
  time, 6 h timeout per unit. Smoke seeds 111197676–111197679; pre-launch reviewer seeds 111197680–111197691.
- Expected size (**Inference**): ~2,500 states, ~7 continuations each, ~1 h per worker.

## Analysis ([tools/analyze_concave_hp_leaf.py](../../../../tools/analyze_concave_hp_leaf.py))

Leaf effect of a state = value(leaf copy) − value(base). Seed-clustered bootstrap, 10,000 resamples, RNG 534;
terminal source states dropped (base runs no fight), invalid rows dropped.

- **Primary:** mean leaf effect on `altFloor`, k = 2.7. **BETTER** if the 95% CI lower bound > 0, **WORSE** if the
  upper bound < 0, else **NOT_SHOWN**.
- Secondary, same labels: k = 1.35.
- Descriptive: effect on A20 win model, public X2-B, deaths within the 3 fights, HP at the next battle; by start-HP
  band and act; pairs with identical outcome; HP-eq prices of gold, max HP and non-Fairy potions (A20 floor and win
  models).

**Power (Inference).** Per-state SD of a diverged pair ≈ 5–6 floors (§510 smoke), so ~2,500 states give SE ≈ 0.12
floor: the run resolves ≈ ±0.25 floor (≈ 2.7 HP-eq per state at 0.092 floors/HP).

## Validity

INVALID if any cohort unit has rc ≠ 0 or lacks its CSV/log/env, if a log lacks the frozen command or the student
load line, if a unit's env sets `STS_SILVER_CONCAVE_HP_LEAF` or differs from the student/OOC-MCTS-off env, or if a
non-cohort seed is present. Checked by the analyzer; tars by `tools/cloud/verify_campaign.py`.

## Decision

- Primary **BETTER**: propose a paired full-run A20 A/B of k = 2.7 on the standard stack (Philipp authorizes size).
  No default change from this run alone.
- NOT_SHOWN or WORSE: the option stays research-only (unset); ledger entry either way. No re-tuning of k on these
  seeds.

## Known limits

- Fight-window measurement valued by a floor model, not whole runs; keys/Act 4 off; Heart and act-3 boss fights use
  the final-fight leaf and are unchanged by the arm.
- Known-RNG continuation: all copies face the same future encounters.
- k was chosen from the §510 data (different seeds), not tuned on this cohort.
