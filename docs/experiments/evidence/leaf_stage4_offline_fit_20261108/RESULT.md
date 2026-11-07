# Leaf plan, stage 4: offline fit on all 1,938 pilot units (result, 2026-11-08 00:30 CET; decision 00:40 CET)

Exploratory, offline, 0 core-h of new games. Plan: [PLAN.md](PLAN.md) (saved 00:15 CET; its header says 00:20 by
mistake), written before the fit on all units finished (00:16 CET). Data: the stage-2 pilot (PR #1003, ledger §763),
1,938 units, 15,504 source runs, 61,739 forks, 338,434 pairs (156,135 non-HP), every pair weighted by
w = eligible / sampled. Cross-fitting with 5 folds by unit; unit-cluster bootstrap, B = 1000, seed 20261107.

**Selection by the PLAN rule: P1 (four global prices) is the gate candidate.** It beats Silver's default leaf with
the whole CI above 0. The per-act prices P4 do not beat P1 clearly, and no state-dependent model beats P1. Philipp
decided not to gate it (last section).

## Deviations from PLAN.md

1. PLAN.md describes L with gold 0. Silver's default is `goldWeight` 0.25 per gold (`SilverSearcher.h:64`), and the
   pilot meta's `silverL` (§732's L) has no gold term. The first fit on all units (00:15 CET) used gold 0 and gave
   P1 − L +13.7 bp [7.4, 20.1]. The corrected L (+ 0.25 per gold) gives +14.4 [8.3, 20.2]. The selection is the same.
2. `leaf_prices.py` now also writes its out-of-fold predictions for `compare_heads.py`. Re-running it gave a
   byte-identical `lp1938.json`.
3. The heads of `train_eval.py` are put on `leaf_prices.py`'s metric by `compare_heads.py`. The PLAN names this
   comparison but no script for it. Both use the same folds and weights, and the two C predictions agree exactly.

## Cross-family skill (non-HP pairs: potion removed, max HP −5, gold −50)

Skill = 1 − SSE / SSE(C) in basis points, C = per act × family constant from the training folds. All leaves share the
per-act HP scale fitted on the HP pairs, so this measures the relative prices of potions, max HP and gold.

| model | skill vs C, bp [95% CI] | difference to P1, bp [95% CI] |
|---|---|---|
| L (Silver default) | 12.2 [7.5, 17.5] | −14.4 [−20.2, −8.3] |
| **P1** (4 global prices) | **26.6 [17.7, 35.3]** | |
| P4 (prices per act) | 30.4 [20.7, 39.4] | +3.8 [−0.2, +7.5] |
| V0 (net-0420 critic, scale per act) | 16.4 [6.6, 25.9] | −10.3 [−17.9, −2.8] |
| H0 (MLP head on the frozen trunk) | 12.9 [−0.0, 25.3] | −13.7 [−24.2, −4.0] |
| H1 (H0 + CRN pair term, λ 4) | 18.9 [5.9, 31.0] | −7.7 [−16.9, +0.7] |
| H1w (λ 1) | 14.9 [1.9, 27.2] | −11.7 [−21.8, −2.3] |
| H2 (critic + correction) | 22.8 [9.4, 35.3] | −3.8 [−13.5, +5.7] |
| G (LightGBM on pairs) | 12.8 [8.3, 17.7] | −13.8 [−19.7, −7.2] |

V0 in `leaf_prices.py` (critic difference, own scale) scores 10.0 [−0.0, 19.8]; the table uses `train_eval.py`'s V0.

By family (point estimates, bp vs C): potions P1 109, P4 124, L 61, V0 116, H2 121, G 54; max HP P1 −1, P4 +1,
L −1, heads −17 to −31, V0 −31; gold all between −6 and +3. So P1 gains over L on potions (mostly Fairy against the
rest) and a little on gold. The learned heads match P1 on potions but lose on max HP.

## P1 prices (HP units, all data; range over the 5 training folds)

| term | P1 | folds | Silver default |
|---|---|---|---|
| Fairy, on top of its death save (0.3 max HP) | 47.6 | 40.2 to 52.9 | 11 |
| every other potion | 3.67 | 3.11 to 4.22 | 11 |
| max HP, per point | 2.41 | 2.24 to 2.65 | 2.0 |
| gold, per gold | 0.124 | 0.110 to 0.140 | 0.25 |

So the Fairy counts about 70 HP in total at 75 max HP (Silver: about 33). The pilot's direct Fairy price was 74.8 HP
[65, 85]. HP scale (pp of Heart kill per HP): act 1 0.230, act 2 0.199, act 3 0.094, act 4 0.377.

P4 (all data): act 1 Fairy 38.3 / other 3.8 / max HP 2.17 / gold 0.12; act 2 52.4 / 4.4 / 2.92 / 0.14; act 3
117 / 2.2 / 5.3 / 0.19; act 4 18 / −0.6 / 0.5 / −0.04. The act-3 and act-4 weights are not stable across the folds
(act 3 other potions −1.8 to 5.4; act 4 every weight changes sign or scale), so P4 also fails the PLAN's stability
condition.

## Where the default leaf misprices (act means, pp of Heart kill, out of fold)

