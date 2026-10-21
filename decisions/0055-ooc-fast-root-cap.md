# ADR-TBD: Fast roots of playout-cap-randomized OOC MCTS stop at 1024 simulations

Date: 2026-10-21
Status: accepted

## Context

AZ-loop runs use playout-cap randomization (`STS_OOC_MCTS_FULL_BUDGET_FRACTION=0.25`, ADR-0043 targets): a quarter of
the searched roots run the full 4096 simulations and supply the policy targets; the others stop early (learned OOC
stop or gap ladder) and only choose the move. In the 1,024 runs of the gen-1b A/B those fast roots still averaged
1,221 simulations; 3,512 of 25,516 ran to 2048 (`/mnt/project-files/az-speed-profile/REPORT.md`). KataGo gives its
fast searches a small fixed budget. Capping the fast roots at 1024 would have removed 25% of all OOC simulations there
(about 18% of run CPU).

On 2026-10-21 at 09:58Z Philipp wrote: "try a katago on 1024 cap. No gate, just fix that".

## Decision

- `STS_OOC_MCTS_FAST_ROOT_CAP`: when playout-cap randomization is on, a searched root that is not a full-budget root
  runs at most this many simulations; its early stops still apply below the cap. Full-budget roots, singleton roots and
  runs without `STS_OOC_MCTS_FULL_BUDGET_FRACTION` are unchanged.
- Unset, it is 1024 whenever `STS_OOC_MCTS_FULL_BUDGET_FRACTION` is set. `0` restores the uncapped fast roots. A
  positive value without `FULL_BUDGET_FRACTION` is fatal.
- The startup banner prints `fast_root_cap=N`; `heartoutcomegen ... policy` rows carry `root.fastRootCap`, and a capped
  root's `requestedSimulations` is the cap.

## Consequences

- Play changes on fast roots that would have searched past 1024 simulations; full-budget roots and their policy
  targets do not change. No gate was run (Philipp's decision). Runs from before this ADR (gen 0, the gen-1b A/B, the
  value-leaf A/B freeze) are reproduced with `STS_OOC_MCTS_FAST_ROOT_CAP=0`.
- The learned OOC stop still checks at 128, 256, 512 and 1024 simulations; its 2048 checkpoint is never reached on a
  capped root.
