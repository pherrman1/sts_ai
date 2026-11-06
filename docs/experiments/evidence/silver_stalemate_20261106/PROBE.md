# Stall-fix probe: STALL / MAXB / BOTH / CEIL / CEIL_MAXB on the stall seeds (2026-11-06)

Copied from Philipp's PC (`~/longc-diag-out/stalemate/PROBE.md`, md5 07cbfd2955b63cc6c36ee4971cc63a24) for ledger
§759; paths below are on that PC. Diag patch, runner and raw logs stay local. STALL = the first variant
`STS_SILVER_STALL_LEAF` (commit ba996dee), replaced by `STS_SILVER_LOSS_CEILING` (CEIL) in 4cb624e4.

## Setup
- **Fights:** the 16 fights of ≥ 400 turns in `taskC/replay18.txt`. These are 12 × 3 Sentries (seed/floor: 111558435/8,
  111610012/12, 111583124/6, 111570033/10, 111604302/8, 111593733/12, 111572948/7, 111568362/12, 111554888/12,
  111560448/8, 111601380/11, 111557779/8) and 4 × Shapes (111619871/36, 111595870/37, 111565805/47, 111680130/44, the
  last being the Fiend Fire fight). The 12 Sentry fights plus 111619871 and 111595870 are the 14 stall seeds from
  REPORT.md; 111565805 and 111680130 were added. Each is a whole-run replay with the original run's actor settings
  (actors_frozen.env, its arm, salt and net), through `tools/seed_guard.sh`, at nice 10 with no GPU. LONG_C was not touched.
- **Code:**
  - STALL / MAXB / BOTH: `~/sts-stall-probe` (detached at ba996deed).
  - CEIL / CEIL_MAXB: `~/sts-ceil-probe` (detached at 4cb624e46).
  - Both worktrees were created with `tools/agent/worktree.py create --detach`. Both carry the REPORT.md/FIENDFIRE.md diag
    patch (local, uncommitted: `probe/diag_patch_probe.diff`, `probe/diag_live.h`) and the probe switches below.
  - ba996dee's one_combat rejects `STS_SILVER_MAX_BACKUP` (exit 2). So MAXB/BOTH ran on a separate build
    (`~/sts-stall-probe/build/probe-mb`) with that one name added to the allowlist locally. 4cb624e4 accepts it natively.
- **Gating:** `STS_PROBE_ARM_FLOOR=F` (local diag) turns the research arm on only for the target fight's floor. Every arm
  therefore reaches the fight with the identical run state. `STS_PROBE_EXIT_AFTER_FLOOR=F` stops the process when that
  fight ends. Runner: `probe/run_probe.sh`; job lists: `probe/jobs*.txt`; analysis: `probe/analyze.py` → `probe/table.md`.
- **Reproduction checks** (all pass):
  - BASE at ba996dee reproduces the original replays (`~/longc-diag-out/replay/<seed>/stderr.log`) line for line for
    every fight. I compared every DIAG decision line (state, HP, piles, monsters) of the target floor, for all 16 seeds.
  - BASE_mb (the allowlist build) and BASE_ceil (4cb624e4) are identical to BASE on every compared fight: 2 seeds for
    BASE_mb, all 16 for BASE_ceil.
- **Arms:**
  - BASE: nothing set.
  - STALL: `STS_SILVER_STALL_LEAF=1`.
  - MAXB: `STS_SILVER_MAX_BACKUP=4`.
  - BOTH: STALL + MAXB.
  - CEIL: `STS_SILVER_LOSS_CEILING=1`.
  - CEIL_MAXB: CEIL + MAXB.
  - The `STS_COMBAT_TURN_CAP=100` arm was skipped: no such env var exists in 4cb624e4 (no turn-cap getenv anywhere in
    src, include or apps).
- **Columns:**
  - turns: `bc.turn` at fight end (the `DIAGFIGHTEND` line), counted from 0. No fight in this probe was won after
    turn 500: every win is at turn ≤ 500 and every cap loss is at 501. `BattleContext::executeActions`
    (src/combat/BattleContext.cpp:1061–1066 at 4cb624e4) sets PLAYER_LOSS as soon as `turn > 500`, so the latest
    possible win is during turn 500. replay18.txt counts one more for wins (e.g. 498 here = 499 there) and 501 for cap losses.
  - fight wall: the sum of per-decision dt for the target fight. Runs shared the CPU 8–10 ways with Firefox, so treat wall
    times as rough. Example: BASE_mb ran the same decisions as BASE, but under heavier load (333 s vs 33 s).
  - first diverging turn: the first turn at which the arm's chosen action at a root differs from BASE's.

## Headline
- **MAXB, BOTH and CEIL_MAXB end every stall quickly.** All 16 fights are won, in 3–26 turns, at end HP equal to or higher
  than BASE in 15/16 fights (e.g. 111604302: 13 → 53–57 HP; 111568362: 18 → 49). The exception is 111557779, at 40 vs
  42 HP. The 16 include all 4 Shapes fights that BASE lost at the 501-turn cap. They change play from turn 0–3 of these fights, as expected: max-backup changes every selection.
- **STALL** leaves all 12 Sentry fights identical until turns 489–499, or for the whole fight. It turns the 3 Shapes cap
  losses (111619871, 111595870, 111565805) into wins, but only at turns 499–500. On 111680130 it avoids the turn-4 Fiend
  Fire but diverges from turn 1. It then dies at turn 84: Burning Pact lines worth about 130–140 score above wins at about
  75, because deaths still earn survival credit.
