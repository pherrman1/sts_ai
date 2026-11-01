# Map-root prior-share stop (`STS_OOC_MCTS_PRIOR_SHARE_STOP`): implementation smoke

Research option, default off. A full-budget map root (every A20 map root under ADR-0061/ADR-0065, 1,024 sims)
checks after 128, 256 and 512 completed simulations and stops once the most-visited action is the prior argmax
(ties: lowest id) and holds at least `H` of the root visits. This is rule `S_prior` of
`docs/experiments/evidence/map_root_maxq_count_20261101/budget_stop.py` (branch `claude/project-thread-3cpa8j`,
`5d1f743a5`): on §727 arm A (23,826 map roots) `H=0.9` uses 0.38x the sims of 1,024 and differs from the 1,024
pick at 0.21% of roots; `H=0.95` 0.44x, 0.14%. No gameplay experiment was run; this is an implementation check only.

## Smoke (one used seed, 111312000, §741 arm B unit `111312000_div`)

`run_smoke.sh BIN TAG SEED [EXTRA...]` = §741 `run_unit.sh` environment without `STS_OOC_MCTS_FULL_ROOT_SIMS`
(1,024 is the default now). Four games, cloud container, 4 in parallel:

| tag | binary | flag | wall s |
|---|---|---|---|
| OFFmain | main `53d591b` (`c1753729…`) | unset | 884 |
| OFFbr | this branch (`f011db40…`, built from the working tree identical to the PR code) | unset | 880 |
| ON90 | this branch | `0.9` | 642 |
| ON95 | this branch | `0.95` | 710 |

- **Off path identical:** OFFmain and OFFbr records are equal row for row except the record's own CTM-file path
  in the header row; the CTM row files are byte-identical (sha256 `c8fee3c7…`); logs identical. OFFbr also plays
  every decision of the §741 B record of this seed (206/206 keys; roots equal except the explicit `fullRootSims`).
- **Native = offline rule:** `compare.py` applies `S_prior` to the 23 full 1,024-sim map roots of OFFbr and checks
  the ON record root by root (`smoke_111312000.jsonl`): 0 mismatches for both H. H=0.9 stops 16/23 roots, map sims
  0.41x; H=0.95 stops 12/23, 0.54x. Neither game diverges (all 206 decisions equal, same outcome: Act 4, floor 56).
- Bad values (`0.4`, `abc`, `0.9x`) fail at startup.

Wall times are from concurrent games in one container, indicative only.
