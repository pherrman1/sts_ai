# AIVAT replay pilot on the §676 guard: result (2026-10-27)

Pre-registration: [PREREG.md](PREREG.md). Run commit `d147c389`, binary `aadd4ea8` (x86-64-v3), 4 cloud workers,
2026-10-27 00:08Z-14:25Z (01:08-15:25 CET). Verified: `verify_campaign.py` units OK 512, missing 0, bad 0,
duplicates 0, one run commit.

## Validity

- Identity gate: **23,503 of 23,503** recorded non-event fights (512 seeds x 2 arms) reproduced exactly (outcome and
  post state), every unit rc 0. No seed excluded.
- Fight-level bias check (recorded minus mean replay, seed-clustered 95% CI; `estimate.json` `fight_bias`): every
  class contains 0 for end HP, death and V. Review H's boss concern: act-1/2/3 boss HP -0.53 [-1.66, +0.59],
  +0.42 [-1.13, +1.98], -0.61 [-1.70, +0.51]; Heart -0.40 [-2.35, +1.54]; elites +0.06, hallways -0.04 HP. The
  replays are draws from the same distribution as the recorded fights.
- Bias check of the estimate: corrected minus raw C - A = +1.25 pp [-1.41, +3.90], contains 0.

## Result (`estimate.json`, V `8efcc81f`, beta 0.8, m = 4, 4,000 seed bootstrap)

| | C - A | 95% CI | paired SD |
|---|---|---|---|
| raw | +2.15 pp | [-1.17, +5.66] | 0.393 |
| replay-corrected | +3.39 pp | [+0.64, +6.16] | 0.316 |

**Paired SD ratio 0.804** (prediction 0.71) -> pre-registered band 0.80-0.90: **weaker than projected; report, no
recommendation.** Effective seed multiplier 1.55x (projected 1.97x). The corrected CI excluding 0 is not a finding:
the decision rule is about the SD, and the raw result stays the §676 verdict.

## Diagnostics (post hoc, not pre-registered; `decomp.py` -> `decomp.json`)

| fights corrected | ratio at beta 0.8 | best beta (in sample) | ratio at best beta | offline projection (m = 4) |
|---|---|---|---|---|
| all | 0.804 | 0.64 | 0.788 | 0.71 |
| bosses + Heart | 0.844 | 0.64 | 0.833 | 0.73 |
| Heart only | 0.817 | 0.75 | 0.816 | 0.80 |

- The Heart alone gives almost all of the gain, and its ratio matches its offline projection. The projection
  overstated what the earlier fights add: their V(post) luck is real but only weakly predicts the final kill
  (correlation of the luck term with the outcome difference 0.62 all fights vs 0.58 Heart only), and averaging 4
  replays leaves noise of about a quarter of the luck variance. The CTM-based projection overrated how well a
  post-fight value model captures the kill (the same V/CTM inconsistency that biased the CTM-only baseline).
- Even an in-sample optimal beta reaches only 0.79, so a tuned beta would not change the verdict.

## Cost

Replays used 173 CPU-h (fresh replicates 139 CPU-h): bosses 117, Heart 24, elites 15, hallways 18. Heart-only
correction would have cost ~19 CPU-h of fresh replays at this config for ratio 0.82; under today's Act-4 strong
default the Heart search is ~8-15x more expensive, and m = 4 Heart replays cost 4x the A/B's own Heart fights.

Against simply adding seeds (estimate, 2026-10-27): a §676 run took ~580 s wall per lane (mean of 120 runs in the
source tars), so all-fight replays add ~+84% compute for 1.55x effective seeds, which is worse than running 55% more
seeds. Heart-only would add ~+12% for ~1.5x at §676's config, but under Act-4 strong (~10x Heart cost, Heart reached
in ~40% of runs) roughly +55%, about break-even. Not measured under Act-4 strong.

## Conclusion

The fight-replay correction is valid (exact identity, no bias in any fight class) but buys ~1.5x effective seeds,
not ~2x; almost all of it comes from the Heart. Per the pre-registered rule: no recommendation. Open option for
Philipp if ever wanted: Heart-only replay as a secondary metric (~1.5x seeds) where Heart compute is cheap.