- **CEIL** (loss ceiling): on 111680130 it **wins on turn 4 at 32/75 HP**. There is no turn-4 Fiend Fire on the Spiker
  (it plays Fiend Fire on a Repulsor at turn 1) and no Burning Pact death spiral. It wins 111565805 on turn 19, and the
  other two Shapes cap losses (111619871, 111595870) at turn 499 (late). Among the Sentry fights it shortens 3 (111583124: 263,
  111570033: 20, 111560448: 23). The other 9 stay at 424–500 turns, identical to BASE or diverging only after turn 489.
  **CEIL changes play within the first 20 turns in 5/16 fights** (111680130 t0, 111570033 t0, 111565805 t0,
  111583124 t2, 111560448 t2). In the other 11 it is identical to BASE until turn ≥ 489, or for the whole fight.
  The all-win Sentry stalemate (End Turn ahead on the potion artefact) is not a loss-value problem, so CEIL alone leaves it.
- **CEIL_MAXB** ≈ MAXB. Same outcome on all 16. Turns are the same or ±3. End HP is the same or higher
  (111680130: 24 vs 19; 111604302: 57 vs 53; 111583124: 37 vs 35).

## 111680130 floor 44 (Fiend Fire fight)
| arm | turn-4 Fiend Fire → Spiker | Burning Pact death spiral | result |
|---|---|---|---|
| BASE | yes (282 visits, mean 81.2 with 0 wins; see FIENDFIRE.md) | — | loss at the 501 turn cap, 17 HP, 1100 s fight |
| STALL | no (Burning Pact chosen, mean 129.7 with 419/514 deaths) | **yes**: attacks burned, Spiker 38 and Repulsor 3 HP left | death at turn 84 |
| MAXB | no | no | **win turn 3, 19 HP** |
| BOTH | no | no | **win turn 3, 24 HP** |
| CEIL | no (Fiend Fire on a Repulsor at turn 1; turn 4 opens with Bludgeon → Spiker) | no | **win turn 4, 32 HP** |
| CEIL_MAXB | no (Fiend Fire on a Repulsor at turn 1) | no | **win turn 3, 24 HP** |

## Stall-phase roots (End Turn vs most-visited card play, visits/mean)
The stall onset is the first BASE root at turn ≥ 3 where Silver ends the turn with energy left and a card play available.
The first three roots at or after that turn are listed for each arm (column "stall roots" in the table below). In BASE,
End Turn and the top card are within 0.2–2 mean points at every onset (e.g. 111558435 t4: End 114/109.7 vs card
137/110.1, then End 227/111.9 vs 120/109.9). That is the tie described in REPORT.md. STALL and CEIL show the same numbers
where they have not yet diverged. MAXB changes the selection value, not the means, so its roots are not comparable
one-for-one.

