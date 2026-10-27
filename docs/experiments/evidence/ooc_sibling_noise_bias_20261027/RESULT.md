# OOC sibling-value noise and bias by root type (#881): result (2026-10-27)

A diagnostic, not a gate. No policy or default change. No new seeds.

## Question
At an OOC root with sibling actions A and B, the search acts on D = Q̂(A) − Q̂(B). How noisy is D per leaf sample, how
much do common random numbers (CRN) help, how large are the gaps the search must resolve, and is D systematically
biased against a deeper reference? Which follow-up does that justify: search allocation and stopping (variance),
better targets or data (bias), or ε-best-arm stopping (tiny gaps)?

## Preflight (current main `ed2dcb2`)
- **Active OOC path at A20.** Only map roots are searched (ADR-0061); every other screen is decided by student_sel
  alone. The search's leaf is rollout3 with heart1 rollouts and CTM combats, valued by M0-calibrated X2-B
  (sigmoid(a_act + b·logit X2-B), ADR-0057); deaths score 0. No learned value head is in the leaf. The search draws
  each leaf on its own stream: there is no CRN between siblings inside the search.
- **Retained data.** §644's common-seed sibling capture (320 sources, every searched root, 32 CRN repeats per
  depth-1 leaf, gen-2 arm A, raw X2-B) and §695's campfire price (rest sites of 128 §683 seeds, 32 leaf and 32
  act-end rollouts per action, streams shared by the actions).
- **Reference teacher.** The cheapest existing deeper estimator is the act-end rollout of `STS_OOC_CAMPFIRE_PRICE`:
  the same rollout policy and CTM, played to the first map state of the next act and valued there by M0. Real-combat
  forks (§690) and full-game referees (§663, which failed the level gate) were not rerun.
- **SEL 25/50/100 % checkpoints.** See the last section.

