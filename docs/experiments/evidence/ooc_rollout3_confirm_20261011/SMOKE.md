# Smoke: one seed per arm (planning container)

2026-10-11, binary `bab14cd5…` from `f82eeadd`, this folder's `run_unit.sh`, seeds 76009000–002 (not cohort seeds).
`combo` and `rollout3` ran together (2 units on 4 CPUs); `off` ran alone afterwards.

| arm | seed | rc | won | floor | end HP | s/run | MCTS CPU s | owned / OOC decisions | support aborts | config banner |
|---|---|---|---|---|---|---|---|---|---|---|
| `combo` | 76009000 | 0 | 1 | 51 | 56 | 1,336 | 1,278 | 91 / 124 | 30 | `"simulations":4096`, `"wideningK":4,"wideningAlpha":0.75` |
| `rollout3` | 76009001 | 0 | 1 | 51 | 47 | 620 | 509 | 90 / 123 | 30 | `"simulations":2048`, `"wideningK":2,"wideningAlpha":0.5` |
| `off` | 76009002 | 0 | 1 | 51 | 80 | 66 | – | – | – | no `[ooc-mcts-config]` |

Both MCTS logs also show `"leafCombats":3`, `"leafValue":"native"`, `"prior":"policy"` and the production
`combat_model=selfplay/models/combat_transition_deepsets_pathb_r2.native`.

The first `off` attempt stopped before running with `arm env incomplete`: `run_unit.sh` (copied from §424/§427–§430,
which had no `off` arm) required more than 30 environment lines, and `off` has 25. The check is now `> 20`; the rerun
above passed.

Raw files: `/mnt/project-files/ooc-rollout3-confirm/planning-smoke-433.tar` (sha256 `992815e27350ba83e81a99e94f266c00ef9a94409f4fb749e69ac0b7eda1a641`).
