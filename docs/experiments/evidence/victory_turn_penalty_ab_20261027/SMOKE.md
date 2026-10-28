# Pre-launch smokes, seeds 111386990–111386991, code 67d2dc1 (branch on main ed2dcb2)

Binary (linux-gcc-release-x86-64-v3) sha256 `21bc7308…`, built from `67d2dc1` (the flag and trace commit; later
commits on this branch change only this directory). student_sel.bin `cf6bf7fb…`. `run_all.sh` with 2 lanes on this
thread's 4-CPU cloud container, 2026-10-27 19:39–20:14Z.

| check | result |
|---|---|
| all 4 games rc 0 (every banner check in `run_unit.sh` at the time passes) | yes |
| B banner `[silver] research leaf: gold=0.25 maxhp=2 victoryTurnPenalty=0 concave=0 potionWeights=off`; A has none | yes |
| both arms `screens=none`, student_sel loaded, flexible key rules, CTM Act-4 model, OOC learned-stop file (rc 97 check added after the smoke; the banner is in all four logs) | yes |
| trace battle rows carry `turns`, `outcome`, `room`, `escaped` | yes (10 + 35 combats per arm) |
| **the flag reaches the search**: identical trace rows until a combat with the same pre-state plays differently | 990: first 6 combats identical, diverges at floor 10 Gremlin Nob (both won in 4 turns, HP A 9 / B 7); 991: diverges at floor 8 Three Sentries (both 7 turns, HP A 54 / B 66) |
| `analyze.py` on the 2 seeds | runs; 2 valid pairs, both first divergences are paired combats |
| outcomes | 990: both died at the Act-1 boss (floor 16); 991: both killed the Heart (floor 56) |
| turns per combat (n = 45 per arm) | A mean 3.58 (normal 2.87, elite 3.69, boss 6.17), max 10; B mean 3.89 (2.96, 4.23, 7.0), max 13; no combat ≥ 30 turns, no turn cap, no escape |
| wall per game (s) | A 36, 1,201; B 40, 924 |

Seed 991's last step (gzip) did not run because `run_unit.sh` was edited (rc 97 line) while that unit was still
executing; bash then misread the file (`syntax error near unexpected token done`). The outputs were complete; they
were gzipped by hand. `bash -n` passes on the committed scripts. Do not edit scripts under a running campaign.

Cost estimate: a Heart run ~1,000–1,200 s per arm, an early death ~40 s; ~300–450 s mean per game as in the key-rules
smoke → 64 games ≈ 6–8 core-hours ≈ 2–3 h on 4 lanes plus a Heart-run tail.
