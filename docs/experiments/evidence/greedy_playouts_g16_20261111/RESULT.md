# Greedy playouts in G16 (GP16 against §775's G16 + mb4): result (2026-11-11)

Run of [PREREG.md](PREREG.md) (frozen in run commit 06e170db, code 966de5f7, binary 7f2800f0; #1035, review K
PASS). Launched about 23:15 CET on 40 workers; last unit started 23:37 CET, all done by 23:44 CET.

- `verify_campaign.py`: 1,056/1,056 OK, 0 missing, 0 bad, 1 duplicate tar (111379189_GP16, a re-claimed unit),
  run 06e170db, 40/40 DONE.json (`results/verify.txt`). Claims snapshot `results/claims.txt`.
- `python3 -I analyze.py UNITS REF_UNITS results/result.json results/claims.txt`, REF_UNITS = §775's `*_low` tars
  extracted. 0 bad games, 0 env mismatches, 0 aborts, 0 dropped seeds.
- Cost 44.7 lane-h (sum of game walls; plan 50-80).

## Sentinel

32 of 32 G16 games identical to §775's → **REUSE_VALID**; §775's 1,024 G16 games are the control. The same games took
1.05× §775's CPU here, the machine-speed correction below.

## Primary

| | G16 (§775) | GP16 |
|---|---|---|
| Heart kill | 41.21% | 35.74% |
| Act-4 reach (final floor ≥ 52) | 49.22% | 46.29% |
| Mean final floor | 41.58 | 40.75 |
| CPU s per run (mean) | 512.1 | 143.3 |
| CPU s per run median / p90 / p99 / max | 378 / 1,163 / 1,955 / 3,036 | 132 / 300 / 431 / 587 |

- **d = −5.47 pp, 95% CI [−8.11, −2.93]**. 67 seeds kill only with GP16, 123 only with G16. One-sided 95% bounds
  [−7.62, −3.32].
- SPRT nonregression (H0 −1.5 pp, H1 0): accepts H0 at 768 seeds (LLR −3.22) → **WORSE**. The gainer SPRT accepts H0
  at 384 (NOT_SHOWN).
- Act-4 reach −2.93 pp [−5.37, −0.49]; final floor −0.83 [−1.50, −0.19].
- **Cost:** CPU per run **0.280×** [0.270, 0.291] raw, **0.267×** corrected for machine speed. Gumbel simulations per
  run 0.968× (runs end earlier); the budget is unchanged.

## Secondary

- GP16 − D (§775's A20 default combat): **+4.10 pp [+1.07, +7.03]** Heart (31.64% → 35.74%), Act-4 reach +5.18 pp, at
  0.567× D's CPU (143 s vs 253 s).
- Where the runs end (descriptive; losses per 1,024 runs by final floor ≤ 17 / ≤ 34 / ≤ 51 / ≥ 52, G16 → GP16): Act 1 185 → 201, Act 2
  192 → 209, Act 3 143 → 140, Act 4 82 → 108. About half of the loss is the Act-4 conversion (Shield and Spear and the
  Heart, where ADR-0050/0060's prior playouts ran), the rest Act 1-2 (boss rooms).

## Interpretation (Inference)

Prior playouts in boss rooms and Act 4 are worth about 5 pp of Heart kills at 16k, more than §541's fight-level
evidence implied, and they cost about 3/4 of G16's CPU. GP16 is still the best point found so far for its cost: 35.7%
at 143 s per run, against §781's budget curve (G8S 31.6% at 166 s, G1S 24.4% at 137 s) and +4.1 pp over D at 0.57× its
CPU. Its longest game (587 s) is 5× shorter than G16's (3,036 s), which matters for the PPO loop's
slowest-game constraint. The prior playouts' value is concentrated where few simulations are spent per run: a
per-encounter budget (prior playouts and simulation count per encounter class) is the natural next step.

## Decision

WORSE by the pre-registered rule. No default change. Not the 40% candidate on its own; it is the cheap base for the
per-encounter budget work (Philipp's go, 2026-11-11 23:43 CET). The narrow-root campaign's base arm (its PREREG: G16
when this is WORSE) is put to Philipp, because the CPU target favours the GP16 base.
