# §709 re-cut by imagined-fight index × act (research rank 3, 2026-11-01)

**Verdict: no detectable depth trend within §709's range, and no ≥ 2× act-2/3 boss over-forecast near real play.** The "3×" act-2/3
boss over-forecast of the 2026-10-31 full-rollout diagnostic does not appear in §709 at any imagined-fight index
0-3. No growth of the CTM forecast error over index 0-3 is detectable in any act (the act-2/3 boss slope CI
still allows −0.03 per index, about 1.6× by index 3). The one stable bias is mild elite pessimism in
acts 2-3 (about 1.4×), already present at index 0-1. The per-rollout CTM-vs-Silver correlation within a root action is
ρ ≈ 0.10, so sampled CTM rollouts are useless as a control variate for Silver rollouts.

No new compute, no seeds: offline re-analysis of the §709 rows.

## Data and method

- Input: §709's `STS_OOC_CTM_AUDIT` rows, share `ctm-audit-884/ctm-audit-884-replays-98e7d0c.tar.gz` (sha256
  `960900a8fc7646ae…`, as in §709), `cohort/A-*.audit.jsonl`: 144 roots, 16 seeds, 18,547 scored Silver-arm fights and
  18,499 CTM-arm fights.
- `combat` is the fight's index inside one leaf rollout (0 = first imagined fight after the root action). §709's leaf
  is rollout3 + X2-B, so the index runs 0-3 (4 in 36 fights, pooled into 3+). Act and room are the fight's own.
- Silver arm: each fight's entry carries the CTM forecast (pDeath, HP-given-win) and production Silver's drawn
  outcome. Entry states at index ≥ 1 were reached by Silver-played fights, so this arm measures calibration on
  rollout-policy states with no CTM-sampled history (covariate shift, not self-generated drift).
- CTM arm: same root, action and streams, but earlier imagined fights drawn by the CTM. Comparing its entry states to
  the Silver arm's at the same act × room × index measures self-generated drift over ≤ 3 fights.
- ρ: per-rollout leaf value, CTM arm vs Silver arm, matched by (root, action, rollout stream).
- `tools/analyze_ctm_audit_depth.py report.json cohort/A-*.audit.jsonl` → [report.json](report.json). CIs: percentile
  bootstrap over the 16 seeds, 2,000 draws, RNG seed 709. Deterministic rerun reproduces the file.

## Death calibration by index (Silver arm; forecast / observed, pred/obs with seed CI)

| Group | Index 0-1 | Index 2-3+ | All | Trend of (obs − pred) per index |
| --- | --- | --- | --- | --- |
| Act 2-3 bosses | 16.0% / 11.9%, 1.35 [0.87, 3.93], n 413 | 14.6% / 14.8%, 0.98 [0.61, 1.82], n 641 | 15.1% / 13.7%, 1.11 [0.80, 2.23], n 1,054 | +0.006 [−0.030, +0.050] |
| Act 2 bosses | 9.4% / 5.1%, n 236 | 8.6% / 6.8%, n 340 | 8.9% / 6.1%, 1.47 [0.60, 3.68], n 576 | +0.004 [−0.029, +0.055] |
| Act 3 bosses | 24.8% / 20.9%, n 177 | 21.3% / 23.9%, n 301 | 22.6% / 22.8%, 0.99 [0.69, 2.50], n 478 | +0.010 [−0.044, +0.063] |
| Act 2-3 elites | 5.5% / 3.7%, 1.48 [1.21, 2.12], n 1,741 | 4.5% / 3.4%, 1.31 [1.17, 1.75], n 1,462 | 5.0% / 3.6%, 1.40 [1.23, 1.84], n 3,203 | +0.003 [−0.006, +0.013] (elite+boss) |
| Act 1 bosses | 3.7% / 6.5%, n 246 | 9.2% / 6.4%, n 375 | 7.0% / 6.4%, 1.09 [0.64, 2.15], n 621 | −0.029 [−0.058, −0.002] |
| Act 1 elites | 2.2% / 1.9%, n 982 | 1.5% / 2.2%, n 777 | 1.9% / 2.0%, n 1,759 | −0.003 [−0.012, +0.004] (elite+boss) |
| Acts 1-3 elite+boss | | | | +0.001 [−0.006, +0.007] |

- Single cells move a lot: act-2 bosses at index 1 are 13.0% vs 6.0% (8 deaths, n 133), at index 0 4.8% vs 3.9%.
  Index is also confounded with the root: index-0 bosses come from roots just before the boss.
