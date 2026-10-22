# Common-seed sibling recapture: result (2026-10-22)

A data capture with an offline analysis. [PREREG.md](PREREG.md) was frozen before any source ran (RUN_COMMIT
`9fad3f60`).
- Philipp chose this step on 2026-10-22 at 14:51Z ("Erst Neuaufnahme mit gemeinsamen Seeds") and authorized it with
  32 workers at 15:34Z ("Merge 812, go with 32 workers").
- The independent pre-launch review passed at `9fad3f60`.
- 32 cloud workers ran it from 15:47Z to 17:18Z, and the analysis ran in the cloud.

## Question
Round-2 sibling labels (§503) give each root child the mean of 64 rollout3 repeats, and every child gets its own
streams. They are noisy: a perfect evaluator would reach only about 0.81 §577 concordance (§641).
`STS_OOC_SIBLING_COMMON_SEEDS=1` (§639) gives repeat r of every child of a root the same stream.
- Does a recapture with common seeds give cleaner sibling labels?
- How do the existing heads rank the new siblings?

## Setup
- **Producer:** [run_unit.sh](run_unit.sh), the gen-2 A/B arm A config (§621) plus the sibling capture.
  - Capture settings: every searched root, depth 1, at most 64 leaves, 32 repeats, no long repeats, common seeds.
  - Code `90eb9f07`, v3 binary `dda76871…`.
  - The capture runs in a forked child, so play is unchanged.
- **Sources:** 320 fresh A20 seeds, 111144512–111144831. VALIDATION is seed % 4 == 3 (80 sources), TRAIN the other
  240.
- **Run:** 320 queue units on 32 workers. Each source took 1,347 s on average (median 1,443 s, max 2,897 s), 120
  core-h in total (PREREG estimate: about 105).
- **Analysis:** [tools/crn_analyze.py](tools/crn_analyze.py).
  - `rows` applies the acceptance rules.
  - `noise` computes split-half agreement, noise ceilings and hidden-state scatter, against round-2 VALIDATION.
  - `score` computes §577 concordance and regret with `tools/outcome_head_sibling_check.py`'s `group_metrics`, and a
    paired source bootstrap against X2-B.
  - Heads are scored by `one_combat heart1score` `193b0000`, the #812 evaluation binary. Its output was byte-identical
    to the campaign binary's on a 2,000-record check.

## Integrity
- **Verification:** `verify_campaign.py` found 320/320 units OK, 0 BAD, 0 duplicates and one run commit
  ([results/verify.txt](results/verify.txt)).
- **Sources:** every source returned rc 0, with its outcome complete and integrity passed.
- **Rows:** 0 bad capture rows (no timeouts), 0 error repeats and 0 dropped roots
  ([results/rows.json](results/rows.json)).
- **Data:** 578,987 rows.

  | split | sources | rows | roots | groups (≥ 2 actions) | actions per group |
  |---|---|---|---|---|---|
  | VALIDATION | 80 | 158,048 | 5,604 | 5,587 | 6.9 |
  | TRAIN | 240 | 420,939 | 15,183 | 15,129 | 6.7 |

  Round-2 VALIDATION had 2,559 groups from 320 sources.
- **Play:** 70 of 320 runs killed the Heart (21.9 %), in line with gen-2 arm A (20.9 % on 1,024 seeds, §621).

## Label noise
VALIDATION, with round-2 VALIDATION for comparison ([results/noise.json](results/noise.json)):