| cell | pairs | observed | L | P1 | P4 |
|---|---|---|---|---|---|
| act 1, potion removed | 20,248 | −1.69 | −2.86 | −1.80 | −1.70 |
| act 2, potion removed | 11,948 | −2.74 | −2.82 | −2.50 | −2.74 |
| act 3, potion removed | 8,843 | −2.41 | −1.44 | −1.43 | −2.41 |
| act 1, max HP −5 | 36,098 | −2.62 | −2.43 | −2.90 | −2.62 |
| act 2, max HP −5 | 15,949 | −3.08 | −2.18 | −2.58 | −3.07 |
| act 3, max HP −5 | 8,889 | −2.73 | −1.19 | −1.37 | −2.75 |
| act 1, gold −50 | 30,405 | −1.32 | −2.88 | −1.43 | −1.33 |
| act 2, gold −50 | 14,082 | −1.37 | −2.49 | −1.24 | −1.38 |
| act 3, gold −50 | 8,184 | −0.88 | −1.18 | −0.59 | −0.89 |

Relative to HP, Silver's default overprices potions in act 1 and gold in acts 1-2, and underprices max HP in acts 2-3
and potions in act 3. P1 fixes act 1 and gold; P4 would also fix act 3, but its act-3 weights are unstable.

## State dependence (train_eval.py, all units)

Within-cell slope b of the true D on the predicted D (1 = calibrated, 0 = no signal), cell = act × variant × fold:

| model | HP b [95% CI] | HP skill vs C, bp | potion b | potion skill, bp | level BCE / AUC |
|---|---|---|---|---|---|
| L | 0.01 [−0.00, 0.02] | −1 | 2.34 | +77 | |
| V0 | 0.48 [0.22, 0.73] | −0 | 1.21 | +116 | 0.5284 / 0.777 |
| H0 | 0.37 [0.21, 0.53] | −10 | 0.79 | +94 | 0.5307 / 0.773 |
| H1 | 0.40 [0.22, 0.57] | −7 | 0.82 | +105 | 0.5286 / 0.775 |
| H2 | 0.37 [0.18, 0.55] | −8 | 0.88 | +120 | 0.5274 / 0.777 |
| G | 0.27 [−0.45, 0.94] | −6 | 1.94 | +54 | |

Constant BCE 0.6506. On the 880-unit interim data the HP slopes were V0 0.66 [0.32, 1.00] and heads 0.49 to 0.51.
**With 2.2 times the data the HP slope did not improve** (the interim learning curve had suggested +0.12 per doubling),
and no model predicts the state-dependent part of the HP price better than the per-cell constant. Potions improve a
little (heads 0.71-0.80 → 0.79-0.88). Max HP and gold have no usable state dependence in any model.

## What this means

- The pilot's labels support better **global** prices (P1), not a state-dependent leaf. A full factory (stage 3,
  5-15k core-h) is not justified by these learning curves for HP; potions might gain a little.
- **Prior evidence against cheaper potions.** §542 (2026-10-18, student_sel, exact 10k Silver): arm W (non-Fairy
  potions 5.0, Fairy and Smoke Bomb 11, max HP 1.1, gold 0.01) lost 5.9 pp of wins [−9.0, −2.5] and 1.6 floors.
  §513: potions 7.8 NOT_SHOWN, both point estimates negative. P1 lowers non-Fairy potions even further (3.7). The
  pilot's 3.6 HP is the marginal value of one held potion under the current policy, which spends potions at price 11.
  A leaf that spends them at 3.7 changes the policy, not just the margin, and a noisy search tends to over-spend.
  So the measured price is plausibly a lower bound for a good leaf weight. The Fairy price, by contrast, was never
  tested (W kept it at 11) and is the most robust number of the pilot.

## Decision (Philipp, 2026-11-08 00:40 CET): no gate

"Ich glaube wir müssen p1 nicht messen, das ist vermutlich verschwendetes compute." Prices are to follow the E1
approach instead (fight-luck replays; learned price head thread). A gate was drafted, built and smoke-tested but not
launched: arms D, P1 and PF (= P1 with every non-Fairy potion at 11), net-0420 policy, combat B,
`bestbench 1000 1 20`, seeds 111820000-111822047, two SPRTs at α 0.025, ≈ 36 core-h. The draft (PREREG, campaign,
analysis, smoke logs) is in `/mnt/project-files/leaf-plan/stage4/gate-draft/`; its binary c201818cb248cef2… (main
ccc53a48) is in the bin cache. Of its seeds only the smokes 111829990-111829991 were played; the block stays unused.

What carries over:

- P1 is the offline benchmark for any learned price model on these CRN pairs (cross-family skill 26.6 bp vs C).
- Fork pairs are weighted by eligible / sampled (§763) and models are compared on held-out units.
- Fight luck changes HP (and sometimes whether a potion is drunk) but rarely max HP, gold or counters, so a luck-based
  price model needs the CRN prices above for those terms.
- Later candidate (needs code): the implied value of surviving a fight, V / s, is about 114 / 185 / 552 / 189 HP in
  acts 1 / 2 / 3 / 4 (V = base Heart kill, s = HP scale), against Silver's 53 + HP. If it holds, Silver takes too much
  death risk to save HP in acts 2-3. Act 3's s is poorly resolved (8-HP price z 1.2).

## Files (this folder)

`leaf_prices.py`, `compare_heads.py`, `train_eval.py`, `extract_embed.py`, `src_weights.py`; outputs `lp1938.json`
(prices, skills, act means), `heads1938.json` (heads on the same metric), `te1938w.result.json` and `te1938w.log`
(state dependence). Inputs (net-0420 trunk embeddings of 400,173 copies) are not kept;
`extract_embed.py` rebuilds them from the pilot tars, and `src_weights.py` the weights.
