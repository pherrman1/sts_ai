# E1 of the learned price head: RESULT

Pre-registration: [PREREG.md](PREREG.md). Review K: PASS at 3ae9b045 on condition F1 (luck weight v leave-one-out),
fixed in 2a667420 (delta PASS); worker count 20 → 40 at f29d1695 (delta PASS). Reports:
`/mnt/project-files/reviews/pr1004-prelaunch-review.md`.
Philipp's go: 2026-11-07 17:45 CET ("jap find ich gut, mach das"); 40 workers 22:21 CET ("Let's go 40, falls die pilot
worker fertig sind"). Run on 40 cloud workers 2026-11-07 22:53 CET (first claim) to 23:57 CET (last tar), after the leaf
pilot's workers were released. RUN_COMMIT `f29d1695`, code `065e4280`, binary `26775caf3c986e38…`.

Raw records: `e1_result.json` (the full output of `analyze.py`), `inputs.sha256` (SHA-256 of the 512 E1 tars and the
1,020 pilot tars analysed). The E1 tars stay on the share in `/mnt/project-files/learned-price-head/e1/units/`.

## Run

- 512 of 512 units, one tar each, every one rc 0 with 16 source rows; no failed, stale or duplicate claims. Units by
  worker: W1-W39 (W40 started when the queue was already empty). Unit wall median 11.1 min (3-25 min).