- Act-2/3 boss deaths are concentrated: seed 111374104 carries 76 of 144 deaths (forecast 79%, observed 88%).
  Dropping any one seed keeps pred/obs between 1.03 and 1.34. Without 111374104: 9.4% vs 7.0% (1.34).
- By forecast bin (act 2-3 bosses): < 5% 2.1 vs 1.6% (n 511), 5-10% 6.9 vs 8.5% (201), 10-20% 13.9 vs 13.3% (128),
  20-50% **31.7 vs 13.9%** (n 108, obs − pred −0.18 [−0.27, −0.03]), ≥ 50% 78 vs 82% (106). The over-forecast sits
  in the 20-50% bin.
- Act-4 (S&S, reached from act-3 roots): 0 of 64 deaths vs 7.2% forecast (small n).
- HP given a win, Silver − CTM: act 2-3 bosses about −6 HP at both index halves (CTM optimistic on HP), elites about −1 to
  −2; no growth with index.

## Arm drift over ≤ 3 fights (CTM arm − Silver arm entry state, same act × room × index)

- Potions at entry: within ±0.2 in every cell with a CI; significant only in act 1 (boss index 2 −0.21 [−0.33,
  −0.06], elite index 1 −0.13 [−0.21, −0.03]). Acts 2-3: −0.19 to +0.27, all CIs include 0.
- CTM forecast at entry: within ±0.06; HP within a few points. Index 0 is identical by construction.
- So the CTM arm's potion deficit at bosses seen in the full-game diagnostic (act 2 1.28 vs 1.61, act 3 0.72 vs 0.99)
  is not visible yet after ≤ 3 imagined fights; if it is real it builds up over longer rollouts (not testable here).

## ρ (per-rollout leaf value, CTM arm vs Silver arm)

| Root act | n rollouts | raw ρ | within root-action ρ |
| --- | --- | --- | --- |
| all | 5,264 | 0.74 [0.64, 0.81] | **0.10 [0.04, 0.15]** |
| 1 | 2,176 | 0.48 [0.33, 0.59] | 0.13 [0.06, 0.18] |
| 2 | 1,664 | 0.63 [0.46, 0.73] | 0.12 [0.02, 0.19] |
| 3 | 1,424 | 0.80 [0.55, 0.89] | 0.06 [−0.02, 0.13] |

- Raw ρ mostly reflects that both arms see the same root state. For estimating one leaf's value (MFMC, PPI), the
  within root-action ρ is the relevant one: 1 − ρ² ≈ 0.99, i.e. no variance reduction.
- Inference: the CTM draws its outcomes with its own RNG, not the fight's combat stream, so its sampled outcome is
  nearly independent of Silver's given the entry state. A deterministic CTM expectation (pDeath, HP mean) as the
  low-fidelity model could correlate better; not measured here.

## Interpretation against the rank-3 rule

- "Boss over-prediction ≥ 2× already at index 0-1": not met (act 2-3 bosses 1.35× [0.87, 3.93]). Depth compounding is
  therefore not falsified by this rule.
- "No trend over indices 0-3": met. Every act's slope includes 0 (pooled elite+boss +0.001 [−0.006, +0.007]), and
  act-2/3 bosses are near-calibrated at index 2-3. So the long-rollout over-forecast claim rests on the 8-root, 4-game
  diagnostic alone.
- Inference: the diagnostic's act-2/3 boss numbers (forecast 15.5% / 17.7%, observed 5.3% / 6.7%) are outside what
  §709 shows near real play (act 2 8.9 / 6.1%, act 3 22.6 / 22.8%). In §709, 75 of the 715 four-seed subsets of the 13 seeds with act-2/3 boss fights reach
  pred/obs ≥ 2.5 for act-2/3 bosses (135 reach ≥ 2; subsets with 0 deaths counted as exceeding), so a 4-game sample can show a 2.5-3× excess by chance at
  roughly 10-20% odds. Together with the 20-50% bin result, the most specific lead is a CTM over-forecast on
  mid-risk boss states, not an error that grows with depth.
- ρ < 0.5: the rank-3 rule's branch "PPI/MFMC only as debiasers" applies, at least for sampled CTM rollouts.

## Not covered

Index ≥ 4 (the leaf stops at 3-4 fights); self-generated drift beyond 3 fights; Act 4 apart from 64 S&S fights;
non-map roots. The paired full-game audit running in the CTM-deaths thread (seeds 111388204-219) is the test for
depth ≥ 4.
