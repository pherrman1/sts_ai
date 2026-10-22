# Value level 2×2 A/B: calibrated leaf (M0) × SR_w1 blend at A20 (pre-registration)

Written 2026-10-22 before any game of this campaign ran. Stage 3 of the value-head research plan
([doc](https://claude.ai/artifact/MoLmbWb4QXdLTEsDVYgt4a), section 7).

**Authorization:** Philipp, 2026-10-22 21:44Z, in the research thread: "keep going with the plan, you can use 32
workers if you want to, just do it, i allow it." The coordinator confirmed at 21:44Z (frozen brief, seeds from a free
block, reviews and pre-registration as usual).

## Question
In today's A20 search stack, does ending every rollout3 leaf in calibrated Heart-kill probability (M0) instead of raw
X2-B kill the Heart more often? Secondary: does the SR_w1 value-head blend (the parked blend A/B's candidate), and do
the two add up?

## Background: stage 0 (offline, no game seeds)
Tool [`../value_death_price_20261023/tools/stage0.py`](../value_death_price_20261023/tools/stage0.py) and
`calib_check.py` on §644's common-seed capture (320 A20 sources of gen-2 A/B arm A play, 70 Heart kills, 20,679
searched roots; capture `/mnt/project-files/ooc-sibling-crn/units/`).
- **Calibration** (per searched root: X2-B of the executed action's child, labelled with the run's Heart kill;
  logistic fit, one intercept per act, a common slope on logit X2-B): a = (−2.5384, −2.9227, −3.6523, −3.6334),
  b = 1.0535 [0.81, 1.29] (source bootstrap). Per-act slopes 0.90 / 0.97 / 1.22 / 1.10. Held out (fit on TRAIN,
  240 sources; VALIDATION, seed % 4 == 3, 80 sources): predicted − observed Heart rate −0.002 / +0.051 / +0.070
  (acts 1–3, every CI includes 0).
- **Death price.** A rollout3 leaf returns 0 on a death, 1 on a Heart kill and X2-B otherwise; X2-B's level is far
  above the Heart rate (decision roots: 0.75 vs 0.22 in act 1, 0.91 vs 0.38 in act 3). Relative to the calibrated
  price, the search over-prices a death 3.3× [2.5, 4.1] in act 1, 4.0× [3.0, 5.0] in act 2 and 7.7× [5.5, 9.8] in
  act 3. Rollouts also die more often than the real runs over the same horizon (real / rollout 0.59, 0.85, 0.62,
  0.80 in acts 1–4).
- **Deviation from the plan doc.** The doc's arm was M0′: X2-B kept for survivors and a death worth
  c_act = x̄ − x̄(1 − x̄)/(b(1 − p̄)) (0.52 / 0.58 / 0.77 here). Stage 0 found M0′ inconsistent across act borders, worst
  at act 3 → 4: a rollout that dies at the act-3 boss would score 0.77, above the ≈ 0.54 average of rollouts that
  reach act 4 (whose deaths stay 0 and kills 1). So this A/B uses M0 itself, the doc's first model rung ("X2-B with a
  per-act calibration"): every surviving rollout end and tree leaf in act k becomes σ(a_k + b · logit x), deaths stay
  0 and kills 1. All leaves then share one unit, Heart-kill probability.
- **Prediction (frozen here).** PUCT proxy on the capture's root siblings (fixed Q, the root's priors and completed
  simulations; it reproduces the played action at 91% of roots): M0 changes the pick at 7.0% of searched roots
  (13.5% of full-budget roots), 74% of them toward the sibling with the higher rollout death rate (mean +7.5 pp within
  the rollout horizon). If M0's calibration holds between siblings, those picks gain **+1.8 pp** Heart kills per run;
  if today's implied death price were right, they lose **−6.1 pp**. The proxy ignores the deeper tree and the stop.
- Precedents: §522 (td2 Heart leaf at rollout ends, act-1 level too low) had many more act-1 deaths and fewer act-3
  deaths at equal Heart kills; §615 (gen 1b value head at rollout ends, learned stop off) leaned +3.1 pp [−1.0, +7.2].

