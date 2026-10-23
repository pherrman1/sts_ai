# Result: A20 self-play data with Silver's own end scores (2026-10-22)

## Verdict

The pre-registered first-fight test **failed**: the head alone made Silver much worse, and the 50/50 head-playout
blend passed both pooled bars but missed the encounter cap in Two Louse with max backup. The campaign's combat was
weaker than production Silver (below), so its labels describe a weaker player; the rerun with production combat is
`../silver_leaf_a20_prod_20261022`.

## Campaign

RUN_COMMIT 2f910dba, binary sha256 13055711... (code a8fd1fd5). `verify_campaign.py --extract`: 192 of 192 units OK,
none missing or bad, no duplicates, every unit rc=0; all 8 workers verified. Wall 20:01-21:43Z (42.7 lane-hours).

Outcomes of the 1,024 natural runs: Heart killed in 188 (18.4%, 95% CI 16.1-20.8), act 4 reached in 30.6%, act 3 in
56.0%, act 2 in 84.2%; 60.1% of Heart fights won. Perturbed runs' real path: act 4 reached in 27.5%. Production
references (other seeds): student_sel 23.4% Heart and 41.5% act 4 (§569), gen-2 A/B arms 21.5% and 20.9% (§621).
Cause: silverazgen installs its self-play search overrides for the whole run (root prior bonus off; under the
override NativeSilverBackend skips the boss prior playouts); commit 1e34ad14 makes that optional.

## Pack and head (README steps 2, 3, 5)

`pack_a20.py`: 736,347 roots (76 roots dropped by the extractor for an edge mismatch, none for a missing score),
30,426 refchg roots left out. `train_head_a20.py`: fit 419,724, stop 143,451, test (fold 4) 142,746 roots, 17 epochs.
Head `a20` (sha256 049d08a2...; `results/a20_head.txt`, also on the share as
`exact-combat-research/leaf-value/heads/a20.txt`). Fold 4, Silver points (score = 100 z):

| group | roots | actual | head RMSE | head bias | root value RMSE | root value bias | constant RMSE |
|---|---|---|---|---|---|---|---|
| all | 142,746 | 120.1 | 25.0 | −0.8 | 24.6 | −13.5 | 36.4 |
| act 1 | 43,091 | 111.8 | 17.0 | +0.0 | 16.1 | −8.3 | 25.8 |
| act 2 | 41,979 | 116.0 | 22.4 | −0.6 | 23.3 | −13.6 | 33.7 |
| act 3 | 49,729 | 130.7 | 28.3 | −0.2 | 25.9 | −15.5 | 42.6 |
| act 4 | 7,947 | 120.0 | 44.8 | −9.3 | 49.1 | −28.8 | 53.7 |
| hallway | 59,060 | 125.5 | 17.4 | +1.0 | 12.8 | −7.9 | 30.3 |
| elite | 42,488 | 114.9 | 22.4 | +1.1 | 22.5 | −13.5 | 36.1 |
| boss | 37,576 | 117.2 | 35.9 | −5.7 | 38.1 | −22.8 | 45.1 |
| turn 0 | 34,554 | 120.0 | 24.1 | −0.2 | 31.6 | −21.2 | 35.1 |

"Root value" is Silver's own Q of the most visited edge after the 10,000-simulation search; it runs 8-32 points
below the score the fight actually ends with (largest at bosses and on turn 0). The head is unbiased outside act 4
and bosses; in hallway fights the searched root value is the sharper estimate. Full table: `results/a20_report.json`.

## First-fight test (README step 4)

Exact regret per fight on the held-out replays 111149650-699 (150 fights), paired against the playout (none):

| config | none | head:a20 | hblend:a20:0.5 | head:ct | hblend:ct:0.5 | exact |
|---|---|---|---|---|---|---|
| prod | 0.872 | +6.337 ± 2.286 | −0.438 ± 0.082 | −0.195 ± 0.092 | −0.094 ± 0.058 | −0.291 ± 0.084 |
| prod@mb=4 | 0.497 | +24.367 ± 7.879 | −0.254 ± 0.066 | +0.760 ± 1.014 | −0.042 ± 0.048 | −0.365 ± 0.061 |

Blend by encounter with max backup: Cultist +0.017 ± 0.030, Jaw Worm −0.894 ± 0.149, Two Louse +0.114 ± 0.060.
Neither mode meets the pre-registered rule (at most −0.10 with max backup, below 0 without, no encounter above +0.10
in either config): the head misses every bar, the blend the encounter cap. Files: `results/oracle_a20.json`,
`results/oracle_analysis.txt`.

The head alone stalls: with one louse left it blocks and ends turns. The solver's value has an absolute turn cap (8)
and scores a fight still running past it like a loss, so the regret counts such a stall as a loss even when it costs
no HP. The follow-up `../leaf_head_turn_penalty_20261022` (Philipp 21:58Z) prices each turn beyond the root and adds
the played fights' own outcome, which has no cap, as a readout.
