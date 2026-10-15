# Singleton reroot correction: current-main hard64 holdout

Status: **64 attempted, 63 valid paired replays, one shared technical failure.**
This is not a complete valid N64 confirmation.

## Question and frozen comparison

Does skipping search at a singleton root while retaining the selected edge
reduce Silver work without changing the observed outcomes on the frozen hard
fights?

- **Control:** current `main` at `46684659a0d56729d7af1f8ae2ce9eeab39a6934`.
- **Treatment:** merged PR #315 implementation at
  `be47b2a1502013b04dcdd923b6d14c1c22c7dde1`.
- **Single variable:** the treatment replay invocation enables
  `--skip-singleton-search`; the control does not. The production live path
  uses the same retained-session selector and is covered by the bridge
  continuity regression and flat/adaptive integration checks.
- **Decision rule:** preserve every attempted row; compare paired wins and
  trace hashes alongside simulations and replay time. Treat this cohort as
  descriptive only; it cannot establish equivalence or promote a default.

## Artifact inventory and configuration

The existing `silver_singleton_reroot_hard64_holdout_2026-09-25` packet used
main at `01f6f164`; that result was retained as historical evidence but did not
qualify as the requested current-main comparison. The frozen `hard64-holdout`
input remained suitable: 64 unique stored snapshots and per-fight benchmark
seeds from `silver_hard_combat_v1_20260918`, SHA-256
`e8b914ad74ca0508ee6b1db329c5f454e92e7785cd60af1475d53b35a9d8af34`. No new
states or seeds were collected. The current run reused this exact cohort in
both arms, for 128 arm-case replays total.

Both Release binaries used 10,000 simulations per searched root, allocated
reuse cap 32,768, adaptive search off, exact visit lock off, rho racing off,
and `OMP_NUM_THREADS=4`. Every chunk invocation went through the repository
`tools/seed_guard.sh`; the eight chunks alternated which arm ran first. The
control and treatment were built separately with `cmake --preset
linux-gcc-release` and `cmake --build --preset linux-gcc-build --target
silver-hard-combat-replay`.

- Control binary SHA-256:
  `58a8b80a857bedcb8773f2f26d4390d7f0ec720a9f3984e201821d0714fbdc05`.
- Treatment binary SHA-256:
  `03a6aa7f0dcb613ddbd70beba1e8ed18b59c2ea7ee0102ed71effc31ba8fa63d`.

The exact chunk case IDs, invocation order, command arguments, return codes,
elapsed times, and output hashes are in [`run-order.json`](run-order.json).
The actual runner and analysis scripts are retained as [`runner.py`](runner.py)
and [`analyze.py`](analyze.py).

## Results

| Measure | Control | Treatment |
|---|---:|---:|
| Valid paired cases | 63/64 | 63/64 |
| Wins on valid cases | 57/63 | 57/63 |
| Singleton searches skipped | 0 | 62 |
| Simulations on valid cases | 20,720,000 | 20,060,000 |
| Mean ending HP, losses counted as 0 | 31.635 | 31.794 |
| Summed per-case replay wall time | 189.820 s | 183.421 s |
| Replay failures | 1 | 1 |

There were no outcome flips; mean ending HP changed by **+0.159** for
`treatment - control`. Treatment used **3.185% fewer simulations** and had
**3.371% lower summed replay wall time**. Action trace hashes matched on
60/63 valid pairs. Three valid pairs had different traces but the same
win/loss outcome. These are descriptive observations from this frozen cohort,
not an equivalence test or a universal safety claim.

## Post-run source advance and binary identity

