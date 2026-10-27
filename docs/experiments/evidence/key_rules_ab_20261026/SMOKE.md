# Pre-launch smokes, seeds 111383024–111383027, code db216ff0 (main)

Binary (linux-gcc-release-x86-64-v3) sha256 `d74cfded…`, built from main `db216ff0`; student_sel.bin `cf6bf7fb…`.
`run_unit.sh` as committed, 4 units on one 4-CPU container (4 lanes busy).

| check | result |
|---|---|
| all 8 games rc 0 (every banner check in `run_unit.sh` passes) | yes |
| F banner `heart_key_rules sapphire=2 ruby=2 ruby_min_hp=0.600 emerald=1`; R has no such line | yes |
| both arms `screens=none`, student_sel loaded, CTM Act-4 model, learned OOC stop file | yes |
| no `by=mcts` decision in either arm | yes (deciders: heart1_screen, tree/relic/chest rules, heart_key, match_and_keep) |
| analyze.py on the 4 seeds | runs; 4 valid; 1 identical pair (seed 027: both arms took the Sapphire in Act 1, so the games match; died floor 25), 3 diverge at an Act-1 REWARDS screen with a Sapphire offer (R: `heart_key`) |
| key timing (descriptive, n=4) | R: Sapphire in Act 1 at floor 9 in 4/4; F: Act 1 in 1/4, Act 2 in 3/4; relics at Act-2 start R 6.0 vs F 7.25 |
| outcomes | Heart kills R 1 / F 1; Act 4 R 2 / F 3 |
| wall per game (s) | R 215, 53, 1337, 11; F 234, 399, 1541, 13 (the Heart run 1,337–1,541 s under Act 4 strong) |

Cost estimate from the smoke and §683 (OFF 87 s per game without Act 4 strong): ~300–450 s per game, 2,048 games
≈ 170–260 core-hours, ≈ 3–4 h on 16 workers × 4 lanes plus a Heart-run tail (≤ ~30 min per game).
