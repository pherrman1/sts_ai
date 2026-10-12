# Lizard Tail support in the default OOC MCTS CTM stack (ledger §435)

Code `c5d0d2c4` (this branch), `one_combat` sha256 `1ffa4dd3…`, built in a cloud container (Release).
Seeds 74011000–74011007 (8 runs per arm, same seeds), A0, `bestbench` through `tools/seed_guard.sh`,
[run.sh](run.sh): the §422 rollout3 environment with `STS_OOC_MCTS_SIMS=256` (a support census, not a
win-rate test).

- `old`: the #418 stack the automatic default loaded before this change, selected explicitly
  (`combat_transition_deepsets_pathb_r2.native` + `near_full_escape_pathb_r2` + `ACTIVE_LIZARD=1`).
- `new`: the automatic default stack after this change (`combat_transition_deepsets_pathb_r2_lizard.native`).

All 16 runs rc=0, no seed failures; every log names its arm's combat model and `active_lizard_correction=1`.

| | old | new |
|---|---|---|
| OOC decisions | 1,007 | 1,009 |
| V4 fallback | 72 (7.1%) | 25 (2.5%) |
| support aborts | 47 | 0 |
| `active_unqualified_lizard` (Fairy Potion + unused Tail) | 41 | 0 |
| `active_lizard_entropic_brew_unsupported` (Brew + unused Tail) | 6 | 0 |
| `root_boundary` (root is already a leaf boundary; nothing to search) | 25 | 25 |
| runs with any Lizard abort | 7/8 | 0/8 |
| wins (descriptive only) | 7/8 | 8/8 |

Per-run decision counts differ slightly after the first divergent decision. Every remaining fallback in
`new` is `root_boundary`, which is not a support failure.

Raw: `/mnt/project-files/ooc-lizard-default-435/lizard-default-435.tgz`
(sha256 `b7243293484d9b0cbba169f56bbc6b30275a5728a78b5df0e5794e83993c776d`): per run the bestbench CSV,
log, MCTS trace CSV, support-reason JSONL and action trace.