## Full table
| seed | floor | arm | outcome | turns | end HP | fight wall s | proc wall | first diverging turn vs BASE | stall roots (turn: End v/mean vs top card v/mean) |
|---|---|---|---|---|---|---|---|---|---|
| 111558435 | 8 | BASE | WIN | 498 | 49/75 | 33.5 | 0:34.74 | — | onset t4: t4: E 114/109.7 vs 137/110.1; t4: E 227/111.9 vs 120/109.9; t5: E 606/108.0 vs 306/106.5 |
| 111558435 | 8 | STALL | WIN | 499 | 49/75 | 41.3 | 0:42.76 | t489 | onset t4: t4: E 114/109.7 vs 137/110.1; t4: E 227/111.9 vs 120/109.9; t5: E 606/108.0 vs 306/106.5 |
| 111558435 | 8 | MAXB | WIN | 16 | 49/75 | 5.7 | 0:13.81 | t0 (<20!) | onset t4: t4: E 98/110.0 vs 126/106.1; t4: E 125/110.1 vs 239/108.0; t4: E 201/111.3 vs 665/111.5 |
| 111558435 | 8 | BOTH | WIN | 16 | 49/75 | 5.6 | 0:12.90 | t0 (<20!) | onset t4: t4: E 98/110.0 vs 126/106.1; t4: E 125/110.1 vs 239/108.0; t4: E 201/111.3 vs 665/111.5 |
| 111558435 | 8 | BASE_mb | WIN | 498 | 49/75 | 333.3 | 5:41.98 | none | onset t4: t4: E 114/109.7 vs 137/110.1; t4: E 227/111.9 vs 120/109.9; t5: E 606/108.0 vs 306/106.5 |
| 111558435 | 8 | BASE_ceil | WIN | 498 | 49/75 | 45.1 | 0:46.57 | none | onset t4: t4: E 114/109.7 vs 137/110.1; t4: E 227/111.9 vs 120/109.9; t5: E 606/108.0 vs 306/106.5 |
| 111558435 | 8 | CEIL | WIN | 500 | 49/75 | 45.7 | 0:47.24 | t489 | onset t4: t4: E 114/109.7 vs 137/110.1; t4: E 227/111.9 vs 120/109.9; t5: E 606/108.0 vs 306/106.5 |
| 111558435 | 8 | CEIL_MAXB | WIN | 16 | 49/75 | 1.1 | 0:02.53 | t0 (<20!) | onset t4: t4: E 98/110.0 vs 126/106.1; t4: E 125/110.1 vs 239/108.0; t4: E 201/111.3 vs 665/111.5 |
| 111619871 | 36 | BASE | LOSS | 501 | 34/97 | 980.1 | 16:48.18 | — | onset t3: t3: E 168/171.4 vs 135/170.6; t4: E 138/170.2 vs 136/169.9; t5: E 77/164.1 vs 190/166.7 |
| 111619871 | 36 | STALL | WIN | 500 | 34/97 | 971.0 | 16:40.82 | t499 | onset t3: t3: E 168/171.4 vs 135/170.6; t4: E 138/170.2 vs 136/169.9; t5: E 77/164.1 vs 190/166.7 |
| 111619871 | 36 | MAXB | WIN | 3 | 64/97 | 1.0 | 5:07.96 | t0 (<20!) | onset t3: t3: E 71/170.3 vs 173/171.5; t3: E 101/171.0 vs 217/171.8; t3: E 144/171.1 vs 352/172.9 |
| 111619871 | 36 | BOTH | WIN | 3 | 64/97 | 0.9 | 5:11.87 | t0 (<20!) | onset t3: t3: E 71/170.3 vs 173/171.5; t3: E 101/171.0 vs 217/171.8; t3: E 144/171.1 vs 352/172.9 |
| 111619871 | 36 | BASE_ceil | LOSS | 501 | 34/97 | 869.3 | 15:00.97 | none | onset t3: t3: E 168/171.4 vs 135/170.6; t4: E 138/170.2 vs 136/169.9; t5: E 77/164.1 vs 190/166.7 |
| 111619871 | 36 | CEIL | WIN | 499 | 34/97 | 859.3 | 14:50.92 | t499 | onset t3: t3: E 168/171.4 vs 135/170.6; t4: E 138/170.2 vs 136/169.9; t5: E 77/164.1 vs 190/166.7 |
| 111619871 | 36 | CEIL_MAXB | WIN | 3 | 64/97 | 0.2 | 0:31.58 | t0 (<20!) | onset t3: t3: E 71/170.3 vs 173/171.5; t3: E 101/171.0 vs 217/171.8; t3: E 144/171.1 vs 352/172.9 |
| 111680130 | 44 | BASE | LOSS | 501 | 17/75 | 1099.9 | 18:29.85 | — | onset t6: t6: E 1708/84.4 vs 1695/84.4; t7: E 754/84.3 vs 764/84.3; t8: E 1478/84.3 vs 1525/84.3 |
| 111680130 | 44 | STALL | LOSS | 84 | 0/75 | 31.3 | 0:40.04 | t1 (<20!) | onset t6: t6: E 1070/126.0 vs 2204/126.6; t6: E 2549/125.1 vs 1653/124.7; t7: E 374/115.8 vs 900/116.5 |
| 111680130 | 44 | MAXB | WIN | 3 | 19/75 | 1.8 | 1:18.57 | t1 (<20!) | onset t6:  |
| 111680130 | 44 | BOTH | WIN | 3 | 24/75 | 1.3 | 1:18.63 | t1 (<20!) | onset t6:  |
| 111680130 | 44 | BASE_ceil | LOSS | 501 | 17/75 | 989.4 | 16:38.33 | none | onset t6: t6: E 1708/84.4 vs 1695/84.4; t7: E 754/84.3 vs 764/84.3; t8: E 1478/84.3 vs 1525/84.3 |
| 111680130 | 44 | CEIL | WIN | 4 | 32/75 | 0.2 | 0:09.49 | t0 (<20!) | onset t6:  |
| 111680130 | 44 | CEIL_MAXB | WIN | 3 | 24/75 | 0.2 | 0:09.35 | t0 (<20!) | onset t6:  |
| 111595870 | 37 | BASE | LOSS | 501 | 101/110 | 23.6 | 0:38.61 | — | onset t3: t3: E 286/176.9 vs 235/176.2; t4: E 137/172.3 vs 117/171.4; t5: E 50/165.5 vs 124/168.6 |
| 111595870 | 37 | STALL | WIN | 499 | 101/110 | 28.3 | 0:41.09 | t499 | onset t3: t3: E 286/176.9 vs 235/176.2; t4: E 137/172.3 vs 117/171.4; t5: E 50/165.5 vs 124/168.6 |
| 111595870 | 37 | MAXB | WIN | 6 | 110/110 | 2.1 | 1:58.33 | t0 (<20!) | onset t3: t3: E 167/180.4 vs 225/175.1; t3: E 182/179.2 vs 396/177.7; t3: E 1030/179.1 vs 258/176.1 |
| 111595870 | 37 | BOTH | WIN | 6 | 110/110 | 2.2 | 2:05.47 | t0 (<20!) | onset t3: t3: E 167/180.4 vs 225/175.1; t3: E 182/179.2 vs 396/177.7; t3: E 1030/179.1 vs 258/176.1 |
| 111595870 | 37 | BASE_mb | LOSS | 501 | 101/110 | 240.1 | 5:52.90 | none | onset t3: t3: E 286/176.9 vs 235/176.2; t4: E 137/172.3 vs 117/171.4; t5: E 50/165.5 vs 124/168.6 |
| 111595870 | 37 | BASE_ceil | LOSS | 501 | 101/110 | 28.6 | 0:43.19 | none | onset t3: t3: E 286/176.9 vs 235/176.2; t4: E 137/172.3 vs 117/171.4; t5: E 50/165.5 vs 124/168.6 |
| 111595870 | 37 | CEIL | WIN | 499 | 101/110 | 28.8 | 0:42.89 | t499 | onset t3: t3: E 286/176.9 vs 235/176.2; t4: E 137/172.3 vs 117/171.4; t5: E 50/165.5 vs 124/168.6 |
| 111595870 | 37 | CEIL_MAXB | WIN | 6 | 110/110 | 0.3 | 0:13.91 | t0 (<20!) | onset t3: t3: E 167/180.4 vs 225/175.1; t3: E 182/179.2 vs 396/177.7; t3: E 1030/179.1 vs 258/176.1 |
| 111610012 | 12 | BASE | WIN | 497 | 65/75 | 27.6 | 0:29.61 | — | onset t3: t3: E 26/125.8 vs 295/134.6; t3: E 234/135.2 vs 333/135.6; t3: E 534/137.5 vs 249/136.0 |
| 111610012 | 12 | STALL | WIN | 497 | 65/75 | 25.0 | 0:26.83 | none | onset t3: t3: E 26/125.8 vs 295/134.6; t3: E 234/135.2 vs 333/135.6; t3: E 534/137.5 vs 249/136.0 |
| 111610012 | 12 | MAXB | WIN | 14 | 65/75 | 2.4 | 0:15.87 | t0 (<20!) | onset t3: t3: E 24/130.6 vs 314/136.8; t3: E 343/138.9 vs 339/137.2; t4: E 79/139.0 vs 140/136.6 |
| 111610012 | 12 | BOTH | WIN | 14 | 65/75 | 2.2 | 0:17.15 | t0 (<20!) | onset t3: t3: E 24/130.6 vs 314/136.8; t3: E 343/138.9 vs 339/137.2; t4: E 79/139.0 vs 140/136.6 |
| 111610012 | 12 | BASE_ceil | WIN | 497 | 65/75 | 26.2 | 0:28.26 | none | onset t3: t3: E 26/125.8 vs 295/134.6; t3: E 234/135.2 vs 333/135.6; t3: E 534/137.5 vs 249/136.0 |
| 111610012 | 12 | CEIL | WIN | 497 | 65/75 | 26.8 | 0:28.88 | none | onset t3: t3: E 26/125.8 vs 295/134.6; t3: E 234/135.2 vs 333/135.6; t3: E 534/137.5 vs 249/136.0 |
| 111610012 | 12 | CEIL_MAXB | WIN | 14 | 65/75 | 0.4 | 0:02.45 | t0 (<20!) | onset t3: t3: E 24/130.6 vs 314/136.8; t3: E 343/138.9 vs 339/137.2; t4: E 79/139.0 vs 140/136.6 |
| 111583124 | 6 | BASE | WIN | 496 | 24/75 | 19.7 | 0:20.42 | — | onset t3: t3: E 64/97.4 vs 380/102.0; t3: E 177/101.2 vs 389/102.7; t3: E 390/103.4 vs 350/103.1 |
| 111583124 | 6 | STALL | WIN | 496 | 24/75 | 19.7 | 0:20.48 | none | onset t3: t3: E 64/97.4 vs 380/102.0; t3: E 177/101.2 vs 389/102.7; t3: E 390/103.4 vs 350/103.1 |
| 111583124 | 6 | MAXB | WIN | 26 | 35/75 | 7.1 | 0:11.79 | t0 (<20!) | onset t3: t3: E 29/96.1 vs 337/99.8; t3: E 107/100.2 vs 484/100.4; t3: E 417/102.7 vs 438/101.7 |
| 111583124 | 6 | BOTH | WIN | 26 | 35/75 | 8.6 | 0:13.13 | t0 (<20!) | onset t3: t3: E 29/96.1 vs 337/99.8; t3: E 107/100.2 vs 484/100.4; t3: E 417/102.7 vs 438/101.7 |
| 111583124 | 6 | BASE_ceil | WIN | 496 | 24/75 | 25.3 | 0:26.23 | none | onset t3: t3: E 64/97.4 vs 380/102.0; t3: E 177/101.2 vs 389/102.7; t3: E 390/103.4 vs 350/103.1 |
| 111583124 | 6 | CEIL | WIN | 263 | 30/75 | 8.3 | 0:09.16 | t2 (<20!) | onset t3: t3: E 64/97.4 vs 380/102.0; t3: E 177/101.2 vs 389/102.7; t3: E 390/103.4 vs 350/103.1 |
| 111583124 | 6 | CEIL_MAXB | WIN | 23 | 37/75 | 1.0 | 0:01.85 | t3 (<20!) | onset t3: t3: E 23/95.4 vs 317/100.7; t3: E 143/100.8 vs 455/100.3; t3: E 389/102.5 vs 458/101.6 |
| 111570033 | 10 | BASE | WIN | 442 | 28/75 | 25.4 | 0:26.85 | — | onset t3: t3: E 62/87.9 vs 403/92.6; t3: E 119/91.5 vs 692/95.0; t3: E 610/96.2 vs 385/95.1 |
| 111570033 | 10 | STALL | WIN | 442 | 28/75 | 26.2 | 0:27.45 | none | onset t3: t3: E 62/87.9 vs 403/92.6; t3: E 119/91.5 vs 692/95.0; t3: E 610/96.2 vs 385/95.1 |
| 111570033 | 10 | MAXB | WIN | 12 | 35/75 | 3.6 | 0:13.50 | t0 (<20!) | onset t3: t3: E 137/98.0 vs 245/96.7; t3: E 226/98.2 vs 912/96.6; t4: E 283/96.5 vs 623/96.8 |
| 111570033 | 10 | BOTH | WIN | 12 | 35/75 | 3.5 | 0:14.00 | t0 (<20!) | onset t3: t3: E 137/98.0 vs 245/96.7; t3: E 226/98.2 vs 912/96.6; t4: E 283/96.5 vs 623/96.8 |
| 111570033 | 10 | BASE_ceil | WIN | 442 | 28/75 | 28.0 | 0:29.43 | none | onset t3: t3: E 62/87.9 vs 403/92.6; t3: E 119/91.5 vs 692/95.0; t3: E 610/96.2 vs 385/95.1 |
| 111570033 | 10 | CEIL | WIN | 20 | 34/75 | 0.6 | 0:02.03 | t0 (<20!) | onset t3: t3: E 151/97.3 vs 156/97.0; t3: E 336/97.5 vs 289/96.7; t4: E 540/95.7 vs 356/94.9 |
| 111570033 | 10 | CEIL_MAXB | WIN | 12 | 35/75 | 0.5 | 0:01.85 | t0 (<20!) | onset t3: t3: E 137/98.0 vs 245/96.7; t3: E 226/98.2 vs 912/96.6; t4: E 283/96.5 vs 623/96.8 |
| 111604302 | 8 | BASE | WIN | 433 | 13/75 | 17.3 | 0:18.68 | — | onset t4: t4: E 215/112.2 vs 253/112.2; t4: E 686/113.6 vs 488/112.9; t5: E 283/113.8 vs 310/113.6 |
| 111604302 | 8 | STALL | WIN | 433 | 13/75 | 22.4 | 0:23.75 | none | onset t4: t4: E 215/112.2 vs 253/112.2; t4: E 686/113.6 vs 488/112.9; t5: E 283/113.8 vs 310/113.6 |
| 111604302 | 8 | MAXB | WIN | 21 | 53/75 | 8.0 | 0:16.61 | t0 (<20!) | onset t4: t4: E 99/107.9 vs 275/107.7; t4: E 798/108.8 vs 376/107.2; t5: E 111/110.2 vs 355/109.7 |
| 111604302 | 8 | BOTH | WIN | 21 | 53/75 | 6.2 | 0:13.48 | t0 (<20!) | onset t4: t4: E 99/107.9 vs 275/107.7; t4: E 798/108.8 vs 376/107.2; t5: E 111/110.2 vs 355/109.7 |
| 111604302 | 8 | BASE_ceil | WIN | 433 | 13/75 | 18.7 | 0:20.14 | none | onset t4: t4: E 215/112.2 vs 253/112.2; t4: E 686/113.6 vs 488/112.9; t5: E 283/113.8 vs 310/113.6 |
| 111604302 | 8 | CEIL | WIN | 433 | 13/75 | 21.0 | 0:22.41 | none | onset t4: t4: E 215/112.2 vs 253/112.2; t4: E 686/113.6 vs 488/112.9; t5: E 283/113.8 vs 310/113.6 |
| 111604302 | 8 | CEIL_MAXB | WIN | 24 | 57/75 | 1.4 | 0:02.80 | t0 (<20!) | onset t4: t4: E 107/112.3 vs 237/112.4; t4: E 445/112.3 vs 671/112.0; t5: E 94/113.0 vs 447/113.4 |
| 111593733 | 12 | BASE | WIN | 499 | 50/75 | 17.0 | 0:18.46 | — | onset t3: t3: E 219/124.5 vs 197/124.2; t4: E 389/122.2 vs 223/120.9; t5: E 247/123.5 vs 263/123.6 |
| 111593733 | 12 | STALL | WIN | 499 | 50/75 | 17.5 | 0:19.06 | t497 | onset t3: t3: E 219/124.5 vs 197/124.2; t4: E 389/122.2 vs 223/120.9; t5: E 247/123.5 vs 263/123.6 |
| 111593733 | 12 | MAXB | WIN | 7 | 50/75 | 2.2 | 0:11.47 | t0 (<20!) | onset t3: t3: E 230/126.4 vs 246/124.2; t3: E 690/125.3 vs 471/124.4; t4: E 94/126.9 vs 157/124.7 |
| 111593733 | 12 | BOTH | WIN | 7 | 50/75 | 2.1 | 0:12.50 | t0 (<20!) | onset t3: t3: E 230/126.4 vs 246/124.2; t3: E 690/125.3 vs 471/124.4; t4: E 94/126.9 vs 157/124.7 |
| 111593733 | 12 | BASE_ceil | WIN | 499 | 50/75 | 19.1 | 0:20.60 | none | onset t3: t3: E 219/124.5 vs 197/124.2; t4: E 389/122.2 vs 223/120.9; t5: E 247/123.5 vs 263/123.6 |
| 111593733 | 12 | CEIL | WIN | 499 | 50/75 | 17.5 | 0:18.91 | t497 | onset t3: t3: E 219/124.5 vs 197/124.2; t4: E 389/122.2 vs 223/120.9; t5: E 247/123.5 vs 263/123.6 |
| 111593733 | 12 | CEIL_MAXB | WIN | 7 | 50/75 | 0.3 | 0:01.72 | t0 (<20!) | onset t3: t3: E 230/126.4 vs 246/124.2; t3: E 690/125.3 vs 471/124.4; t4: E 94/126.9 vs 157/124.7 |
| 111572948 | 7 | BASE | WIN | 497 | 27/75 | 20.0 | 0:20.69 | — | onset t3: t3: E 74/102.9 vs 286/106.5; t3: E 102/105.8 vs 222/107.9; t3: E 284/108.3 vs 260/107.6 |
| 111572948 | 7 | STALL | WIN | 497 | 27/75 | 18.1 | 0:18.94 | t494 | onset t3: t3: E 74/102.9 vs 286/106.5; t3: E 102/105.8 vs 222/107.9; t3: E 284/108.3 vs 260/107.6 |
| 111572948 | 7 | MAXB | WIN | 12 | 35/75 | 3.7 | 0:08.56 | t1 (<20!) | onset t3: t3: E 36/103.6 vs 295/106.1; t3: E 59/103.8 vs 622/106.8; t3: E 106/105.8 vs 491/107.6 |
| 111572948 | 7 | BOTH | WIN | 12 | 35/75 | 3.8 | 0:08.90 | t1 (<20!) | onset t3: t3: E 36/103.6 vs 295/106.1; t3: E 59/103.8 vs 622/106.8; t3: E 106/105.8 vs 491/107.6 |
| 111572948 | 7 | BASE_ceil | WIN | 497 | 27/75 | 20.9 | 0:21.75 | none | onset t3: t3: E 74/102.9 vs 286/106.5; t3: E 102/105.8 vs 222/107.9; t3: E 284/108.3 vs 260/107.6 |
| 111572948 | 7 | CEIL | WIN | 496 | 27/75 | 19.1 | 0:19.92 | t493 | onset t3: t3: E 74/102.9 vs 286/106.5; t3: E 102/105.8 vs 222/107.9; t3: E 284/108.3 vs 260/107.6 |
| 111572948 | 7 | CEIL_MAXB | WIN | 12 | 35/75 | 0.5 | 0:01.35 | t2 (<20!) | onset t3: t3: E 36/103.6 vs 295/106.1; t3: E 59/103.8 vs 622/106.8; t3: E 106/105.8 vs 491/107.6 |
| 111568362 | 12 | BASE | WIN | 499 | 18/99 | 23.7 | 0:25.10 | — | onset t4: t4: E 383/127.6 vs 304/127.1; t5: E 386/127.3 vs 296/126.6; t6: E 237/125.9 vs 258/125.9 |
| 111568362 | 12 | STALL | WIN | 499 | 18/99 | 26.6 | 0:28.06 | none | onset t4: t4: E 383/127.6 vs 304/127.1; t5: E 386/127.3 vs 296/126.6; t6: E 237/125.9 vs 258/125.9 |
| 111568362 | 12 | MAXB | WIN | 10 | 49/99 | 1.5 | 0:10.05 | t0 (<20!) | onset t4: t4: E 262/125.4 vs 393/124.6; t5: E 136/125.4 vs 216/124.4; t5: E 415/124.6 vs 434/123.9 |
| 111568362 | 12 | BOTH | WIN | 10 | 49/99 | 2.0 | 0:13.31 | t0 (<20!) | onset t4: t4: E 262/125.4 vs 393/124.6; t5: E 136/125.4 vs 216/124.4; t5: E 415/124.6 vs 434/123.9 |
| 111568362 | 12 | BASE_ceil | WIN | 499 | 18/99 | 26.1 | 0:27.49 | none | onset t4: t4: E 383/127.6 vs 304/127.1; t5: E 386/127.3 vs 296/126.6; t6: E 237/125.9 vs 258/125.9 |
| 111568362 | 12 | CEIL | WIN | 499 | 18/99 | 22.5 | 0:23.90 | t497 | onset t4: t4: E 383/127.6 vs 304/127.1; t5: E 386/127.3 vs 296/126.6; t6: E 237/125.9 vs 258/125.9 |
| 111568362 | 12 | CEIL_MAXB | WIN | 10 | 49/99 | 0.3 | 0:01.69 | t0 (<20!) | onset t4: t4: E 262/125.4 vs 393/124.6; t5: E 136/125.4 vs 216/124.4; t5: E 415/124.6 vs 434/123.9 |
| 111554888 | 12 | BASE | WIN | 496 | 34/75 | 29.0 | 0:30.82 | — | onset t3: t3: E 42/96.3 vs 768/104.5; t3: E 534/105.5 vs 344/104.6; t4: E 214/105.1 vs 170/104.5 |
| 111554888 | 12 | STALL | WIN | 496 | 34/75 | 25.4 | 0:27.03 | none | onset t3: t3: E 42/96.3 vs 768/104.5; t3: E 534/105.5 vs 344/104.6; t4: E 214/105.1 vs 170/104.5 |
| 111554888 | 12 | MAXB | WIN | 12 | 40/75 | 2.4 | 0:16.06 | t0 (<20!) | onset t3: t3: E 125/110.5 vs 651/109.9; t3: E 226/110.6 vs 533/110.4; t3: E 693/111.3 vs 725/110.9 |
| 111554888 | 12 | BOTH | WIN | 12 | 40/75 | 1.9 | 0:12.27 | t0 (<20!) | onset t3: t3: E 125/110.5 vs 651/109.9; t3: E 226/110.6 vs 533/110.4; t3: E 693/111.3 vs 725/110.9 |
| 111554888 | 12 | BASE_ceil | WIN | 496 | 34/75 | 25.6 | 0:27.45 | none | onset t3: t3: E 42/96.3 vs 768/104.5; t3: E 534/105.5 vs 344/104.6; t4: E 214/105.1 vs 170/104.5 |
| 111554888 | 12 | CEIL | WIN | 494 | 34/75 | 19.3 | 0:21.17 | t493 | onset t3: t3: E 51/97.1 vs 724/104.2; t3: E 437/105.0 vs 354/104.5; t4: E 214/105.1 vs 170/104.5 |
| 111554888 | 12 | CEIL_MAXB | WIN | 12 | 40/75 | 0.3 | 0:02.00 | t0 (<20!) | onset t3: t3: E 125/110.5 vs 651/109.9; t3: E 226/110.6 vs 533/110.4; t3: E 693/111.3 vs 725/110.9 |
| 111560448 | 8 | BASE | WIN | 497 | 22/75 | 18.0 | 0:19.00 | — | onset t3: t3: E 68/96.6 vs 347/100.5; t3: E 305/100.6 vs 361/100.8; t3: E 412/101.4 vs 403/101.2 |
| 111560448 | 8 | STALL | WIN | 497 | 22/75 | 16.0 | 0:16.93 | none | onset t3: t3: E 68/96.6 vs 347/100.5; t3: E 305/100.6 vs 361/100.8; t3: E 412/101.4 vs 403/101.2 |
| 111560448 | 8 | MAXB | WIN | 8 | 43/75 | 1.7 | 0:08.73 | t0 (<20!) | onset t3: t3: E 126/104.4 vs 291/104.7; t3: E 307/104.3 vs 951/105.2; t4: E 43/102.4 vs 210/103.8 |
| 111560448 | 8 | BOTH | WIN | 8 | 43/75 | 1.5 | 0:06.48 | t0 (<20!) | onset t3: t3: E 126/104.4 vs 291/104.7; t3: E 307/104.3 vs 951/105.2; t4: E 43/102.4 vs 210/103.8 |
| 111560448 | 8 | BASE_ceil | WIN | 497 | 22/75 | 15.8 | 0:16.81 | none | onset t3: t3: E 68/96.6 vs 347/100.5; t3: E 305/100.6 vs 361/100.8; t3: E 412/101.4 vs 403/101.2 |
| 111560448 | 8 | CEIL | WIN | 23 | 34/75 | 0.6 | 0:01.60 | t2 (<20!) | onset t3: t3: E 75/97.0 vs 356/100.6; t3: E 282/100.6 vs 378/100.9; t3: E 404/101.2 vs 409/101.0 |
| 111560448 | 8 | CEIL_MAXB | WIN | 11 | 43/75 | 0.3 | 0:01.28 | t0 (<20!) | onset t3: t3: E 119/104.2 vs 329/105.0; t3: E 483/104.7 vs 810/105.1; t4: E 40/102.0 vs 205/103.6 |
| 111601380 | 11 | BASE | WIN | 424 | 15/82 | 12.2 | 0:13.51 | — | onset t3: t3: E 51/94.6 vs 466/100.3; t3: E 750/101.3 vs 642/100.7; t5: E 60/96.9 vs 198/100.2 |
| 111601380 | 11 | STALL | WIN | 424 | 15/82 | 11.4 | 0:12.68 | none | onset t3: t3: E 51/94.6 vs 466/100.3; t3: E 750/101.3 vs 642/100.7; t5: E 60/96.9 vs 198/100.2 |
| 111601380 | 11 | MAXB | WIN | 14 | 28/82 | 4.2 | 0:13.05 | t0 (<20!) | onset t3: t3: E 35/94.6 vs 543/101.1; t3: E 677/101.7 vs 798/100.5; t5: E 52/97.7 vs 268/99.7 |
| 111601380 | 11 | BOTH | WIN | 14 | 28/82 | 4.2 | 0:13.98 | t0 (<20!) | onset t3: t3: E 35/94.6 vs 543/101.1; t3: E 677/101.7 vs 798/100.5; t5: E 52/97.7 vs 268/99.7 |
| 111601380 | 11 | BASE_ceil | WIN | 424 | 15/82 | 14.5 | 0:15.81 | none | onset t3: t3: E 51/94.6 vs 466/100.3; t3: E 750/101.3 vs 642/100.7; t5: E 60/96.9 vs 198/100.2 |
| 111601380 | 11 | CEIL | WIN | 424 | 15/82 | 12.6 | 0:13.86 | none | onset t3: t3: E 51/94.6 vs 466/100.3; t3: E 750/101.3 vs 642/100.7; t5: E 60/96.9 vs 198/100.2 |
| 111601380 | 11 | CEIL_MAXB | WIN | 14 | 28/82 | 0.5 | 0:01.82 | t0 (<20!) | onset t3: t3: E 35/94.6 vs 543/101.1; t3: E 677/101.7 vs 798/100.5; t5: E 52/97.7 vs 268/99.7 |
| 111557779 | 8 | BASE | WIN | 497 | 42/75 | 14.9 | 0:16.02 | — | onset t3: t3: E 225/118.7 vs 200/118.3; t4: E 351/118.3 vs 299/117.7; t5: E 246/118.2 vs 202/117.5 |
| 111557779 | 8 | STALL | WIN | 497 | 42/75 | 13.7 | 0:14.92 | none | onset t3: t3: E 225/118.7 vs 200/118.3; t4: E 351/118.3 vs 299/117.7; t5: E 246/118.2 vs 202/117.5 |
| 111557779 | 8 | MAXB | WIN | 10 | 40/75 | 2.1 | 0:09.53 | t0 (<20!) | onset t3: t3: E 80/114.7 vs 202/113.8; t3: E 132/114.8 vs 279/113.1; t3: E 410/113.9 vs 289/112.6 |
| 111557779 | 8 | BOTH | WIN | 10 | 40/75 | 2.0 | 0:09.64 | t0 (<20!) | onset t3: t3: E 80/114.7 vs 202/113.8; t3: E 132/114.8 vs 279/113.1; t3: E 410/113.9 vs 289/112.6 |
| 111557779 | 8 | BASE_ceil | WIN | 497 | 42/75 | 19.0 | 0:20.18 | none | onset t3: t3: E 225/118.7 vs 200/118.3; t4: E 351/118.3 vs 299/117.7; t5: E 246/118.2 vs 202/117.5 |
| 111557779 | 8 | CEIL | WIN | 497 | 42/75 | 18.4 | 0:19.58 | none | onset t3: t3: E 225/118.7 vs 200/118.3; t4: E 351/118.3 vs 299/117.7; t5: E 246/118.2 vs 202/117.5 |
| 111557779 | 8 | CEIL_MAXB | WIN | 10 | 40/75 | 0.3 | 0:01.34 | t0 (<20!) | onset t3: t3: E 80/114.7 vs 202/113.8; t3: E 132/114.8 vs 279/113.1; t3: E 410/113.9 vs 289/112.6 |
| 111565805 | 47 | BASE | LOSS | 501 | 56/89 | 10.3 | 0:20.38 | — | onset t3: t3: E 143/132.2 vs 331/134.1; t3: E 656/133.2 vs 524/132.8; t4: E 128/132.8 vs 142/132.9 |
| 111565805 | 47 | STALL | WIN | 500 | 54/89 | 10.1 | 0:21.43 | t499 | onset t3: t3: E 143/132.2 vs 331/134.1; t3: E 656/133.2 vs 524/132.8; t4: E 128/132.8 vs 142/132.9 |
| 111565805 | 47 | MAXB | WIN | 8 | 61/89 | 2.6 | 1:29.89 | t0 (<20!) | onset t3: t3: E 88/133.2 vs 224/132.9; t3: E 142/133.2 vs 316/132.9; t3: E 236/133.5 vs 426/133.4 |
| 111565805 | 47 | BOTH | WIN | 8 | 61/89 | 2.7 | 1:29.03 | t0 (<20!) | onset t3: t3: E 88/133.2 vs 224/132.9; t3: E 142/133.2 vs 316/132.9; t3: E 236/133.5 vs 426/133.4 |
| 111565805 | 47 | BASE_ceil | LOSS | 501 | 56/89 | 12.0 | 0:22.71 | none | onset t3: t3: E 143/132.2 vs 331/134.1; t3: E 656/133.2 vs 524/132.8; t4: E 128/132.8 vs 142/132.9 |
| 111565805 | 47 | CEIL | WIN | 19 | 61/89 | 0.3 | 0:11.02 | t0 (<20!) | onset t3: t3: E 135/132.8 vs 312/134.8; t3: E 719/134.0 vs 459/133.0; t4: E 127/134.3 vs 136/134.2 |
| 111565805 | 47 | CEIL_MAXB | WIN | 8 | 61/89 | 0.3 | 0:09.73 | t0 (<20!) | onset t3: t3: E 88/133.2 vs 224/132.9; t3: E 142/133.2 vs 316/132.9; t3: E 236/133.5 vs 426/133.4 |