## Data
1. **§644 capture, re-read (no new runs).** Per searched root the three highest-prior actions (prior from the
   trace's root candidates), pairs top-1 vs top-2 and top-1 vs top-3. Leaf values were raw X2-B; M0 is applied post
   hoc per repeat (non-terminal endpoints only, act from the endpoint floor, ≤16/33/50, as in
   `value_death_price_20261023/tools/stage0.py`). This is exact up to the act of boundary floors, since M0 leaves the
   rollout unchanged. 36,131 pairs from 20,608 roots. Older stack (gen-2 arm A, before the CTM fine-tune default).
2. **Fresh cohort on today's code.** Research options `STS_OOC_CAMPFIRE_PRICE_SCREENS=all` and
   `STS_OOC_CAMPFIRE_PRICE_TOP=3` (code `3bfca325`) price the top-3 prior actions at every real OOC root in a forked
   child: 32 leaf values (the search's own leaf, rollout3 + M0) and 32 act-end values, stream r shared by all actions
   within a kind. Replays of 16 already-used §683 MAP seeds, 111374100–111374115 (Philipp's go 2026-10-27 20:37Z),
   with [replay_unit.sh](replay_unit.sh) (the §695 env plus `STS_CALLING_BELL_CARD_RNG_FIX=0`), stopped at the first
   act-4 state. Binary sha256 `f18e737d…`, student_sel `cf6bf7fb…`. **All 16 replays reproduce their §683 trace row
   for row** ([results/trace_check.txt](results/trace_check.txt)). 1,872 roots with ≥ 2 priced actions, 3,396 pairs;
   68 roots logged "OOC MCTS actions requested at leaf" (no candidates, e.g. rule-forced sites) and are excluded.
   Wall 22 min on average per game on 4 lanes.
3. **§695 rest sites (no new runs).** 774 sites, 1,499 pairs, same estimator pair.

Frozen roots for #882/#884/#886: data branch `claude/sibling-noise-881-data` @ `f35262a`, `sibling-noise-881/`
(`roots.jsonl.gz` with seed, decisionIndex, screen, record and all values; `core: true` = 8 roots per type).

Definitions. sd1 = SD of a single-sample sibling difference (one leaf per action); paired = same stream r, unpaired =
independent streams. With a child-sampling successor (map rooms, events, boss relic acts) one sample is a random
captured child plus one rollout. CRN ratio = paired / unpaired variance. n(gap) = (1.96·sd1 / gap)² samples per action
for a two-sided 95 % resolution. Units: calibrated Heart-kill probability, in pp. Bias = mean(D_leaf − D_ref), D =
top-1 minus top-j by prior; negative means the leaf favours student_sel's top action less than the reference does.
Intervals resample seeds (roots of one game are correlated).

## Noise (leaf, single sample)

| type | pairs §644 / cohort | sd1 paired | sd1 unpaired | CRN ratio | n for 1 / 2 / 5 pp, unpaired | paired |
|---|---|---|---|---|---|---|
| pooled | 36,131 / 3,396 | 11.9 / 9.5 | 18.9 / 17.9 | 0.39 / 0.28 | 1,372 / 343 / 55 | 541 / 135 / 22 |
| CARD_REWARD | 17,113 / 2,184 | 6.9 / 6.3 | 17.9 / 17.7 | 0.15 / 0.13 | 1,238 / 309 / 50 | 185 / 46 / 7 |
| MAP | 6,194 / 362 | 15.5 / 15.8 | 16.8 / 17.5 | 0.85 / 0.82 | 1,088 / 272 / 44 | 925 / 231 / 37 |
| REST | 3,967 / 197 | 11.3 / 12.9 | 20.6 / 21.7 | 0.30 / 0.35 | 1,627 / 407 / 65 | 495 / 124 / 20 |
| SHOP | 4,274 / 207 | 19.7 / 17.2 | 25.9 / 19.7 | 0.58 / 0.76 | 2,583 / 646 / 103 | 1,492 / 373 / 60 |
| EVENT | 3,128 / 144 | 11.5 / 11.8 | 15.3 / 15.7 | 0.57 / 0.57 | 902 / 225 / 36 | 512 / 128 / 20 |
| BOSS_RELIC | 1,002 / 50 | 12.7 / 10.8 | 13.8 / 15.4 | 0.84 / 0.49 | 735 / 184 / 29 | 619 / 155 / 25 |
| CARD_SELECT | 408 / 184 | 5.0 / 6.0 | 18.4 / 18.9 | 0.07 / 0.10 | 1,294 / 324 / 52 | 96 / 24 / 4 |
| TREASURE | 45 / 68 | 16.6 / 9.2 | 18.5 / 15.1 | 0.80 / 0.37 | 1,312 / 328 / 52 | 1,052 / 263 / 42 |

(n columns from §644; [results/crn644_noise.txt](results/crn644_noise.txt), [results/cohort.txt](results/cohort.txt).)

- One leaf sample of a sibling difference has an SD of 14–26 pp without CRN at every root type. The two data sets agree
  within about 2 pp except at the small types.
- CRN cuts the variance to 0.07–0.15 at card rewards and card selects (deterministic children), to about 0.3 at rest
  sites, and hardly at all at map roots (0.82–0.85), where the successor (room, combat outcome) is itself random.
- About 41 % of single paired samples order the pair against its 32-repeat mean (§644 pooled; 34 % at boss relics).

## Gap sizes (§644, 32 CRN repeats)

| type | \|D₃₂\| < 1 pp | < 2 pp | \|D₃₂\| > 2 SE | split-half sign agreement | SD of the leaf's own gaps |
|---|---|---|---|---|---|
| pooled | 0.43 | 0.63 | 0.40 | 0.75 | 3.6 pp |
| CARD_REWARD | 0.53 | 0.73 | 0.44 | 0.76 | 2.8 pp |
| MAP | 0.31 | 0.50 | 0.34 | 0.72 | 4.2 pp |
| REST | 0.33 | 0.54 | 0.47 | 0.76 | 3.4 pp |
| SHOP | 0.42 | 0.59 | 0.19 | 0.66 | 3.0 pp |
| EVENT | 0.35 | 0.55 | 0.41 | 0.74 | 5.1 pp |
| BOSS_RELIC | 0.16 | 0.31 | 0.60 | 0.86 | 6.6 pp |

([results/crn644_gaps.txt](results/crn644_gaps.txt).) Most leading-sibling gaps are below 2 pp, and 60 % are not
resolved even by 32 CRN repeats. The gap distribution is heavy-tailed: a minority of pairs carry gaps of 5–20 pp and
are resolved by a few dozen samples.

## Bias against the act-end reference

The act-end rollout is deeper than the leaf only early in an act. Its median horizon is 6–13 floors against the leaf's
4–5; but it ends at or before the leaf at 14–54 % of roots (by type) and at every boss-relic root (where it is M0 of X2-B at the
next act's first map state, no rollout). The main rows therefore keep pairs whose reference ends ≥ 3 floors beyond
the leaf ("deep"); all pairs (including 11 act-4 roots) are in [results/cohort.txt](results/cohort.txt).

| type (deep pairs) | pairs | median \|D\| leaf / ref | median SE leaf / ref | bias [95 % CI, seeds] | bias SD beyond noise | MAE / noise-only MAE | order disagrees: all / both resolved |
|---|---|---|---|---|---|---|---|
| pooled, cohort | 2,034 | 1.20 / 1.48 | 0.72 / 1.50 | −0.34 [−0.56, −0.13] | 1.7 | 2.19 / 2.38 | 0.30 / 0.02 (n 323) |
| CARD_REWARD | 1,258 | 0.93 / 1.22 | 0.51 / 1.20 | −0.26 [−0.44, −0.05] | 1.4 | 1.68 / 1.67 | 0.29 / 0.01 (228) |
| MAP | 252 | 2.02 / 2.42 | 2.39 / 3.39 | −0.20 [−0.93, +0.49] | 0.0 | 3.48 / 3.97 | 0.37 / 0.00 (6) |
| REST | 87 | 2.20 / 1.86 | 1.00 / 1.56 | +0.55 [−0.11, +1.24] | 1.4 | 2.32 / 2.23 | 0.18 / 0.05 (22) |
| REST, §695 | 651 | 1.96 / 1.55 | 0.99 / 1.54 | +0.51 [+0.16, +0.84] | 2.2 | 2.58 / 2.34 | 0.28 / 0.03 (114) |
| SHOP | 154 | 2.04 / 2.49 | 1.55 / 2.86 | −0.15 [−0.91, +0.90] | 2.2 | 3.20 / 3.29 | 0.32 / 0.00 (15) |
| EVENT | 123 | 1.38 / 2.76 | 1.50 / 2.97 | **−2.50 [−4.08, −1.06]** | 4.5 | 4.11 / 3.34 | 0.40 / 0.00 (14) |
| CARD_SELECT | 108 | 1.48 / 1.42 | 0.59 / 1.05 | −0.32 [−0.66, +0.01] | 0.5 | 1.42 / 1.42 | 0.28 / 0.03 (30) |
| TREASURE | 52 | 1.31 / 1.37 | 0.74 / 0.91 | −0.18 [−1.20, +1.03] | 0.0 | 1.94 / 2.45 | 0.21 / 0.00 (8) |
| BOSS_RELIC (all pairs; reference shallower) | 50 | 3.92 / 3.38 | 1.36 / 0.03 | +1.52 [+0.20, +3.06] | 3.5 | 2.59 / 1.60 | 0.12 / 0.03 (37) |

- **Reference uncertainty.** At N = 32 the reference's median SE (1.0–3.4 pp) is as large as the typical gap, so
  most pair-level "errors" are within reference noise: MAE is at or below its noise-only expectation for every type
  except EVENT and BOSS_RELIC.
- **Where both estimators resolve a pair** (|D| > 2 SE in both; 323 cohort pairs, 114 §695), they order it the same
  way 95–100 % of the time.
- **Signed bias** is small on average: −0.3 pp pooled (cohort, deep pairs), +0.3 to +0.5 pp at rest sites (§695 CI
  excludes 0; leaf favours student_sel's top rest-site action slightly more than the act-end rollout does). The
  exception is **EVENT: −2.5 pp [−4.1, −1.1]** with a pair-level spread of 4.5 pp beyond noise. The leaf, which stops
  after three combats, values the option student_sel prefers lower than a rollout to the act's end does.
- **Map roots** (the only type searched at A20): no bias is detectable (−0.2 [−0.9, +0.5]), but the reference's SE
  (3.4 pp) is larger than the typical gap, so the check has little power there.
- **What this reference cannot see.** Leaf and reference share the rollout policy, the CTM and M0; they differ only in
  horizon. So this measures horizon bias of the leaf, not bias against real play. §663 found such rollouts die more
  often than real play, most of all in act 3. A real-combat reference (#882's forced-decision continuations on the
  core roots) can be joined later on (seed, decisionIndex).

## Interpretation
- **Variance-dominated, with mostly tiny gaps.** A single leaf sample has an SD of 14–26 pp (unpaired), while about
  half the leading-sibling gaps are below 1–2 pp. Resolving a 2 pp gap at 95 % takes about 180–650 independent leaf
  samples per action; a 5 pp gap about 30–100.
- **Map roots** (production search, 4,096 simulations at full budget over 2–4 actions): about 270 samples per action
  resolve 2 pp and about 1,100 resolve 1 pp, so today's budget resolves gaps of roughly 1–2 pp at the top at best (an upper bound: it assumes all 4,096 simulations
  run, while the learned OOC stop often ends earlier, and that they split over the top two actions). Half of the
  map pairs have gaps below 2 pp. CRN would not help here (ratio 0.85) because the successor itself is random.
- **Card rewards and card selects:** CRN would cut the samples needed 6–14× (paired n 46 vs 309 for 2 pp at card
  rewards). Bias against the deeper reference is −0.3 pp, inside the noise.
- **Rest sites:** a small, consistent positive bias (+0.3 to +0.5 pp) against act-end, the same order as typical
  rest-site gaps (median 1.7–2 pp); CRN helps (0.3).
- **Events:** the one type with a horizon bias clearly beyond noise (−2.5 pp); the leaf's three-combat horizon is too
  short for event options whose consequences unfold over the act. Events are decided by student_sel at A20 today.
- **Boss relics:** largest gaps (median 3–4 pp) and best order stability (split-half 0.86); no deeper reference exists
  in this harness (the act-end value is shallower), so bias is not measured. §690's real-combat forks are the right
  reference there.

## Decision / recommended next step (no policy promotion)
- **Mixed, mostly variance and tiny gaps.** Variance: all types. Tiny gaps: card rewards, card selects, map. Bias:
  events (horizon), possibly rest (small). Inconclusive: map bias (reference too noisy), boss relic (no deeper
  reference), shop, treasure (few roots).
- **Search side (map, today's only searched type):** ε-best-arm stopping (stop when the leader's lead is within ε of
  practically equivalent) rather than larger fixed budgets; at ε = 2 pp the needed samples are about 270 per action.
  The existing learned OOC stop is a version of this; quantifying its implied ε is the cheapest follow-up.
- **If non-map screens are searched again** (card rewards, card selects): paired sampling of siblings would be the
  cheapest variance reduction (#883).
- **Data/target side:** only events show a bias large enough to matter; a longer-horizon or act-end target for event
  roots is the candidate. Not tested here.
- No claim of near-ceiling or bias at map roots until a real-combat reference (#882) is joined.

## SEL 25/50/100 % checkpoints (follow-up)
- **Verified to exist** on `claude/az-gen2-data` `gen2/value-sr-lc/` at `0d84e2c4`: LC25_s1 (ep 17), LC25_s2 (ep 39),
  LC50_s1 (ep 27), LC50_s2 (ep 29), secondary LC25rows_s1 (ep 49), LC25groups_s1 (ep 12) under `weights/`, with
  `PLAN.md` (nested 25 %/50 % source subsets, matched optimizer steps, torch seeds 1 and 2), `pick.json` and
  `summary.json` per run. 100 % = SR_crn_r2_s1 (ep 13) / SR_crn_r2_s2 (ep 20) of §649. These are SR value heads,
  not the active A20 leaf.
- **Not evaluated here.** The learning-curve thread evaluates them on the same §644 VALIDATION siblings
  (`tools/lc_eval.py`, concordance, small-gap concordance, blend). Their targets are the rollout3 X2-B labels, so any
  comparison is student–teacher agreement, not correctness. Adding per-type signed sibling-difference error would need
  a scale map from head output to calibrated leaf units and is a separate bounded follow-up on the same pairs (frozen
  here: [tools/crn_extract.py](tools/crn_extract.py) top-3 pairs, and the cohort's 1,872 roots with records).

## Reproduce
- §644 noise: `crn_extract.py OUT.json.gz` (reads `/mnt/project-files/ooc-sibling-crn/units/*.tar`), then
  `crn_noise.py OUT.json.gz cal` and `crn_gap.py OUT.json.gz cal`.
- Cohort and §695: `price_bias.py OUT.json P-*.price.jsonl` (`DEEP=3` for deep pairs). Raw price rows:
  `replays-3bfca325.tar.gz` on the data branch; §695's on the share `campfire-price-stage0/replays-38bd5a71.tar.gz`.
- Frozen roots: `freeze_roots.py roots.jsonl P-*.price.jsonl`.
- Seeds: none new; 111374100–111374115 (§683, used) replayed.