## Arms (`run_unit.sh` is the source of truth)
Every arm is the gen-2 A/B arm A config (§621, `../az_gen2_ab_20261021/run_unit.sh`): student_sel OOC prior and
rollout net (`cf6bf7fb…`), OOC MCTS 4096 sims, rollout3 native leaf, learned OOC stop 0.99, 25% full-budget roots,
fast roots capped at 1024, learned Silver stop with exact root budgets, g7f_E root table and prior, boss-only prior
playouts, keys on, CTM rows on.
- **A:** X2-B leaf (control).
- **M:** A + `STS_OOC_MCTS_LEAF_CALIBRATION=-2.5384,-2.9227,-3.6523,-3.6334:1.0535` (new research option, code
  `ee43726f`, default unset is byte-identical).
- **S:** A + `STS_OOC_MCTS_LEAF_HEART1_VALUE=sr_w1.bin` (sha256 `146a4512…`, data branch `claude/az-gen2-data`
  `3f0676b`, `gen2/value-sr/weights/SR_w1/student.bin`) + `STS_OOC_MCTS_LEAF_HEART1_VALUE_WEIGHT=0.1` (w picked on the
  TRAIN holdout of §645's evaluation, before any play).
- **MS:** both (the calibration acts on the blended anchor; it was fit for X2-B, so MS is slightly under-levelled).
- One unit is one seed with all four arms in sequence, order rotated by seed % 4, on one lane: wall times compare
  within a lane.

**Learned OOC stop: on in all arms.** Its features are root Q differences only (`oocLearnedStopFeatures`). M0 keeps
survivor gaps in acts 1–2 within about 0.88× and shrinks death-driven gaps, so the stop may fire later there; it grows
act-3 survivor gaps about 1.6×, so the stop may fire earlier in act 3. The blend at w 0.1 barely moves the gaps. The
stop's behaviour is reported (fast-root simulations and stop share by act and arm), not corrected.

## Seeds, workers, cost
- Seeds 111330000–111331023 (1,024, fresh; unused in the repo). Smokes 111339990–111339993.
- 32 workers × 4 lanes, `schedule queue`, 7 h timeout per arm.
- About 4 × 1,024 × 780 s ≈ 890 core-h, about 7 h of wall on 128 lanes.

## Analysis (`analyze.py`)
- **Valid seed:** all four arms rc 0 with `complete` and `integrityPassed` footers and the banner checks of
  `run_unit.sh` (rc 92–97). Invalid seeds are reported, not replaced.
- **Primary:** Heart kills, main effect of M0: per seed ((M + MS) − (A + S)) / 2, mean with a 95% seed-bootstrap CI
  (10,000 resamples, RNG 20261023). **IMPROVED** if the CI is above 0, **WORSE** if below, **NOT_SHOWN** otherwise.
- **Secondary:** main effect of the blend ((S + MS) − (A + M)) / 2 with the same rule; interaction
  (MS − S) − (M − A); simple effects M − A, S − A, MS − A (paired, exact McNemar); reached Act 4; deaths by act
  (act 1 named, given §522); mean floor.
- **Guard:** mean wall per arm over A's. A default proposal needs ≤ 1.10.
- **Descriptive:** searched, full-budget and aborted roots; picks off the prior's argmax; fast-root completed
  simulations and stop share by act.
- Power: from §621 (208 of 1,024 seeds discordant) a simple effect resolves about ±2.8 pp; a main effect averages
  two, about ±2.0–2.2 pp.

## Decision
No default changes from this run alone; Philipp decides. A win for M0 would still need the learned stop checked on
the new Q scale and a confirmation before it becomes a default. The result is also the first prospective test of the
stage-2 decision metric (built after launch, blind to these outcomes).

## Before launch
1. Freeze: RUN_COMMIT, code commit, binary sha256 in `campaign.manifest` and the brief.
2. Smoke on the frozen binary: seeds 111339990–993, every arm rc 0, banners as required.
3. Independent pre-launch review.
