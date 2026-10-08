# Read-only main-movement assessment

**No material impact identified for the frozen non-CTM campaign. The branch has three documentation merge conflicts with new main.** No rebase, merge, index/source modification, repeated build/test or final-outcome read was performed.

Main advanced from campaign base `a4b3df35d170abba7860e8e854cc24cfd3579075` to `dd308d3d89e6dde49b80468f66c6b0fe8e714136` through PR #440 (CTM escape capability). The common ancestor with campaign implementation `5add2413281c95a29e32846531d41353c804fd3c` remains the original base. The [machine receipt](MAIN_MOVEMENT_REVIEW.json), SHA256 `e74dca4b16a1b4f6e9364b8d23af0d1172d17264118933fec05d4fb6fb1c8885`, binds the exact upstream diff, paths and virtual merge output.

The change affects optional CTM model capabilities, CTM escape/HP/potion sampling, its forecast and support contracts, related Python tools/tests, and the explicit `ctmescapefeatures` command. Production CTM capability metadata remains empty. The campaign's declared clean environment has `STS_OOC_MCTS=0`, `STS_SILVER_ADAPTIVE=0`, and no `STS_SIM_ADAPT` or CTM override. `configureLiveOocMcts` returns before loading a CTM when disabled; the separate CTM adaptive-budget constructor requires its explicit adaptive controls. The adapter's actual noncombat-future sampling function, native OOC floor/win scorer and Silver search were not changed by #440.

The frozen final producer remains `d35b42b1`, binary SHA256 `1dcc79169e60cc58865218cd66644dd2db61a9e9ceaafdf39c1b8a7b6600a8f5`. Fetching main cannot alter that executable. The absence of an identified active-path change is a source-scope inference for the declared configuration, not a parity or build result for a future merged source.

A read-only `git merge-tree a4b3df35 5add2413 dd308d3d` reports no textual source/CMake conflicts. It does report conflicts in the initial **Last verified** paragraph of:

- `docs/knowledge-base/architecture/out-of-combat.md`
- `docs/knowledge-base/operations/environment-variables.md`
- `docs/knowledge-base/operations/ooc-label-pipeline.md`

The remaining additions merge textually in that virtual view, including the overlapping CMake, main-command and driver-header edits. The raw virtual display retained locally at `/home/philippherrmann/.codex/worktrees/ironclad-overnight-20261008/sts_lightspeed/build/overnight_20261008/audit/raw_build_logs/main_movement_virtual_merge.log` is SHA256 `ac3d4ae0497e4d57fd12355c23c968d78a11c97ba850e2eaf8c93bb849ea5359`. Legacy three-tree `merge-tree` returns exit0 even with conflict markers; this is explicitly **not** a clean-merge verdict.

For the draft handoff, disclose that evidence was produced on the original frozen campaign sources, not latest main. Eventual integration must reconcile both sets of verification metadata and then receive appropriate merged-source checks/CI; no historical result should be relabelled as measured on that integration. This virtual check covers committed `5add2413`, not the coordinator's still-uncommitted documentation/evidence packaging. It does not require disturbing the current frozen confirmation run.
