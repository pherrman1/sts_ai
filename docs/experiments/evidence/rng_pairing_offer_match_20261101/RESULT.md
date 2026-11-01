# Result: per-floor RNG keying for evaluation — DROP (offer-match gap 0.089 < 0.1; 0.00 at map roots)

Question: idea 7 of the [literature review](../../../knowledge-base/research/search-and-value-literature.md)
(keyed run-level RNG as an evaluation-only mode). Its cheapest falsifying check, chosen by Philipp on 2026-11-01:
in §685's 8,510 first-divergence pairs, compare the outcome correlation rho of pairs whose next offer happened to
coincide with pairs whose next offer differed. Decision rule (from the review, fixed before this analysis): drop the
idea if the gap is < 0.1.

Offline, no gameplay seeds, about 15 CPU-minutes on one cloud container. Code [analyze.py](analyze.py); per-pair data
[pairs.csv.gz](pairs.csv.gz); all numbers [result.json](result.json); hashes [artifacts.sha256](artifacts.sha256).

## Data and definitions
- The same 2,560 unit tars as §685 (§683 D/MAP/OFF, §661 A/M/S/MS, §676 A/C; 8,192 valid games). Pairs are built
  exactly as `s0.py extract`: per seed, each arm pair, first state k whose public record differs; root = state k−1.
  8,510 pairs, identical to §685.
- Next offer of a child: the first combat-reward screen (screen 2) with a non-empty card offer on a floor above the
  root's floor. MATCH = both children have one and the card lists (ids and upgrades, in order) are identical.
  Card rewards come from the sequential run-level card stream, so a match means the stream was still aligned (same
  floor, same reward type, same draw count) — the state keyed RNG would enforce.
- rho = Pearson (phi) correlation of the two children's Heart kills. CIs: 2,000 bootstrap draws over
  (campaign, seed) clusters.

## Primary
| next card offer | pairs | rho Heart kill [95% CI] |
| --- | --- | --- |
| match | 6,633 | 0.506 [0.471, 0.539] |
| differ | 1,703 | 0.417 [0.346, 0.481] |
| (missing in a child) | 174 | — |

**Gap 0.089 [0.021, 0.163] < 0.1 → DROP.**

## Secondary and robustness
- Act-4 arrival instead of Heart kill: gap 0.145 [0.081, 0.209].
- Match vs "same floor, different cards" (371 pairs, the stream-desync case at an aligned floor): 0.036 [−0.112, +0.199].
- Next relic offer: 0.066 [0.002, 0.128]; next potion offer: 0.098 [0.035, 0.167].
- By root act: 1 0.079, 2 0.077, 3 0.126 (CIs all include 0).
- By root screen: map roots (screen 5, 1,216 match / 1,374 differ — 81% of all differ pairs) **−0.004
  [−0.102, +0.094]**; other screens have ≤ 153 differ pairs each (gaps 0.03-0.17, CIs include 0).
- By campaign: §661 value-level 0.117 [0.025, 0.219]; §683 map-only 0.038; §676 CTM calibration 0.009.

## Interpretation
- The benefit ceiling is small. Keyed streams could at most lift the 20% differ pairs to the match pairs' rho.
  Overall rho would then rise from 0.488 to about 0.506 (CI upper end: about 0.521), i.e. 1 − rho falls by 4%
  (≤ 7%): ≈ 1.04× (≤ 1.07×) effective seeds, against the review's hoped-for 1.2-1.7×. Pairs that never diverge
  (1,218) gain nothing either way.
- At map roots, the case keyed streams target (children walk into different rooms and the card stream desyncs),
  pairs whose next offer happened to match correlate no better than pairs whose offer differed (−0.004). Most of
  the pooled gap comes from non-map roots and from §661, where an offer match mostly marks children that are close.
- This is an upper-bound argument: offer match is observational and selects similar children, so the causal gain
  of keying is likely smaller than the observed gap. The upper end of the primary CI (0.163) is above 0.1, but even
  that value implies ≤ 1.07× effective seeds.
- Consistent with §703 (keyed rollout streams alone: WEAK, 0.64× work) and §699 (combat death draws dominate
  sibling-difference noise): the run-level stream is not where whole-game pairing loses its correlation.

No code, default or seed block changed. Seeds: none (existing games only).
