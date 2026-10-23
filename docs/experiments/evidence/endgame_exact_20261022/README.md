# Endgame exact study (thread "Exact combat solving research", 2026-10-22)

Question (Philipp's pick, 11:08Z): are exact solves of the last one or two turns of A20 elite and boss fights
feasible, and what do they show about Silver racing vs blocking? Research only: no play-changing code, no gate.

## Roots

68 A20 runs, seeds 111149700-767 (own block of the thread), production settings without OOC MCTS (student_sel
argmax plays OOC; real combats are production Silver), recorded with `one_combat endgamerootgen` (commit 69e6ba4a,
one_combat sha256 b73033a5910e6f13669b656e5e98cacdade60d9a7be019862efb39a8b1ec8616):

```
source record_env.sh   # EG_ENV
env -i PATH=/usr/local/bin:/usr/bin:/bin HOME=$HOME "${EG_ENV[@]}" OMP_NUM_THREADS=3 \
  STS_OOC_HEART1=student_sel.bin (cf6bf7fb7c3147dcc5b106b1a946486e40bf27fee87c57bcc3262b5869d507c7) \
  bash tools/seed_guard.sh one_combat endgamerootgen N 10000 20 FIRST_SEED OUT.jsonl 2
```

Every Silver decision of the last three turns of every elite and boss fight is one row (state, Silver's edges with
visits and Q, Silver's choice). Seeds 700-703 were recorded twice (pilot recorder and this one): identical rows.
All rows: /mnt/project-files/exact-combat-research/endgame/recorded/endgame_roots_111149700-767.jsonl.gz.

`make_inputs.py` keeps complete runs, applies the solver's eligibility filter and each config's fight filter, and
shuffles with a fixed seed (68 runs, 12 won):

| input | roots | used by |
|---|---|---|
| S0 | 716 (boss 541, elite 175) | lost fights, last three turns |
| C0 | 1664 (boss 603, elite 1061) | last turn of every fight |
| S1 | 251 (boss 184, elite 67) | lost fights, second-to-last turn |
| W1 | 2498 (boss 786, elite 1712) | won fights, second-to-last turn (C1 and C2) |

## Solves

`exact_combat_solver roots` at c449ca96 (sha256 e16d59d1...; the redraw-loop fix of that commit is required: about
12% of the roots have a Discovery-style edge). Configs and limits: `run_unit.sh`. 133 units on 8 workers x 4 lanes
(`worker.sh`, queue schedule).

## Analysis

```
python3 tools/cloud/verify_campaign.py docs/experiments/evidence/endgame_exact_20261022 --extract $HOME/endgame-exact-units
python3 docs/experiments/evidence/endgame_exact_20261022/collect.py $HOME/endgame-exact-units \
  /mnt/project-files/exact-combat-research/endgame/inputs OUTDIR E
python3 docs/experiments/evidence/endgame_exact_20261022/study.py OUTDIR E RECORDED.jsonl
```

Results: the thread's report, /mnt/project-files/exact-combat-research/REPORT.md section 9.
