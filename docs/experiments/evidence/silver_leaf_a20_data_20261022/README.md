# A20 self-play data with Silver's own end scores (leaf value step 1b, 2026-10-22)

Thread "Exact combat solving research" (leaf evaluation for Silver). Philipp 2026-10-22 17:08Z: "you can use up to 8
workers, and / or gpu for training later". Seeds from the coordinator (18:53Z): natural 111310000-111314095,
perturbed 111320000-111324095, smoke 111329990-111329997; this campaign uses natural 111310000-111311535 and
perturbed 111320000-111321535 (the rest of both blocks stays unused). Smokes used 111329990-111329993.

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
`SilverSearcher::evaluateEndState` of the fight's end, referenced to the fight's first searched root (code commit
09d5fd16). On two A20 smoke seeds all root and fight rows equal the base binary's (165b5060, sha256 eb314334...)
except for the new key, at the same speed.

192 units of 16 runs on 8 workers x 4 lanes, queue schedule. Smokes (A20, these settings): a natural run that died
on floor 12 took 14 s for 102 roots, a perturbed one that died on floor 16 took 36 s for 125 roots; full runs are
several times longer. Expected (inference): 1-2M roots, 50-80 core-h, about 2-2.5 h, 300-500 MB of tars.

## Analysis (pre-registered)

1. Verify and unpack: `python3 tools/cloud/verify_campaign.py docs/experiments/evidence/silver_leaf_a20_data_20261022
   --extract $HOME/silver-leaf-a20-units`. Units with rc != 0 are rerun locally from their seeds (deterministic).
2. Pack: state block (1,766 features, the prior's extractor at the code commit), label z = score / 100, plus won,
   end HP, turns, act, room, turn, fold = seed mod 5.
3. Head on the frozen g7f_E trunk (128 -> 64 -> 1, as the probe and the capacity test), MSE on z; folds 0-2 fit,
   3 stops, 4 tests. Report fold-4 RMSE and bias by act, room, turn and turn-start vs mid-turn root.
4. Exact first fights: the head as Silver's leaf in `exact_combat_solver --leaf-oracles` on the held-out replays
   111149650-699 (Cultist, Two Louse, Jaw Worm), configs prod and prod@mb=4, modes none, exact, head, 50/50 blend,
   next to the capacity-test head. Pass: pooled paired change in exact regret against the playout at most -0.10 per
   fight with max backup and below 0 without, and no encounter worse than +0.10 in either. Pass leads to a native
   default-off leaf flag and fight-level A/Bs (Philipp's go); fail leads to other labels (n-step, CRN) first.
5. Descriptive: on fold 4, head value, Silver's root value and the actual score by act, room and turn (the act-4
   gap table of the leaf doc for every act).

Later and separate: prior and value trained together on this data plus the g7f pack (gen 8, GPU).
