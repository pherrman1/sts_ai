# Exact speedup of the native heart1/student forward (ledger §TBD)

Performance only: no gameplay, model, RNG or default change. Philipp 2026-10-18 11:52Z ("definitely work on the
student forward thing and make it faster") after the A20 stack profile (thread "Profile the A20 winrate stack",
report `/mnt/project-files/a20-profile/REPORT.md`): student_sel forwards inside rollout3 leaves are about 70% of an
A20 winrate-check run, real Silver combat 2-3%.

## Setup

- Baseline: `main` at `658d43ee`, Release `one_combat` sha256 `3315a7c1…`. Candidate: the PR head's code, Release
  sha256 `04e15813…` (GCC 13.3.0, 4-CPU cloud container with AVX-512, FMA and AVX2).
- Record parity: `heart1score` (logits, value and pooled vector for every record) byte-identical between the two
  binaries, and with `STS_OOC_HEART1_SCALAR=1` on the candidate, on records captured with
  `STS_OOC_HEART1_CAPTURE` (`EVERY=1`) from A20 seed 111195256 (Act 1, the frozen winrate-check env):
  4,383 records (`bench.jsonl`, every 20th early row) and 2,395 (`bench2.jsonl`, every 250th row of 1.1 GB).
  The same first 300 rows of `bench2.jsonl` with heart1 (`1e92f2a6…`) and student C (`eff2f74f…`): identical.
  `heart1logitscheck`: 0 logits-only vs full mismatches.
- Play parity [compare.py](compare.py): one guarded `bestbench 10000 1 20 SEED` unit per binary through
  [gate.sh](gate.sh) with the A20 winrate-check env ([run_unit_prof.sh](run_unit_prof.sh) is its `run_unit.sh` at
  `9db53ea3` plus an extra-env line, here `STS_RUN_PROFILE`). Compared: result and MCTS summary rows without timing
  columns, byte-identical MCTS action and support traces and decision log, run-profile rows without timing keys, and
  log lines without timing. Seeds: 111195257 full run (dies on Act 2 floor 21), 111195258-260 Act 1
  (`STS_STOP_AFTER_ACT=1`). Units ran 3-5 at a time on 4 vCPUs, so wall time is noisy; MCTS CPU is thread CPU.

## Change (`apps/one_combat/heart1_policy.cpp`)

Each path keeps the reference arithmetic per output element; `STS_OOC_HEART1_SCALAR=1` turns all of them off.

- Attention in AVX: scores keep `dot()`'s eight partial sums and reduction order (eight keys reduced together),
  max, exp and sum stay sequential, each output dimension sums `p * v` over keys in key order.
- Projection kernel: four-output reductions (`reduce4`, the same pair/quad/final additions as `reduce8`), vector
  bias and accumulate additions, and leftover tokens tiled by four outputs instead of scalar `dot()`.
- FixedVec memo: per-thread projected rows (bias included) by weights id and input bits, for inputs with at most
  four features (map position, path xs, relative position, DAG aggregates, path x, cone, deck misc, relic counter,
  gold). A row's projection does not depend on the other rows of its call, so adding the stored row is the same
  addition. `fixed_obs` (five features) is computed as before. The memo holds up to 16,384 rows and is then cleared.
- Last block of the logits-only pass: observation rows compute only keys and values (a copy of the in-projection's
  key/value rows), as their queries are never read.
- Reused per-thread buffers instead of fresh zeroed vectors per call.
- Softmax and SiLU exps through a four-lane copy of glibc's `__expf_fma` fast path (same constants, table and fused
  operations, disassembled from the container's glibc 2.39 `libm`); special-case inputs (|x| ≥ ~88, inf, nan) call
  `std::exp`. It is used only if a start-up self-test (every 4,093rd float bit pattern plus the special-case
  boundaries) is bitwise equal to the process's `std::exp`; otherwise the scalar calls remain.

## Result

Forward (`heart1logitscheck`, student_sel, 4,383 records x3, one pinned core, otherwise idle container, two
alternating repeats): logits-only pass 887-933 → 450-451 µs per call (about 2.0x); full pass 1,363-1,365 →
730-748 µs (1.8x).

| seed | scope | baseline run s | candidate run s | MCTS CPU s | play |
|---|---|---|---|---|---|
| 111195257 | full run, died A2 F21 | 1,600 | 790 | 1,350 → 763 (1.77x) | identical |
| 111195258 | Act 1 (won) | 486 | 247 | 373 → 211 (1.77x) | identical |
| 111195259 | Act 1 (won) | 516 | 232 | 343 → 205 (1.67x) | identical |
| 111195260 | Act 1 (won) | 522 | 317 | 488 → 285 (1.71x) | identical |

4/4 paired units byte-identical in play. OOC MCTS CPU 1.67-1.77x lower. **Inference:** Act 3 decisions, whose
rollouts reach Act 4 and play imagined Silver fights, gain less (the profile put Silver at 43% of Act-3 CPU).

## Not covered

- Acts 3-4 forwards (records and play) were not part of the parity set; the paths are input-independent
  arithmetic, but no Act 3 record was compared.
- Other CPUs and libm versions: the vector exp self-test decides at run time; the AVX paths need AVX (as before).

## Raw data

`/mnt/project-files/heart1-forward-speedup/raw.tar.gz` (sha256 `dde5d909…`): all unit outputs, record sets,
baseline `heart1score` outputs, scripts, `binaries.sha256`.

Seeds used: 111195256 (capture), 111195257-111195260 (gate). 111195252-255 were the profile runs.