| | common seeds, 32 repeats | round 2, 64 independent repeats |
|---|---|---|
| split-half agreement, 1 vs 1 repeat | 0.610 | 0.558 |
| 2 vs 2 | 0.641 | 0.559 |
| 4 vs 4 | 0.670 | 0.596 |
| 8 vs 8 | 0.689 | 0.627 |
| 16 vs 16 | **0.718** | 0.653 |
| 32 vs 32 | – | 0.682 |
| stream variance of a sibling difference (full label) | 0.00107 | 0.00116 |
| the same with independent streams | 0.00299 | 0.00116 |
| same-public-state row sets (same action and public record) | 2,195 | 1,342 |
| sets whose rows roll out identically | 69 % | 0.1 % |
| hidden-state variance σ_h² per row, each set counted once [95 % CI] | 0.00005 [0.000002, 0.00011] | 0.00022 [0.00007, 0.00042] |
| the same, each row pair counted once | −0.00003 | 0.00001 |
| a row's stream variance, each set counted once | 0.0024 | 0.0010 |
| ceiling: stream noise only | 0.873 | 0.849 |
| ceiling with a hidden term on every row: proportional (#812's model), constant | 0.829, 0.799 | 0.837, 0.802 |
| #812's sets (same action and X2-B value) | 8,311 | 4,458 |
| share of them holding one public record | 9 % | 19 % |
| f, #812's inflation, on those sets | 0.90 | 1.37 |

Definitions:
- **Split-half agreement** compares the sibling order from two disjoint sets of repeats. It is taken per root, then
  per source, then over sources.
- **Ceiling** is the expected §577 concordance of a perfect evaluator. A pair's order is wrong with probability
  Φ(−|d| / se(d)).
  - With common seeds, se(d)² = var_r(v_i − v_j) / R.
  - With independent streams, se(d)² = se_i² + se_j².
  - The hidden term treats every row's hidden state as independent. It is either proportional to the stream variance,
    c(se_i² + se_j²) with independent streams' se and c = σ_h² / a row's stream variance (#812's f² − 1), or constant,
    σ_h²(1/k_i + 1/k_j), where k_i and k_j are the actions' row counts. Both use σ_h² with each set counted once.
  - Siblings of a deterministic action share the root's hidden state, so the hidden term overstates their noise.
  - All ceilings use the observed gaps, which noise inflates, so they lean optimistic.
- **Same-public-state sets** are rows of one root with the same action and an identical public record (the heart1
  record the head sees). Their rows differ only in hidden state.
- **σ_h²** comes from row pairs in those sets: E[d̄²] = 2σ_h² + E[var_r(d) / R], whatever the streams are.
  - Counting each set once matches #812's f. The interval is a source bootstrap.
  - Counting each pair once lets the large sets dominate, and most of them roll out identically.

Findings:
- **Common seeds work as designed.**
  - The stream variance of a sibling difference falls to 0.36 of independent streams (0.37 on TRAIN; §639 measured
    0.36 on one seed). So 32 common-seed repeats are worth about 89 independent ones.
  - At equal repeats per half, the split-half agreement is 0.05–0.08 above round 2's.
  - 16 vs 16 (0.718) beats round 2's 32 vs 32 (0.682). The PREREG expectation holds.
- **Hidden state is small, but not zero.**
  - Rows with the same public record now share their streams, and 69 % of these sets roll out identically.
  - Counting each set once, σ_h² is 0.00005 per row (TRAIN: 0.00009 [0.00004, 0.00015]). That is 2–4 % of a row's
    stream variance. Sets of 2–4 rows carry nearly all of it.
  - Counting each pair once, it is about 0, because the large sets mostly roll out identically.
  - Round 2 gives 0.00022 [0.00007, 0.00042]. Its interval overlaps this round's.
  - If siblings' hidden states were independent, hidden state would add 6 % (TRAIN: 12 %) to the stream variance of
    a common-seed sibling difference (#812's model).
- **The ceiling is 0.80–0.87.**
  - Stream noise alone gives 0.873.
  - A hidden term on every row lowers it to 0.829 (#812's model) or 0.799 (constant), on TRAIN to 0.820 or 0.787.
  - It matters more than its share suggests, because common seeds leave close pairs with a tiny SE.
  - The hidden term overstates the noise of deterministic siblings, so the truth lies in between.
- **Correction to §641's noise model.**
  - #812 (`sr_noise.py`) took rows with the same action and X2-B value as one public state. Only 9 % of those sets
    (round 2: 19 %) hold one public record.
  - The rest differ mostly in gold, HP, the boss or the cards offered. X2-B partly ignores these, but the head sees
    them.
  - Their spread (round 2's f: 1.37 with this tool, 1.40 in §641) is a real difference between chance outcomes, not
    label noise: the head and the label average over the same children.
  - With identical records, round 2's f is 1.12, and #812's ceiling is 0.84 instead of about 0.81.
  - An earlier draft of this README (`586ed461`, `4ed352e6`) used #812's sets and called σ_h² ≈ 0.0015 hidden state.
    That was wrong.
- **The two rounds' ceilings are not strictly comparable.** This round captures every root with up to 64 leaves, so
  its groups hold more close pairs than round 2's.

## Re-scoring the heads
Heads are scored on the new VALIDATION (5,587 groups from 80 sources) and compared with round-2 VALIDATION (§641). No
head saw any of these seeds. Blend weights are the round-2 TRAIN-holdout choices from #812. Full output:
[results/score.json](results/score.json) and [results/score.txt](results/score.txt).

| evaluator | concordance | − X2-B [95 % CI] | regret | round 2 |
|---|---|---|---|---|
| X2-B | **0.664** | – | 0.0176 | 0.633 |
| r0 (the search's own leaf value, one rollout3) | 0.564 | −0.100 [−0.114, −0.087] | 0.0272 | – |
| M0.3 | 0.585 | −0.079 [−0.093, −0.065] | 0.0245 | 0.555 |
| SR_w0.3 | 0.628 | −0.036 [−0.048, −0.026] | 0.0192 | 0.613 |
| SR_w1 seed 0 | 0.645 | −0.019 [−0.031, −0.008] | 0.0184 | 0.644 |
| SR_w1 seed 1 | 0.644 | −0.020 [−0.032, −0.009] | 0.0183 | 0.645 |
| SR_w1 seed 2 | 0.629 | −0.035 [−0.046, −0.024] | 0.0192 | 0.618 |
| M0.3 blend, w 0.15 | 0.669 | +0.005 [−0.002, +0.012] | 0.0177 | 0.644 |
| SR_w0.3 blend, w 0.15 | 0.681 | +0.017 [+0.011, +0.023] | 0.0165 | 0.666 |
| SR_w1 seed 0 blend, w 0.05 | **0.690** | +0.026 [+0.020, +0.032] | 0.0163 | 0.673 |
| SR_w1 seed 1 blend, w 0.25 | 0.683 | +0.019 [+0.011, +0.027] | 0.0158 | 0.665 |
| SR_w1 seed 2 blend, w 0.10 | 0.682 | +0.018 [+0.012, +0.023] | 0.0165 | 0.665 |

- **TRAIN (240 sources).** These sources are also unseen by every head.
  - X2-B scores 0.657.
  - SR_w1 seed 0 is level with it: 0.651, −0.007 [−0.014, +0.002]. Seeds 1 and 2 are at −0.011 and −0.028.
  - The three blends gain +0.020 to +0.027 (seed 0: +0.027 [+0.023, +0.031]).
- **Blend weight (exploratory, SR_w1 seed 0).** The curve is flat from 0.05 to 0.20, as on round 2.

  | w | 0.05 | 0.10 | 0.15 | 0.20 | 0.30 |
  |---|---|---|---|---|---|
  | VALIDATION − X2-B | +0.026 | +0.025 | +0.027 | +0.023 | +0.015 |
  | TRAIN − X2-B | +0.027 | +0.032 | +0.031 | +0.030 | +0.024 |
- **By the root's screen (VALIDATION; SR_w1 seed 0 blend at w 0.05 − X2-B).**
  - The blend gains on rewards, +0.042 [+0.034, +0.051] (2,374 groups); on rest sites, +0.034 [+0.025, +0.046] (538);
    on shops, +0.026 [+0.012, +0.042] (601); and on events, +0.019 [−0.000, +0.040] (502).
  - It is level on map choices, +0.007 [−0.006, +0.021] (1,364 groups). X2-B is weakest there (0.602).
  - It is slightly behind on boss relics and card selects (−0.008 each; 139 and 62 groups).
  - The head alone loses most on boss relics (−0.130) and card selects (−0.136), as on round 2.
- **PREREG expectations.**
  - The evaluators gain on the new VALIDATION: X2-B +0.031, M0.3 +0.030, SR_w0.3 +0.015, SR_w1 seed 2 +0.011 and the
    blends +0.015 to +0.025. **SR_w1 seeds 0 and 1 do not gain** (+0.001 and −0.001).
  - The order holds: X2-B and SR_w1 are above M0.3.

## Interpretation
- **Common seeds deliver cleaner sibling differences.** 32 common-seed repeats carry about as much stream noise as 89
  independent ones.
- **Most of the remaining label noise is stream noise.** Hidden state would add at most about 6–12 % to it. So more
  repeats, especially on close pairs, would still sharpen the labels.
- **The blend's gain replicates; the head alone does not.**
  - On 320 new sources the blend beats X2-B for all three seeds, on both splits (+0.018 to +0.027, every CI above 0).
    That is smaller than round 2's +0.032 to +0.040.
  - The head alone gains nothing from the new data while X2-B gains 0.031. On VALIDATION it is now 0.019–0.035 below
    X2-B, and seeds 0 and 1 exclude 0.
  - §641's "at X2-B's level" was the optimistic end: on these sources the head ranks slightly below X2-B.
- **Why the head alone falls behind is not tested.** The heads were fitted to round 2's labels, which used every 8th
  root and independent streams. The new data has every root. As in §641, the targets end in X2-B, which favours it.
- **There is room left.** X2-B (0.664) and the best blend (0.690) are well below the ceiling (0.80–0.87).

## Decision and next steps
- **No default change.** The leaf stays X2-B. The blend (SR_w1 seed 0, w 0.05–0.15) stays the online candidate; the
  head alone is not a leaf replacement.
- **Next:** Philipp chose to retrain the sibling-ranking loss on the new TRAIN labels ("go gpu", 2026-10-22 17:50Z).
  - The plan is `gen2/value-sr-crn/PLAN.md` on `claude/az-gen2-data` (`a8ab7da`), written before the run.
  - It has two arms on the SR_w1 recipe: the new TRAIN groups alone (15,129), and together with round-2 TRAIN.
  - The gate is this VALIDATION: X2-B 0.664, SR_w1 0.645, best blend 0.690.
  - The online A/B of the blend stays parked until then.
- No game seeds beyond 111144512–111144831 were used.

## Lessons for future label captures
1. **Turn common seeds on for every sibling capture.** Rankings are differences. 32 common-seed repeats are worth
   about 89 independent ones, so the same label quality costs about a third of the rollouts.
2. **Identify duplicate states by the full public record, not by X2-B.** Equal X2-B values mostly hide public
   differences (only 9 % share a record). Under common seeds, 69 % of same-record sets roll out identically. Rolling
   each record out once, weighted by its count, would save budget for more roots at a small cost in hidden-state
   averaging.
3. **Spend repeats where the order is close.** The split-half curve flattens (0.689 at 8 vs 8, 0.718 at 16 vs 16).
   Clear pairs need few repeats, and close pairs need many.
4. **Fix the noise model before the run, including how sets are weighted, and test it on a small sample.** The
   definition error above would have shown at once in a record comparison. The weighting moves σ_h² from about 0 to
   0.00005.
5. **Let some labels not end in X2-B**, for example rollouts to the end of the run. Targets that end in X2-B favour
   X2-B in every comparison.
6. **Capture with the deployed encoding.** This round used the Wing Boots counter; round 2 had to drop those groups.
7. **Cover map choices.** They are the weakest screen for every evaluator (X2-B 0.602; the blend gains nothing there).

## Reproduce
```
python3 tools/cloud/verify_campaign.py docs/experiments/evidence/ooc_sibling_crn_capture_20261022 --extract EXT
T=docs/experiments/evidence/ooc_sibling_crn_capture_20261022/tools/crn_analyze.py
python3 $T rows EXT OUT
python3 $T noise OUT R2 OUT/noise.json                  # R2 = the extracted §503 round-2 delivery
python3 $T score ONE_COMBAT OUT OUT/score.json M0.3=M0.3.bin SR_w0.3=SR_w0.3.bin SR_w1=SR_w1.bin \
  SR_w1_s1=SR_w1_s1.bin SR_w1_s2=SR_w1_s2.bin M0.3@0.15=M0.3.bin@0.15 SR_w0.3@0.15=SR_w0.3.bin@0.15 \
  SR_w1@0.05=SR_w1.bin@0.05 SR_w1_s1@0.25=SR_w1_s1.bin@0.25 SR_w1_s2@0.10=SR_w1_s2.bin@0.10 \
  SR_w1@0.10=SR_w1.bin@0.10 SR_w1@0.15=SR_w1.bin@0.15 SR_w1@0.20=SR_w1.bin@0.20 SR_w1@0.30=SR_w1.bin@0.30
```
- Head weights are on `claude/az-gen2-data` under `gen2/value-cf/weights` (M0.3) and `gen2/value-sr/weights` (the SR
  arms). Their sha256 values are in [results/weights.sha256](results/weights.sha256).
- `rows` needs about 2.5 min, `noise` 2 min and `score` 15 min on 4 cores (the heads are scored in 4 parallel parts).
