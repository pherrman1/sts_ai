# Smoke: two r5liz seeds (planning container)

2026-10-12 11:08Z–11:23Z, binary `10dc2616…` from `3b06c924`, this folder's `run_unit.sh`, arm `r5liz`, seeds
80009000–80009001 (not cohort seeds), next to the gate rerun (3 units on 4 CPUs). Both logs print `[ooc-mcts-config]` with
`"leafCombats":5`, `"simulations":2048`, the native leaf, the policy prior, `combatModel` `…pathb_r2_lizard.native` and
`"activeLizardCorrection":true`, plus `[ctm-research-candidate] candidate_id=pathb-r2`.

| seed | rc | won | floor | end HP | s/run | MCTS CPU s | owned / OOC decisions | support aborts | Lizard support failures |
|---|---|---|---|---|---|---|---|---|---|
| 80009000 | 0 | 1 | 51 | 20 | 891 | 764 | 124 / 129 | 2 | 0 |
| 80009001 | 0 | 1 | 51 | 37 | 787 | 711 | 115 / 118 | 0 | 0 |

The 2 aborts on 80009000 are `fastSupportFailures` (not Lizard). Expected cost (**Inference**): about 850 s per run, so
128 runs ≈ 30 CPU-hours per arm and about 1 h per worker at 4 units at a time; `lizard` (3 leaf combats) somewhat less.
Raw files (smokes and the stopped gate rerun): `/mnt/project-files/ooc-rollout5-lizard-446/planning-smoke.tar` (sha256 `4df53d91a76c6ecd1b8542ca487f4c2ccd71f47721a59b733d6d075c5e5481f9`).
