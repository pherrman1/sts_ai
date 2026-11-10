# Gumbel stop trace: smoke and plan (2026-11-10)

Step 1 of the learned stop for the Gumbel root (G16 + max backup 4, ledger §775). Research only: a trace, no stop.
Authorization: Philipp 2026-11-10 00:22 CET ("Jo klingt gut, go") for the code and a smoke; data, seeds, worker
count and any gate each need his own typed go. No default changes.

## What the trace writes

`STS_SILVER_GUMBEL_STOP_TRACE=<csv>` (docs/knowledge-base/operations/environment-variables.md) writes one row per
sequential-halving boundary of every whole-run Gumbel root (`STS_SILVER_GUMBEL_ROOT`):

- boundary 0 is before the first phase (spent 0, candidates ranked by g + logit: what a zero-simulation stop returns);
- boundary p is after phase p's scoring, before the halving. The leader is the candidate the search ranks first
  (score g + logit + sigma(completed q)), i.e. the edge `searchGumbelRoot` would return if it stopped there;
- the last boundary's leader is the final pick (`leader_is_final` = the label; checked in the unit test).

The hook is `SilverSearcher::gumbelBoundaryObserver`. It only reads the tree (selection values, visit counts, the
root prior); it draws no random numbers and takes no steps.

## Where a stop may act

Only at phase boundaries. Sequential halving fixes each phase's per-candidate budget from the total budget in
advance, so a stop inside a phase would compare candidates with unequal visits and would no longer be the
search Danihelka et al. (2022) analyse; at a boundary all remaining candidates have equal visits and the
ranking is the one the search itself uses. With k = 16 and n legal actions the root has ceil(log2(min(n, 16)))
phases, so the possible stops are after 1/P, 2/P, ... of the budget (P = 4: 25 %, 50 %, 75 %).

Max backup (M = 4) enters through `selectionValue`: a candidate's q is its max-backup value once it has at least
4 visits, which every candidate has after phase 1 at 16k. The trace's `leader_q` / `score_gap` are these values,
so the stop sees what the halving sees.

Not traced (Inference, not tested): choosing a smaller budget before the search starts. That runs a different
halving schedule, and only a separate run can show whether it picks the same action.

## Smoke: replays of §775 games (binary of this commit, sha256 112c0f3a...)

`replay.sh ARM SEED off|on` reruns one §775 game with its own `.env` from the share tars
(`/mnt/project-files/gumbel-wholerun/units`), net-0420 (sha 8c0bd16c), through `tools/seed_guard.sh`, and adds the
trace for `on`. `compare.py` compares final floor, hp_end, win, `[heart1_ppo] decisions/single/fallbacks` and
`[silver] whole-run Gumbel roots=N sims=S` with the original logs.

Result (`results/compare_and_boundaries.txt`): 18/18 games identical. That is 8 G16 games with the trace off
(this binary reproduces §775's binary 0eabb014), the same 8 with the trace on, and 2 D games. The 8 G16 games
include two Heart kills (111378315, 111378346) and one Heart loss (111378325). In every traced game the summed
`root_sims` over traced roots equals the `sims=` total, so every root that searched is in the trace; the roots
missing from the trace are one-action roots, which `searchGumbelRoot` plays without searching.

Per boundary over 3,965 traced roots (descriptive, 8 games, not a stop policy):

| phases | boundary | roots | leader = final | CPU share before boundary | sim share |
|---|---|---|---|---|---|
| 1 | 0 | 449 | 0.737 | 0 | 0 |
| 2 | 0 / 1 | 1,071 | 0.561 / 0.846 | 0 / 0.499 | 0 / 0.500 |
| 3 | 0 / 1 / 2 | 1,676 | 0.346 / 0.703 / 0.745 | 0 / 0.331 / 0.664 | 0 / 0.333 / 0.666 |
| 4 | 0 / 1 / 2 / 3 | 769 | 0.202 / 0.525 / 0.614 / 0.706 | 0 / 0.249 / 0.499 / 0.749 | 0 / 0.25 / 0.5 / 0.75 |

CPU tracks simulations almost exactly inside a root (thread CPU, measured while other jobs shared the 4 cores).
Of root CPU, 4-phase roots take 25 %, 3-phase 41 %, 2-phase 24 %, 1-phase 10 %. Raw agreement is not
the stop's accuracy. A learned stop only has to find the subset of roots where an early leader is safe.

## Plan for steps 2 and 3 (each needs Philipp's typed go)

Step 2, data. G16 + mb4 + trace in whole runs on fresh seeds (not the §775 block 111378256-111379279, which the
gate reuses), same env as §775 G16 plus `STS_SILVER_GUMBEL_STOP_TRACE`. §775 G16 averaged 0.145 h of one lane per
run (120 sampled games), so 1,024 runs are about 150 lane-h, about 1 h on 40 workers at 4 lanes each. The trace
is about 1 MB of CSV per run (2.2 MB xz for these 8), so about 0.3 GB xz for 1,024 runs, one tar per unit. Training: adapt
`tools/silver_learned_stop.py` to these columns (rows grouped by root; candidate stops are boundaries 0..P-1;
label `leader_is_final`), cross-validated by run. Offline report: agreement with the full-budget pick against
CPU fraction, as for ADR-0026 and ADR-0051.

Step 3, gate. G16STOP vs G16 in whole runs on the §775 seeds, with §775's G16 games as the reused control (the
replays are deterministic: 16/16 here, 32/32 in the tuning thread). SPRT per ADR-0064, with Heart kills as the
outcome and the CPU ratio reported. The treatment costs at most the G16 arm, about 150 lane-h for 1,024 seeds,
and less with the stop.
