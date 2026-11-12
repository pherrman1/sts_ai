# Narrow Gumbel root (P4, N4 against §775's G16 + mb4): result (2026-11-12)

Run of [PREREG.md](PREREG.md) (amended before launch; frozen in run commit 187cbad7, code 5fc8f890, binary 5dcf3125;
#1036, review K PASS on the amended version). Launched about 00:04 CET on 40 workers; last tar about 03:10 CET.

- `verify_campaign.py`: 2,080/2,080 OK, 0 missing, 0 bad, 2 duplicate tars, run 187cbad7 (`results/verify.txt`).
  Claims snapshot `results/claims.txt`.
- About 01:40-02:10 CET the tail stalled: 34 claims of 8 workers lost their heartbeat at once (share writes failed on
  those containers, about 00:41 CET); after the 90-minute lease they were re-run as attempt a2 (`claims.txt`). No game
  result was lost or counted twice.
- `python3 -I analyze.py UNITS REF_UNITS results/result.json results/claims.txt`, REF_UNITS = §775's `*_low` tars
  extracted. 0 bad games, 0 env mismatches, 2 combat aborts (N4 on 111378756 and 111379220, counted losses), 0 dropped
  seeds.
- Cost 181.4 lane-h (sum of game walls; plan 120-180).

## Sentinel

32 of 32 G16 games identical to §775's → **REUSE_VALID**; §775's 1,024 G16 games are the control. The same games took
1.05× §775's CPU here, the machine-speed correction below.

## Primary (alpha 0.025 per arm)

| | G16 (§775) | P4 | N4 |
|---|---|---|---|
| Heart kill | 41.21% | 32.81% | 33.89% |
| Act-4 reach (final floor ≥ 52) | 49.22% | 43.16% | 44.43% |
| Mean final floor | 41.58 | 39.61 | 39.83 |
| CPU s per run (mean) | 512.1 | 306.2 | 317.1 |
| CPU s per run median / p90 / p99 / max | 378 / 1,163 / 1,955 / 3,036 | 133 / 778 / 1,556 / 2,152 | 140 / 823 / 1,420 / 7,656 |

- **P4 − G16: −8.40 pp, 95% CI [−11.43, −5.37]** (= the one-sided 97.5% bounds). 84 seeds kill only with P4, 170 only
  with G16. SPRT nonregression accepts H0 at 512 seeds (LLR −3.12) → **WORSE**. Act-4 reach −6.05 pp [−8.98, −3.13];
  final floor −1.98 [−2.99, −0.96].
- **N4 − G16: −7.32 pp [−10.16, −4.39]**. 79 / 154 seeds kill only with N4 / G16. SPRT accepts H0 at 576 (LLR −2.99)
  → **WORSE**. Act-4 reach −4.79 pp [−7.72, −1.86]; final floor −1.75 [−2.70, −0.81].
- Gainer SPRTs: both NOT_SHOWN (H0 at 384 / 512).
- **Cost:** CPU per run P4 **0.598×** [0.562, 0.637] raw, 0.569× machine-corrected; N4 **0.619×** [0.578, 0.668], 0.590×.
  Gumbel simulations per run 0.507× / 0.535×. N4's maximum (7,656 s) is a combat-abort game (stall).

## Secondary

- **N4 − P4: +1.07 pp [−1.86, +4.10]** (127 / 116 seeds kill only with N4 / P4), Act-4 reach +1.27 pp: the net's top 4
  is not shown to be better than g7f_E's.
- Losses per 1,024 runs by final floor ≤ 17 / ≤ 34 / ≤ 51 / ≥ 52 (descriptive): G16 185 / 192 / 143 / 82, P4 209 / 224
  / 149 / 106, N4 202 / 230 / 137 / 108. The loss is spread over Acts 1, 2 and 4.
- Against E0's GP16 (§790, same seeds, not paired here): GP16 35.74% at 143 s; P4 and N4 have a lower Heart rate at
  about twice GP16's CPU.

## Interpretation (Inference)

Halving the root budget and keeping 4 deterministic candidates costs about 7-8 pp of Heart kills for 40% of the CPU.
That is close to §781's plain budget curve (16k → 8k about −6 pp at 0.61× CPU), so the narrow root did not buy
anything over simply halving the budget; step 0's 88.6-91.9% top-4 coverage was not enough. The distilled net's
candidates are at most slightly better than the prior's. Removing prior playouts (GP16) is the far better saving per
lost Heart kill. On this roadmap the root width and root budget are not where the cheap 40% is.

## Decision

Both arms WORSE by the pre-registered rule. No default change; the flag stays default 1. Per the PREREG, the
per-encounter budget work starts from G16 + mb4 and GP16.
