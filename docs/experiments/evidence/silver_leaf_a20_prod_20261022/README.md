# A20 self-play data with production Silver in combat (leaf value step 1b rerun, 2026-10-22)

Thread "Exact combat solving research" (leaf evaluation for Silver). Philipp 2026-10-22 21:53Z: "go rerun", on the
proposal of 8 workers. Seeds from the coordinator (21:57Z): natural 111330000-111331023, perturbed
111332000-111332511, smokes 111339990-111339999 (the smoke used 111339990-111339994).

## Why

The first campaign (`../silver_leaf_a20_data_20261022`) played its fights under silverazgen's self-play search
overrides: tree prior K = 8 with the root bonus off and, because the override is set, no boss prior playouts. Its
combat was weaker than production Silver (Heart kill 18.4% of 1,024 natural runs, act 4 reached in 30.6%), and its
label is Silver's own end score of fights played that way. The head trained on it failed its first-fight test.
Commit 1e34ad14 adds `STS_AZGEN_PRODUCTION_COMBAT=1` (default off): silverazgen installs no search override and the
whole run plays production Silver (g7f_E root prior with its bonus, tree prior K = 8, boss prior playouts), and the
manifest records `"combat": "production"` and the prior-playout rooms actually used (the first campaign's manifest
said `boss`, though the override skipped them; the generator now writes `none` in that case).

Checks (silverazgen natural, production out-of-combat chain, A20, 1,000 simulations, seeds 111329990-991, against
bestbench on the same seeds and settings): with the flag all 41 fights match bestbench (encounter, won, HP and max
HP entering each fight); without it 16 of 41 match (the first difference at fight 4), and its rows are
byte-identical to those of the first campaign's binary (sha256 13055711..., code a8fd1fd5).

## What

As the first campaign except for `STS_AZGEN_PRODUCTION_COMBAT=1` (`record_env.sh`) and root bonus 1 (`run_unit.sh`,
which silverazgen requires with the flag): `one_combat silverazgen`, A20, flat 10,000 simulations, student_sel argmax
out of combat through the production chain, every searched root one row, every fight row with Silver's own end score
`score`. `run_unit.sh` marks a unit rc=97 unless its manifest says `"oocPlay": "production_chain"`,
`"combat": "production"` and `"prior_playout_rooms": "boss"`. 192 units of 8 runs on 8 workers x 4 lanes, queue
schedule: 64 perturbed units first, then 128 natural ones.

Smoke (`run_unit.sh` as on a worker, 4 lanes at once; teacher `silver-az-10000-k8-rb1-prod-c45dcc0a`, all rc=0):

| seed | variant | fights | roots | end | wall |
|---|---|---|---|---|---|
| 111339990 | natural | 7 | 160 | floor 16, The Guardian | 278 s for both runs |
| 111339991 | natural | 28 | 702 | floor 50, Awakened One | |
| 111339993 | natural | 7 | 129 | floor 16, Hexaghost | 29 s |
| 111339992 | perturbed | 15 copies | 257 | after floor 30 | 92 s |
| 111339994 | perturbed | 7 copies | 107 | after floor 8 | 21 s |

Expected: the first campaign took 42.7 lane-hours (0.16 s per root in natural units, 0.32 in perturbed ones) and
1 h 41 min on 8 workers. The smoke ran at 0.31 s per root in both variants (few runs); production combat also gets
further. Hence about 1.5 times the cost: about 65 lane-hours, 2.5-3 h on 8 workers, about 0.8-1.0M roots.

## Analysis (pre-registered)

1. Verify and unpack: `python3 tools/cloud/verify_campaign.py docs/experiments/evidence/silver_leaf_a20_prod_20261022
   --extract $HOME/silver-leaf-a20-prod-units`. Units with rc != 0 are rerun locally from their seeds.
2. Pack and head with the first campaign's scripts unchanged (`../silver_leaf_a20_data_20261022/pack_a20.py` with
   this campaign's binary, `train_head_a20.py`): the same features, label z = score / 100, folds seed mod 5, refchg
   roots left out; head `a20prod` on the frozen g7f_E trunk (128 -> 64 -> 1), fold-4 report as before.
3. Part B of `../leaf_head_turn_penalty_20261022/PREREG.md`: a20prod with the mode selected there
   (hblend:NAME:0.5/1) on the fresh first fights 111333000-099, same pass rule; head:a20prod and hblend:a20prod:0.5
   and the played fights' outcome (`outcome_tp.py`) descriptive.
4. Descriptive: outcomes by act (Heart kill, act 4 reached) next to the first campaign's, and the fold-4 head,
   root-value and actual-score table by act, room and turn.
