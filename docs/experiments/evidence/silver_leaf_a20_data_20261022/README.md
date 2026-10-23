# A20 self-play data with Silver's own end scores (leaf value step 1b, 2026-10-22)

Thread "Exact combat solving research" (leaf evaluation for Silver). Philipp 2026-10-22 17:08Z: "you can use up to 8
workers, and / or gpu for training later". Seeds from the coordinator (18:53Z): natural 111310000-111314095,
perturbed 111320000-111324095, smoke 111329990-111329997; this campaign uses natural 111310000-111311023 and
perturbed 111320000-111320511 (the rest of both blocks is released). Smokes used all of 111329990-111329997.

## Why

On the exact first fights a value head on the frozen g7f_E trunk, trained on exact values of first-fight states,
cuts Silver's exact regret on held-out fights from 0.49 to 0.25 per fight with max backup (perfect leaf 0.13), while
g7f_E's own value head and a probe trained on the g7f pack make Silver worse: the pack holds no A20 state before
act 4, and its label won x (53 + HP) prices a loss at 0 where Silver's tree scores a lost fight at about 20-35. The
missing piece is A20 data from every act with a label on the tree's own scale.

## What

`one_combat silverazgen` (the Silver AZ MLP loop's self-play generator), A20, flat 10,000 simulations, g7f_E as
tree prior (K = 8, root bonus off) and rollout root table, production A20 settings otherwise (`record_env.sh`:
the endgame study's settings without the learned stop, which silverazgen refuses), student_sel argmax out of
combat. Natural runs record every fight of the run; perturbed runs record a detached copy of each fight with a
small random change (HP, cards, upgrades, a potion) while the run continues through the real fight. Every searched
root is one row (state, edges with visits and Q). Every fight row now also carries `score`:
`SilverSearcher::evaluateEndState` of the fight's end, referenced to the fight's first searched root (commit
09d5fd16). On two A20 smoke seeds all root and fight rows equal the base binary's (165b5060, sha256 eb314334...)
except for the new key, at the same speed.

Out of combat: the first freeze (RUN_COMMIT 257bfbd2) failed its pre-launch review because silverazgen plays its
own out-of-combat rules and never consults STS_OOC_HEART1 (reviewer D: rows byte-identical with and without
student_sel; runs died in acts 1-2). Commit a8fd1fd5 moves runFullRunOOC's non-battle dispatch into
`realOocChainStep` and adds `STS_AZGEN_PRODUCTION_OOC=1` (default off), which makes the generator play every
non-battle screen through it, as bestbench does with live OOC MCTS off; `record_env.sh` sets it and `run_unit.sh`
marks a unit rc=97 unless its manifest says `"oocPlay": "production_chain"`. Checks: bestbench A20 (heart1, OOC
MCTS off, 1,000 sims, seeds 111329990-991) gives identical results and byte-identical decision traces with the old
and the new binary (238 heart1 steps, 3 key steps, 41 battles); silverazgen without the flag writes rows
byte-identical to the frozen 7916b9eb binary (seed 111329994). With the flag, A20, these settings:

| seed | student_sel | fights | roots | end | wall (4 runs at once) |
|---|---|---|---|---|---|
| 111329995 | no | 8 | 120 | floor 16, The Guardian | 13 s |
| 111329995 | yes | 28 | 1,045 | floor 51, Awakened One | 192 s |
| 111329996 | yes | 27 | 734 | floor 51, Awakened One | 140 s |
| 111329997 | yes | 28 | 542 | floor 51, Awakened One | 75 s |
| 111329994 | yes | 14 | 285 | floor 22, Masked Bandits | 39 s |
| 111329995 perturbed | yes | 28 copies | 984 | floor 51, Awakened One | 371 s (alone for the last 3 min) |

192 units of 8 runs on 8 workers x 4 lanes, queue schedule: 64 perturbed units first, then 128 natural ones.
Expected (inference from the smokes and the A20 production floor distribution, mean floor 43 and Act 4 in 40% of
runs in the gen-2 A/B): about 750 roots and 130 s per natural run and twice the time per perturbed run, so
1.1-1.2M roots, about 75 core-h, about 2.5 h on 8 workers, about 300 MB of tars.

## Analysis (pre-registered)

1. Verify and unpack: `python3 tools/cloud/verify_campaign.py docs/experiments/evidence/silver_leaf_a20_data_20261022
   --extract $HOME/silver-leaf-a20-units`. Units with rc != 0 are rerun locally from their seeds (deterministic).
2. Pack: state block (1,766 features, the prior's extractor at the code commit), label z = score / 100, plus won,
   end HP, turns, act, room, turn, fold = seed mod 5, and refchg: the root's gold or max HP differs from its fight's
   first searched root (Looter or Mugger steals, Feed), where the label's gold and max-HP terms no longer match the
   tree's reference at that root. refchg roots are left out of fitting and testing and counted.
3. Head on the frozen g7f_E trunk (128 -> 64 -> 1, as the probe and the capacity test), MSE on z; folds 0-2 fit,
   3 stops, 4 tests. Report fold-4 RMSE and bias by act, room, turn and turn-start vs mid-turn root.
4. Exact first fights: the head as Silver's leaf in `exact_combat_solver --leaf-oracles` on the held-out replays
   111149650-699 (Cultist, Two Louse, Jaw Worm), configs prod and prod@mb=4, modes none, exact, head, 50/50 blend,
   next to the capacity-test head. Pass: pooled paired change in exact regret against the playout at most -0.10 per
   fight with max backup and below 0 without, and no encounter worse than +0.10 in either. Pass leads to a native
   default-off leaf flag and fight-level A/Bs (Philipp's go); fail leads to other labels (n-step, CRN) first.
5. Descriptive: on fold 4, head value, Silver's root value and the actual score by act, room and turn (the act-4
   gap table of the leaf doc for every act).

Scripts (committed before the data arrived): `pack_a20.py` (step 2), `train_head_a20.py` (steps 3 and 5),
`run_oracle_a20.sh` and `analyze_oracle.py` (step 4; the playout, exact and capacity-test rows it pairs with are the
leaf-value oracle runs of 2026-10-22 on the same solver binary, exact_combat_solver_ct sha256 26806283...).

Later and separate: prior and value trained together on this data plus the g7f pack (gen 8, GPU).
