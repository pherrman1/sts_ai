# Pre-launch smokes (#854), seed 111375990, code 94e98ac + analysis fix

Binary (linux-gcc-release-x86-64-v3) sha256 `6c7747a9…` for this branch; main `61a536fe` builds to `c31fe2b0…`
(the #853 campaign binary, reproducible). Inputs: student_sel.bin `cf6bf7fb…`.

| check | result |
|---|---|
| D on this branch vs D on main 61a536fe (same env, same seed) | game record identical after the header (sha256 of rows 2.. `43d37021…` both), CTM rows 32 both; Act 4, floor 56, Heart killed |
| `STS_OOC_MCTS_SCREENS=bogus` | refused at startup (rc 1, "must be all, none or a comma list of …") |
| `STS_OOC_MCTS_SCREENS=map,shop` | accepted, banner `screens=map,shop` |
| MAP arm | rc 0, all banner checks pass; 49 searched roots, all on map screens; every other screen `heart1_screen` or a rule |
| OFF arm | rc 0; 0 searched roots, no `by=mcts` decision |
| deciders identical across arms for rule screens | tree_rule 48, relic_rule 7, chest_rule 3, heart_key 4 in MAP and OFF (D: 52 / 11 / 3 / 4 because D's earlier divergence at an act-1 event changes the run) |
| analyze.py on the three games | runs; MAP and OFF games identical (no map override left the prior on this seed); D first diverges at an act-1 event |
| wall | D 689 s, MAP 647 s, OFF 216 s |