- 111558435: BASE@ba996dee vs original replay floor-8 decision lines: identical over 574 lines (orig 574, base 574)
- 111558435: BASE_mb vs BASE floor-8 decision lines: identical (574 vs 574)
- 111558435: BASE_ceil vs BASE floor-8 decision lines: identical (574 vs 574)
- 111619871: BASE@ba996dee vs original replay floor-36 decision lines: identical over 529 lines (orig 529, base 529)
- 111619871: BASE_ceil vs BASE floor-36 decision lines: identical (529 vs 529)
- 111680130: BASE@ba996dee vs original replay floor-44 decision lines: identical over 655 lines (orig 655, base 655)
- 111680130: BASE_ceil vs BASE floor-44 decision lines: identical (655 vs 655)
- 111595870: BASE@ba996dee vs original replay floor-37 decision lines: identical over 527 lines (orig 527, base 527)
- 111595870: BASE_mb vs BASE floor-37 decision lines: identical (527 vs 527)
- 111595870: BASE_ceil vs BASE floor-37 decision lines: identical (527 vs 527)
- 111610012: BASE@ba996dee vs original replay floor-12 decision lines: identical over 527 lines (orig 527, base 527)
- 111610012: BASE_ceil vs BASE floor-12 decision lines: identical (527 vs 527)
- 111583124: BASE@ba996dee vs original replay floor-6 decision lines: identical over 563 lines (orig 563, base 563)
- 111583124: BASE_ceil vs BASE floor-6 decision lines: identical (563 vs 563)
- 111570033: BASE@ba996dee vs original replay floor-10 decision lines: identical over 505 lines (orig 505, base 505)
- 111570033: BASE_ceil vs BASE floor-10 decision lines: identical (505 vs 505)
- 111604302: BASE@ba996dee vs original replay floor-8 decision lines: identical over 528 lines (orig 528, base 528)
- 111604302: BASE_ceil vs BASE floor-8 decision lines: identical (528 vs 528)
- 111593733: BASE@ba996dee vs original replay floor-12 decision lines: identical over 649 lines (orig 649, base 649)
- 111593733: BASE_ceil vs BASE floor-12 decision lines: identical (649 vs 649)
- 111572948: BASE@ba996dee vs original replay floor-7 decision lines: identical over 542 lines (orig 542, base 542)
- 111572948: BASE_ceil vs BASE floor-7 decision lines: identical (542 vs 542)
- 111568362: BASE@ba996dee vs original replay floor-12 decision lines: identical over 534 lines (orig 534, base 534)
- 111568362: BASE_ceil vs BASE floor-12 decision lines: identical (534 vs 534)
- 111554888: BASE@ba996dee vs original replay floor-12 decision lines: identical over 514 lines (orig 514, base 514)
- 111554888: BASE_ceil vs BASE floor-12 decision lines: identical (514 vs 514)
- 111560448: BASE@ba996dee vs original replay floor-8 decision lines: identical over 534 lines (orig 534, base 534)
- 111560448: BASE_ceil vs BASE floor-8 decision lines: identical (534 vs 534)
- 111601380: BASE@ba996dee vs original replay floor-11 decision lines: identical over 467 lines (orig 467, base 467)
- 111601380: BASE_ceil vs BASE floor-11 decision lines: identical (467 vs 467)
- 111557779: BASE@ba996dee vs original replay floor-8 decision lines: identical over 515 lines (orig 515, base 515)
- 111557779: BASE_ceil vs BASE floor-8 decision lines: identical (515 vs 515)
- 111565805: BASE@ba996dee vs original replay floor-47 decision lines: identical over 534 lines (orig 534, base 534)
- 111565805: BASE_ceil vs BASE floor-47 decision lines: identical (534 vs 534)
