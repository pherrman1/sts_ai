# Combat states for the combat net (combat plan stage 0, 2026-11-08)

Stage 0 of the [combat plan](https://claude.ai/artifact/HvTqKL592wjb21Zgb3Sho4): a training set of A20 combat roots
searched by production Silver. Philipp asked for stages 0 and 1 in parallel on 2026-11-08 00:49 CET and gave the go
for up to 18 workers per stage at 00:57 CET ("du hast für beide phasen je 18 worker zur Verfügung, starte die wenn
nötig ... Frag nicht nach Erlaubnis"). Seeds from the coordinator (00:59 CET): 111860000-111863071, smokes
111869990-111869999. Data generation only: no gameplay comparison, no gate, no default change.

## What

`one_combat silverazgen` exactly as `../silver_leaf_a20_prod_20261022` (same `record_env.sh`; `run_unit.sh` differs only
in the 6 h timeout), on the current binary: A20, student_sel argmax out of combat through the production chain, flat
10,000-simulation production Silver in every fight (`STS_AZGEN_PRODUCTION_COMBAT=1`: g7f_E root prior with its bonus,
tree prior K = 8, boss prior playouts). One row per searched root (the public search state as `wire`, every root edge
with visits and Q, the played action) and one row per fight (outcome, end HP, Silver's end score). 384 units of 8
natural runs (`units.txt`), queue schedule, 4 lanes per worker.

Why flat 10k instead of today's learned stop: the rows are policy targets, and the learned stop ends many roots after
1-3k simulations; §716/§718 found no play difference between 10k and the learned stop on Baalorlord's states. The
October campaign (`../silver_leaf_a20_prod_20261022`, 1,536 runs, archived on the share) is the same data on the
2026-10-22 binary and can be pooled once its wire schema is checked against this encoder.

## Smoke (2026-11-08, binary of code 1a37c74a, two natural runs at once)

| seed | roots | fights | end | wall |
|---|---|---|---|---|
| 111869990 | 683 | 28 | floor 39, Spire Growth | 167 s |
| 111869991 | 818 | (see log) | | 303 s |
| 111869992 | 153 | | rc 0 (real manifest smoke) | 33 s |

Both ended rc 134 only because the smoke ran with `STS_EXECUTABLE_GIT_SHA=PENDING` (the manifest write refuses it);
the rows were complete. About 0.3 s per root. Expected for the campaign: 3,072 runs × ~750 roots ≈ 2.3M roots,
≈ 190 lane-hours, ≈ 2.7 h on 18 workers × 4 lanes.

## Processing (after the run)

1. `python3 tools/cloud/verify_campaign.py docs/experiments/evidence/combat_states_20261108 --extract <dir>`.
   Units whose `.done` line has rc != 0 are excluded from the pack; the pack report gives the unit tally by rc
   (0 / 124 / 97 / other / missing).
2. `python3 -I tools/combat_net/pack_states.py OUT.jsonl.gz <dir>/**/natural-*.jsonl.gz`: one training row per root
   (tokens from `tools/combat_net/wire_encoder.py`, Silver's root visit shares, the fight's real outcome, realized HP
   loss to the next one and two turns). The encoder raises on any wire field it does not list
   (`tests/test_combat_net_wire.py` checks that every listed field reaches the encoding), so the pack fails rather than
   drop a field.

Deviations from the plan's stage-0 row, recorded here: the "incoming damage" auxiliary labels are the realized HP loss
on the played line, not an exact simulator quantity; max damage / max block of the hand are not computed yet (they
need a small search per root and belong to stage 2's ablation); potions used per fight are not in the fight rows.

## Result (2026-11-08)

Run commit 75604d31 (code a51a2ed2, binary 44d6d0c9), 18 workers × 4 lanes, 01:50-05:10 CET. A container reset wave
at about 03:25 CET killed some lanes; their stale claims were re-claimed and rerun (a second wave at about 05:25 CET
came after stage 0 had finished).
`verify_campaign.py`: 384 of 384 units OK, 0 missing, 0 bad, 0 duplicates, all tars from run 75604d31, 18/18 worker
DONE.json. Unit tally by rc: 384 rc 0, nothing excluded.

Pack (`pack_states.py`, after the encoder fix below): 384 files, 3,072 runs, 70,641 fights (act 1 28,546, act 2
21,200, act 3 18,491, act 4 2,404; 68,328 won), 1,633,473 root rows, of which 1,519,158 have more than one edge; 0 rows
dropped (no wire 0, no fight row 0, invalid fight 0). Output on the share:
`/mnt/project-files/combat-plan/states-packed/combat_states_20261108.jsonl.gz` (338 MB, sha256
`21e843310f0b9a4d11e4549df1987cd13a57464b53634f469e756d7ae49c9611`).

Encoder fix found by the pack: the first pack stopped on `monsters[].pendingAttackPredicates[][]` (16,138 of 1.63M
wires; each predicate is a (step, attacking) pair, and the stage-0 fixture had none). The pairs were already encoded
by the generic flattening of the monster list; only the SPEC entry was missing. `SPEC` now lists the path, and one
fixture row with a predicate was added to `tests/data/combat_net_wire_sample.jsonl` so the perturbation test covers it.
A full scan of all 1,633,473 wires found no other unknown path.
