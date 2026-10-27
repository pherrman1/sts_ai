# Dynamic campfire price, stage 0: result (2026-10-27)

**Verdict: STOP under the frozen rule.** Gate (a) fails. At N = 32 the price separates Rest from the best Smith
by more than 2 paired SE at only 29% of rest sites (gate: 50%). Gates (b) and (c) pass. The price moves the right
way with HP, and it would rest much less at 40–60% HP than student_sel does. But the sites where it disagrees with
the played choice are mostly within noise: only 12.6% of them are separable.

## Run

- Code `38bd5a71` (observer), binary sha256 `46001555a23d53c8…`; student_sel `cf6bf7fb…`. Plan and gates were
  committed in `ada3b5cd` before any results.
- 128 §683 seeds (111374100–111374227), MAP arm, replayed with `replay_unit.sh` (the §683 MAP configuration plus
  `STS_SILVER_ACT4_STRONG=0`), `STS_OOC_CAMPFIRE_PRICE_N=32`. No new seeds.
- 51 games were stopped at their first act-4 state; 77 ended earlier.
- **Trace check:** all 128 replays reproduce their §683 MAP trace row for row (`trace_check.txt`). The smoke
  replay of 111374100, played to the end, reproduced all 399 rows including the outcome. The observer does not
  change play.
- Raw rows: share `campfire-price-stage0/replays-38bd5a71.tar.gz` (sha256 `5a3b685ce291c147…`) and
  `analyze.json` (per-site values).
- Not priced: 45 rule-forced Ruby Recall sites (floor 49, decided by `heart_key`). The search model has no
  candidates there by design, and they are out of scope (§687).

## Gates (actEnd price, 732 rest sites in acts 1–3 with a legal Rest; 665 also offer Smith)

| Gate | Value | Threshold | |
| --- | --- | --- | --- |
| (a) \|Rest − best Smith\| > 2 SE | 29.3% | ≥ 50% | FAIL |
| (b) Spearman(Rest − Smith, HP fraction) | −0.44 [−0.50, −0.37] | ≤ −0.2, CI < 0 | PASS |
| (c) price class ≠ played class | 32.8% | ≥ 10% | PASS |

Mean \|Rest − Smith\| is 0.030 in calibrated Heart-kill probability, against a median paired SE of 0.017. The
search's own rollout3 leaf (reported, not gated) gives the same picture: separable 37.7%, Spearman −0.49,
disagreement 30.3%.

## By HP band (sites where the bot rested, smithed or recalled)

| HP / max HP | Sites | Played: rest | Price: rest | Mean Rest − Smith |
| --- | --- | --- | --- | --- |
| < 40% | 105 | 100% | 67% | +0.023 |
| 40–60% | 155 | 85% | 56% | +0.006 |
| 60–80% | 197 | 43% | 41% | −0.006 |
| ≥ 80% | 242 | 7% | 19% | −0.022 |

The expert audit (#865) found Baalorlord rests 13% of the time at 40–60% HP. The price lands between the bot and
the expert there. At high HP it rests more than the bot.

Played vs price class: rest→smith 118 and smith→rest 71 are the main disagreements. The price's favourite upgrade
targets are Spot Weakness, Inflame, Pommel Strike, Shockwave and Ghostly Armor.

## Interpretation

- **Implementation success:** the price runs on real rest sites at about 1–2 s per site (N = 8 to 32) and leaves
  play unchanged.
- **Scientific result:** FAIL on (a). Gate (c)'s 33% disagreement is mostly noise: among the 206 Rest/Smith
  disagreements, only 12.6% clear 2 SE. A rest-site rule driven by this price at N = 32 would mostly follow sampling
  noise.
- **Inference (not tested):** the failure is precision, not direction. SE falls as 1/√N, and pricing costs seconds
  per site. Naively projected, N = 128 would clear 2 SE on about 57% of sites (an upper-bound style estimate) but
  only on about 38% of the disagreements. A re-run at higher N, or a CTM expectation instead of sampled rollouts,
  would be a new pre-registered stage that Philipp decides on.