The paired invocations used current main `46684659a0d56729d7af1f8ae2ce9eeab39a6934`
and treatment source `be47b2a1502013b04dcdd923b6d14c1c22c7dde1`. While the
work continued, main advanced to `8ed346ea1e503a85640c44131c05b9e8b5f48f53`
(PR #320). The Release replay target rebuilt from that latest main produced
control binary SHA-256 `58a8b80a857bedcb8773f2f26d4390d7f0ec720a9f3984e201821d0714fbdc05`,
identical to the control binary used for all recorded rows. After merging that
main head into treatment commit `4b1b27f624d5a4ce8b9545f2dffc36d4e10213ee`,
its replay target rebuilt to SHA-256
`03a6aa7f0dcb613ddbd70beba1e8ed18b59c2ea7ee0102ed71effc31ba8fa63d`,
identical to the treatment binary used for all recorded rows. The raw `run-order.json`
retains the exact source commits used at invocation time. No additional seeded
replays were run after this byte-for-byte identity check; the 128 arm-case
replays had already used the local run allowance.

Main subsequently advanced to `03ae0297ac33fba41c64921d5b0bcc6eabe4be2a`
(PRs #318 and #321). Rebuilding `silver-hard-combat-replay` in Release from
that current main and from the merged treatment at
`b0393b034117cbdf5e16b994a0fe50528e89787b` produced the same control and
treatment hashes listed above: control
`58a8b80a857bedcb8773f2f26d4390d7f0ec720a9f3984e201821d0714fbdc05`,
treatment
`03a6aa7f0dcb613ddbd70beba1e8ed18b59c2ea7ee0102ed71effc31ba8fa63d`.
Both rebuilt binaries are byte-identical to those used for the recorded rows,
so the N64-attempted / N63-valid results carry forward exactly. No new replay
rows were generated and the frozen cohort was not rerun.

Main then advanced to `18232bf049a3facade2d5df440a67bb30135f400` (PR #314).
The Release replay binary rebuilt from that main head has SHA-256
`f0367213d95300dac94fcef486aee0ca9ad3b57b30243b1a7c5e060b78323773`; the
final merged treatment at `b6242a65f98d90520440145600241ad5a39d3860` has SHA-256
`ba4ef57db9b2574b144b4aabbe6e851218606564a41c6b8c2f6bb1817c2d2f57`. Both
differ from the binaries used for the N63 rows, so the 03ae byte-identity
check does not extend to this newer source.

The inspected PR #314 changes are default-preserving for the compared replay:
`rolloutUnsortedPilesEnabled` defaults to false, and the recorded invocations
did not pass `--unsorted-rollout-piles`; canonical pile maintenance therefore
remains active. Optional rollout diagnostics are off in those commands. The
harness now defaults search-timing collection off and omits `wall_seconds`
unless `--rollout-diagnostics` is requested, so the recorded 3.371% wall-time
difference remains a result from the original binaries. None of the 64 stored
inputs has `isolated_search_seed`, so the new harness uses the same stored
`benchmark_seed` as before. The `rolloutScratch` terminal-feature change is
confined to the standalone simple-rollout diagnostic; complete-fight replay
does not call that probe.

Decision: no second hard64 gameplay screen was needed for this merge. The
upstream default search path and its seed mapping remain unchanged; the N63
outcomes and simulation counts remain historical observations of the original
binaries, and are not presented as a new-source replay. No new replay rows
were generated.

## Shared technical failure

Case `12100109/21` failed in both arms after 28 decisions / 280,000
simulations with the same `selected_deterministic_state_mismatch`, including
the same action trace hash `5626104837987834096`. The raw failed rows remain in
both arm files and the paired row. No case was removed, replaced, or rerun.
The comparison is therefore **N64 attempted / N63 valid**.

The replay utility exercises the private retained-session zero-search
selector. It does not run live wire materialization or action resolution; the
focused `silver_bridge_boundary` test and both integration modes cover that
production path separately.

## Raw files

- [`control.jsonl`](control.jsonl) and [`treatment.jsonl`](treatment.jsonl):
  64 raw outputs per arm, including the failed case.
- [`paired.jsonl`](paired.jsonl): one paired record per frozen case.
- [`runs/`](runs/): per-invocation stdout and stderr files.
- [`summary.json`](summary.json): hashes, counts, and aggregate metrics.
- [`run-order.json`](run-order.json): chunk IDs, commands, return codes, timing,
  and raw-output hashes.
- [`SHA256SUMS`](SHA256SUMS): packet file hashes.

Knowledge impact: records the current-main N64 attempted / N63 valid rerun and
its shared technical failure. It provides descriptive evidence for reduced
search work; it does not change the Silver default or establish complete N64
confirmation.