- Cost: 96.5 lane-h in all, 95.7 core-h CPU (projection 94; the go said about 88). Source runs 21.5 s mean (the
  pilot's 20.6 s for the same runs, plus the observer); one replay per fight 0.32 / 0.73 / 1.69 / 4.70 s in acts 1-4.
- 175,807 luck rows (acts 1-3: 170,183; act 4: 5,624): 0 replay errors, 0 health failures.
- Heart rate of the 8,192 source runs: 24.51%.

## Deviations

1. Worker count 40 instead of the frozen 20 (Philipp, 22:21 CET, before launch; K delta PASS). Nothing else changed.
2. None in the analysis: `analyze.py` at `f29d1695` ran unchanged on a snapshot of both tar sets (see Commands).

## Gates

- **G1 source identity:** 8,160 seeds in both sets, 0 mismatches. The pilot's four failed first-block units
  (111781544, 111781808, 111783952, 111786448; all four attempts rc 1, continuation failures) leave S: 32 seeds.
- **G2 fork identity:** 32,502 pilot base copies checked against E1's real fight ends, 0 mismatches, 0 missing rows.
- **G3 replay identity:** 10,943 unchanged replays on the 512 identity seeds, 0 mismatches.
- **G4 replay health:** 0 fights dropped.
- **G5 exchangeability:** all 12 act × room cells pass (largest |z| 1.65, act 3 OTHER, HP; survival largest |z| 1.30).

## Primary result: **INCONCLUSIVE**

| | value | 95% CI |
| --- | --- | --- |
| β_luck (2 × h_a123, HC1 SE 0.018) | 0.155 pp per HP | [0.119, 0.190] |
| β_CRN (π⁻¹ × v weights, 32,072 forks) | 0.178 pp per HP | [0.111, 0.250] |
| ρ = β_luck / β_CRN | 0.87 | 90% [0.60, 1.31]; 95% [0.56, 1.43] |

β_CRN ≤ 0 in 0.0% of the resamples, so the CRN slope is resolved. GO needs the 90% CI of ρ inside [0.67, 1.5]; its
lower end 0.60 is below. FAIL needs the 95% CI to exclude 1; it contains 1. Hence INCONCLUSIVE.
The pilot's own slope (π⁻¹ weights only) on S: 0.188 [0.129, 0.252] pp per HP, ratio to β_luck 0.82. The luck weight v
came from the encounter cell for 32,057 forks and from the (act, room, band) fallback for 15.

By act and room (same weights; per-act and per-act-room HP columns in their own fits). The pilot sampled no act-3
boss fight ends.

| group | forks | β_luck [95%] | β_CRN [95%] | ρ [90%] |
| --- | --- | --- | --- | --- |
| act 1 | 19,004 | 0.182 [0.119, 0.245] | 0.168 [0.078, 0.259] | 1.08 [0.65, 2.04] |
| act 1 NORMAL | 12,655 | 0.252 [0.146, 0.356] | 0.194 [0.096, 0.289] | 1.30 [0.74, 2.35] |
| act 1 ELITE | 5,088 | 0.170 [0.081, 0.260] | 0.251 [0.112, 0.384] | 0.68 [0.34, 1.38] |
| act 1 BOSS | 1,261 | 0.109 [−0.018, 0.239] | −0.027 [−0.205, 0.160] | CRN ≤ 0 in 62% |
| act 2 | 8,399 | 0.147 [0.087, 0.205] | 0.232 [0.133, 0.339] | 0.63 [0.38, 1.06] |
| act 2 NORMAL | 5,650 | 0.191 [0.104, 0.275] | 0.237 [0.138, 0.336] | 0.81 [0.46, 1.39] |
| act 2 ELITE | 2,140 | 0.153 [0.070, 0.243] | 0.250 [0.096, 0.417] | 0.61 [0.28, 1.37] |
| act 2 BOSS | 609 | 0.067 [−0.057, 0.180] | 0.187 [−0.059, 0.450] | CRN ≤ 0 in 6% |
| act 3 | 4,669 | 0.143 [0.077, 0.206] | 0.108 [0.002, 0.222] | 1.33 [0.51, 5.14] |
| act 3 NORMAL | 3,176 | 0.178 [0.076, 0.278] | 0.004 [−0.122, 0.134] | CRN ≤ 0 in 48% |
| act 3 ELITE | 1,493 | 0.138 [0.045, 0.237] | 0.198 [0.049, 0.354] | 0.70 [0.25, 2.14] |

## Descriptive (not gated)

- **Scale check.** The Heart fight's survival luck: s_heart = 99.1 ± 2.2 pp per won Heart fight, the 100 pp it must
  be. The ×2 scale for one replay holds where the truth is known.
- **Act 4.** HP at the end of Shield and Spear (right before the Heart): 0.53 ± 0.08 pp per HP.
- **Potions** (luck 2 × k_a ± SE vs the CRN `pot` copies, π⁻¹ weights): act 1 1.9 ± 0.8 vs 2.0; act 2 −0.9 ± 0.9 vs
  2.8; act 3 1.5 ± 1.1 vs 2.8 pp per potion.
- **Survival** at 0 HP (2 × s_a): −0.8 ± 7.0, −4.7 ± 7.4, −7.6 ± 8.5 pp (uninformative at this sample size).
- **Controls** (acts 1-3 pooled): max HP 0.145 ± 0.087 pp per max HP, gold 0.007 ± 0.006 pp per gold, upgrades
  1.05 ± 0.30 pp per upgrade. Counter relics with data differing in at least 50 fights: Happy Flower, Incense
  Burner, Ink Bottle, Lizard Tail, Nunchaku, Omamori, Pen Nib, Sundial. Lizard Tail is 18.4 ± 5.5 pp per unused tail,
  Pen Nib 0.53 ± 0.21 pp per count, and the others are within 1 SE of 0.
- β_luck on all 8,192 seeds: 0.155 ± 0.018 pp per HP (the same as on S).
- **Inputs of the design doc's cost model** under net-0420. Per-draw luck variance per game (½ Σ u²): HP² 429 / 692 /
  673 and potions² 0.64 / 0.65 / 0.54 in acts 1 / 2 / 3. Fights per game 9.3 / 6.1 / 4.8; residual variance 0.159
  (E0: 0.148).
- **Information per core-h** on the pooled HP price (not pre-registered). Luck: 96.5 lane-h for SE 0.018. CRN: the
  pilot's first block, 1,040.6 lane-h for SE ≈ 0.035 (the bootstrap half-width / 1.96). That gives luck about 40× the
  information per core-h, or about 25× if only the HP copies and the base are charged (about 60% of the pilot's
  copies). The pilot's copies also price potions, max HP and gold, which luck cannot separate as well.

## Interpretation (Inference)

Fight luck and the CRN pairs give the same pooled fight-end HP price within noise (ρ = 0.87, and the 95% CI
[0.56, 1.43] contains 1). The per-act ratios scatter around 1. Act 2 is furthest from it at 0.63 [0.38, 1.06], and
act 1 sits at 1.08. The run cannot certify the calibration inside the pre-registered band, because the CRN reference
is about twice as noisy as the luck estimate even though it cost about ten times as much. The Heart scale check
(99 ± 2 pp) supports the luck instrument directly. For HP, then, luck labels look usable. What is missing is a more
precise CRN reference, not a better luck estimate. The potion prices agree in act 1 and are lower for luck in acts 2-3,
which this run does not resolve.

## Decision

**INCONCLUSIVE** (pre-registered rule). No default change; `luck=` stays a research option. Seeds: none new (the
pilot's 111780000-111788191). Cost: 95.7 core-h on 40 cloud workers, 64 min wall. What would settle it is a more
precise CRN reference. One option (it needs a go): run E1 on the pilot's finished second-block seeds as well. That is
918 more pilot units (7,344 seeds), about 85 core-h of replays, and no new CRN cost, and it narrows the ratio CI by
about a quarter.

## Commands

```
# snapshots taken 2026-11-08 00:01 CET (inputs.sha256)
cp /mnt/project-files/learned-price-head/e1/units/*.tar SNAP/e1units/
#   + the pilot's tars with unit ids 111780000-111788184 from /mnt/project-files/fight-end-pairs-pilot/units/
python3 -I docs/experiments/evidence/learned_price_head_e1_20261107/analyze.py SNAP/e1units SNAP/pilotunits e1_result.json
```
