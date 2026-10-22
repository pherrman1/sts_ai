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
| ceiling, stream noise only | 0.873 | 0.849 |
| same-public-state row sets | 8,311 | 4,458 |
| sets whose rows roll out identically | 8.6 % | 0.2 % |
| f, #812's inflation | 0.90 | 1.37 |
| hidden-state variance σ_h² per row | 0.00152 | 0.00150 |
| ceiling with hidden-state noise (a lower bound) | 0.687 | 0.727 |

Definitions:
- **Split-half agreement** compares the sibling order from two disjoint sets of repeats. It is taken per root, then
  per source, then over sources.
- **Ceiling** is the expected §577 concordance of a perfect evaluator. A pair's order is wrong with probability
  Φ(−|d| / se(d)).
  - With common seeds, se(d)² = var_r(v_i − v_j) / R.
  - With independent streams, se(d)² = se_i² + se_j².
- **Same-public-state sets** are rows of one root with the same action and X2-B value (#812's definition).
- **σ_h²** comes from row pairs in those sets: E[d̄²] = 2σ_h² + E[var_r(d) / R], whatever the streams are.
- **Ceiling with hidden-state noise** adds σ_h²(1/k_i + 1/k_j), where k_i and k_j are the actions' row counts.

Findings:
- **Common seeds work as designed.**
  - The stream variance of a sibling difference falls to 0.36 of independent streams (0.37 on TRAIN; §639 measured
    0.36 on one seed). So 32 common-seed repeats are worth about 89 independent ones.
  - At equal repeats per half, the split-half agreement is 0.05–0.08 above round 2's.
  - 16 vs 16 (0.718) beats round 2's 32 vs 32 (0.682). The PREREG expectation holds.
- **Hidden state is now the larger part of the noise.**
  - Rows with the same public state now share their streams, yet only 8.6 % of these sets roll out identically. 72 %
    of the sets come from map choices.
  - Their spread gives σ_h² ≈ 0.0015 per row in both rounds. It is a property of the states, not of the streams.
  - That is larger than the stream variance of a full common-seed sibling difference (0.0011), and more repeats cannot
    remove it.
  - If every row had its own hidden state, the ceiling would fall to 0.69. Children of a deterministic action share
    the root's hidden state, so the true ceiling lies between about 0.69 and 0.87.
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
  - It is level on map choices, +0.007 [−0.006, +0.021] (1,364 groups). X2-B is weakest there (0.602), and 72 % of
    the hidden-state sets are there.
  - It is slightly behind on boss relics and card selects (−0.008 each; 139 and 62 groups).
  - The head alone loses most on boss relics (−0.130) and card selects (−0.136), as on round 2.
- **PREREG expectations.**
  - The evaluators gain on the new VALIDATION: X2-B +0.031, M0.3 +0.030, SR_w0.3 +0.015, SR_w1 seed 2 +0.011 and the
    blends +0.015 to +0.025. **SR_w1 seeds 0 and 1 do not gain** (+0.001 and −0.001).
  - The order holds: X2-B and SR_w1 are above M0.3.

## Interpretation
- **Common seeds deliver cleaner sibling differences.** 32 common-seed repeats carry about as much stream noise as 89
  independent ones.
- **Hidden state now limits the labels.** Rows with the same public state still disagree. Their spread is the same as
  in round 2 and larger than the remaining stream noise, so more repeats would not help much.
- **The blend's gain replicates; the head alone does not.**
  - On 320 new sources the blend beats X2-B for all three seeds, on both splits (+0.018 to +0.027, every CI above 0).
    That is smaller than round 2's +0.032 to +0.040.
  - The head alone gains nothing from the new data while X2-B gains 0.031. On VALIDATION it is now 0.019–0.035 below
    X2-B, and seeds 0 and 1 exclude 0.
  - §641's "at X2-B's level" was the optimistic end: on these sources the head ranks slightly below X2-B.
- **Why the head alone falls behind is not tested.** The heads were fitted to round 2's labels, which used every 8th
  root and independent streams. The new data has every root. As in §641, the targets end in X2-B, which favours it.
- **There may be little room left.** The best blend (0.690) already sits at the hidden-state bound of the ceiling
  (0.687). The true ceiling is higher, but how much higher is unknown.

## Decision and next steps
- **No default change.** The leaf stays X2-B. The blend (SR_w1 seed 0, w 0.05–0.15) stays the online candidate; the
  head alone is not a leaf replacement.
- **Philipp decides the next step:**
  - Retrain the sibling-ranking loss on the new TRAIN labels (15,129 groups), alone and together with round-2 TRAIN.
    - Epochs would be selected on value plus ranking (§641's lesson).
    - The gate would be this VALIDATION: X2-B 0.664, current best blend 0.690.
    - Training is a GPU step with its own plan and go, about 40 min per arm.
  - Or run the parked online A/B of the blend.
- **For future labels:** only labels that average over hidden states could reduce the hidden-state noise, for example
  by redrawing the hidden RNG state in each repeat. That would be a capture change and is not part of this plan.
- No game seeds beyond 111144512–111144831 were used.

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
