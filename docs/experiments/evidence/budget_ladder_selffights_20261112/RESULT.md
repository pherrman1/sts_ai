# Learned budget step B: per-fight budget ladder 1k-16k on our own H4 states (result, 2026-11-12)

This is the run of [PREREG.md](PREREG.md), frozen in run commit 72e997a4 (code 3c85fb26, binary ca8d9d0b; prelaunch
review K PASS). Launch was about 18:42 CET on W1-W40; the first tar arrived at 18:43 CET and the last at 19:27 CET.

## Run

- `verify_campaign.py`: **768 / 768 units OK, 0 missing, 0 bad, 0 duplicates**, run 72e997a48f1a
  (`results/verify.txt`).
  - Per act (review K, R2): acts 1, 2 and 3 have 256 / 256 OK each, with no unit missing and no unit at rc ≠ 0.
  - 22 of 40 `DONE.json` files were written; the other workers were released idle after their last upload.
- Claims snapshot: `results/claims.txt`. All 768 units were claimed once, as attempt a1; nothing was re-run.
- `analyze.py` (frozen) with §794's `currency.json` gives `results/result.json`:
  - all 768 units at rc 0;
  - **6,817 arm fights from 256 runs, 0 dropped** (26.6 arm fights per run in Acts 1-3).
- Cost: **88.6 lane-hours**, against the 100-160 planned from the smoke. The median unit took 288 s and the longest
  2,158 s.

## Uniform budgets (all Act 1-3 fights; per fight, 4 copies)

| budget | Heart-pp loss | HP lost | CPU s per copy |
|---|---|---|---|
| 1k | 4.40 | 7.45 | 0.29 |
| 2k | 3.94 | 6.72 | 0.59 |
| 4k | 3.67 | 6.32 | 1.20 |
| 8k | 3.31 | 5.82 | 2.51 |
| 16k | 3.12 | 5.55 | 5.22 |

- All five uniform budgets lie on the lower convex hull. Each doubling buys a little less: −0.46 / −0.27 / −0.36 /
  −0.19 Heart-pp per fight.
- The split-half r of the 1k → 16k gain is 0.13 in Heart-pp and 0.11 in HP. That is the first visible per-fight
  signal (§794: ≈ 0 at 16k-64k), but it is weak.

## Primary: learned policies against the uniform frontier at the same CPU (Heart pp, 99.17% CIs)

| policy @ target | CPU vs target | choice share 1k / 2k / 4k / 8k / 16k | Δ per fight | Δ per run [99.17% CI] |
|---|---|---|---|---|
| room @ 4k | 1.22× | 0 / 29 / 53 / 18 / 0 % | −0.067 | −1.77 [−4.15, +0.62] |
| room @ 8k | 1.16× | 0 / 2 / 8 / 77 / 13 % | +0.008 | +0.23 [−1.07, +1.52] |
| encounter @ 4k | 1.26× | 2 / 25 / 45 / 26 / 2 % | −0.002 | −0.06 [−2.48, +2.50] |
| encounter @ 8k | 1.23× | 1 / 3 / 14 / 52 / 30 % | +0.077 | **+2.05 [+0.23, +3.91]** (worse) |
| state @ 4k | 1.13× | 18 / 30 / 27 / 19 / 6 % | −0.018 | −0.48 [−3.13, +2.22] |
| state @ 8k | 1.12× | 13 / 12 / 17 / 27 / 32 % | +0.045 | +1.19 [−1.20, +3.46] |

- Δ is the policy minus the frontier at the policy's realized CPU.
- The policies spend 1.12-1.26× the target. They predict CPU as exp(mean log CPU), which falls below mean CPU. The
  contrast is still fair, because the frontier is taken at the realized CPU.
- **No contrast has CI upper < 0. Decision: NOT_SHOWN.** One contrast (encounter @ 8k) is worse than the frontier.
- In HP all six contrasts lie between −0.05 and +1.36 HP per run, and every CI covers 0.

## Co-reported: uniform loss by act × room (Heart pp per fight / CPU s per copy)

| cell | n | 1k | 2k | 4k | 8k | 16k |
|---|---|---|---|---|---|---|
| A1 hallway | 1,500 | 0.24 / 0.1 | 0.22 / 0.1 | 0.15 / 0.3 | 0.12 / 0.6 | 0.11 / 1.2 |
| A1 elite | 703 | 5.16 / 0.2 | 4.86 / 0.3 | 4.77 / 0.7 | 4.69 / 1.4 | 4.51 / 3.1 |
| A1 boss | 252 | 7.85 / 0.3 | 7.48 / 0.7 | 6.82 / 1.5 | 6.38 / 3.2 | 6.33 / 6.9 |
| A2 hallway | 1,253 | 2.07 / 0.2 | 1.73 / 0.3 | 1.73 / 0.7 | 1.55 / 1.5 | 1.49 / 3.1 |
| A2 elite | 576 | 7.84 / 0.2 | 6.95 / 0.5 | 7.02 / 1.1 | 6.13 / 2.2 | 6.09 / 4.6 |
| A2 boss | 226 | 13.19 / 0.7 | 12.88 / 1.5 | 10.64 / 3.1 | 10.05 / 6.5 | 9.91 / 13.3 |
| A3 hallway | 1,143 | 1.18 / 0.3 | 0.70 / 0.7 | 0.41 / 1.4 | 0.21 / 2.8 | −0.07 / 5.9 |
| A3 elite | 582 | 5.65 / 0.5 | 5.01 / 1.1 | 4.72 / 2.2 | 4.21 / 4.5 | 3.55 / 9.3 |
| A3 boss | 402 | 21.17 / 1.0 | 19.20 / 2.1 | 18.13 / 4.3 | 16.11 / 8.7 | 15.44 / 18.1 |

The `?` rooms are in `results/result.json`. Cells are single means with no CI, so they are descriptive.

## Interpretation (Inference)

- **A uniform budget is again as good as a learned per-fight one.** This now holds at the cheap end (1k-16k), on our
  own states and in every Act 1-3 room, with the run-value currency. Together with §794 (16k-64k), a learned
  per-fight budget is NOT_SHOWN over the whole range that was tested. The budget curve is concave everywhere, but
  similar enough across rooms that reallocating at equal CPU buys nothing measurable.
- **The cells suggest where the hand-set H4 sits.** Act 1 hallway fights gain almost nothing from more simulations
  (0.24 → 0.11 pp from 1k to 16k). Act 3 hallway, elite and boss fights still gain at every step. This is descriptive
  only. The room policy, which could exploit exactly this, did not beat the frontier in the primary test.
- **Caveats.**
  - The currency is associational (§794), and per-fight Heart-pp do not add up to a run's Heart rate. The per-run
    figures are scaled, not measured Heart-kill rates.
  - The arms search each fight with a fresh tree (review K, R3), while the stack reuses trees across roots. Any
    budget policy would still need a whole-run gate.
  - Act 4 is not covered.

## Decision

**NOT_SHOWN.** A learned per-fight budget is parked and there is no default change. No whole-run gate follows. The
by-room curves are kept as data for hand-free per-room budgets (for example lower Act-1 hallway budgets), should the
cheap-combat roadmap want them. Seeds 111970000-111970255 have been used (data only). Cost: 88.6 lane-hours.
