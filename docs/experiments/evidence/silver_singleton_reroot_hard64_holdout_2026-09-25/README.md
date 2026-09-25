# Singleton reroot correction: frozen hard64 holdout

Status: N64 attempted; **63 valid paired replays and one shared technical
failure**. This is not a complete valid N64 confirmation.

## Question and comparison

The question was whether selecting a singleton root with zero new simulations
while retaining the selected edge changes complete frozen-fight outcomes or
reduces Silver work. Control is current `main` at
`01f6f164a0fe757ec174738ac3a2f0fb98c2462d`. Treatment is the corrected PR
implementation at `2da8eed6a9c7faecd82effdd1751265eac1b42fd`, with the
benchmark-only `--skip-singleton-search` switch enabled.

The switch is off by default and only affects `silver_hard_combat_replay`.
It selects the sole private-root edge through the retained-session zero-search
selector. The actual live wire materialization, semantic surface validation,
and action resolution remain covered by `silver_bridge_boundary` and the live
integration checks; this frozen replay does not invoke `SilverLiveBackend.cpp`.

## Frozen inputs and configuration

- Cohort: `hard64-holdout` from
  [`silver_hard_combat_v1_20260918`](../silver_hard_combat_v1_20260918/README.md).
- Snapshot rows: 64 unique cases, each with its stored deterministic benchmark
  seed. SHA-256:
  `e8b914ad74ca0508ee6b1db329c5f454e92e7785cd60af1475d53b35a9d8af34`.
- Both arms used the same frozen state and stored benchmark seed per case,
  10,000 simulations per searched root, allocated reuse cap 32,768, adaptive
  search off, exact visit lock off, rho racing off, and `OMP_NUM_THREADS=4`.
- Each replay was launched through `tools/seed_guard.sh` in balanced 8-case
  blocks; the first arm alternated by block. Block 6 treatment stopped on the
  technical failure, then control was run on the same block. The case was not
  replaced.
- Control Release binary SHA-256:
  `58a8b80a857bedcb8773f2f26d4390d7f0ec720a9f3984e201821d0714fbdc05`.
- Treatment Release binary SHA-256:
  `03a6aa7f0dcb613ddbd70beba1e8ed18b59c2ea7ee0102ed71effc31ba8fa63d`.

The control and treatment binaries were built separately from their pinned
worktrees with `cmake --preset linux-gcc-release` and
`cmake --build --preset linux-gcc-build --target silver-hard-combat-replay`.
For each 8-row input chunk, the commands were:

```bash
env OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  /tmp/sts-singleton-main-control/build/linux-gcc-release/silver_hard_combat_replay \
  CHUNK.jsonl 10000

env OMP_NUM_THREADS=4 bash tools/seed_guard.sh \
  build/linux-gcc-release/silver_hard_combat_replay \
  CHUNK.jsonl 10000 --skip-singleton-search
```

The concrete arm order is in [`run-order.json`](run-order.json). The output
JSONL files preserve every attempted case, including the common failure.

## Results

| Measure | Control | Treatment |
|---|---:|---:|
| Valid cases | 63/64 | 63/64 |
| Wins on valid cases | 57/63 | 57/63 |
| Singleton searches skipped | 0 | 62 |
| Simulations on valid cases | 20,720,000 | 20,060,000 |
| Mean decisions per valid case | 32.889 | 32.825 |
| Mean terminal HP (losses=0) | 31.635 | 31.794 |
| Summed per-case replay wall | 189.465 s | 183.797 s |
| Replay failures | 1 | 1 |

Among the 63 valid pairs, there were zero outcome flips and mean ending HP
changed by **+0.159** (treatment minus control). Treatment used **3.185% fewer
simulations** and **2.991% less summed per-case replay wall time**. Action trace
hashes matched on 60/63 valid pairs; three traces differed without an outcome
flip. These are bounded descriptive results, not an equivalence test or a
universal safety claim.

## Shared technical failure

Case `12100109/21` failed in both arms with
`selected_deterministic_state_mismatch` after 28 decisions and 280,000
simulations. The mismatched state differs in hand UID order while the other
reported player, monster, metadata, and RNG comparisons match. Replaying this
same frozen row separately on current main, treatment with the switch off,
and treatment with the switch on produced the same failure text, action trace
hash `5626104837987834096`, and simulation count. The failure therefore does
not isolate to the singleton bypass. It remains a limitation of this cohort
under the merged base.

Because one case failed identically in both arms, report the experiment as
**N64 attempted / N63 valid**, not a full N64 result. The previous supplied
59/64 result remains pre-reroot-correction evidence and has no raw packet or
candidate SHA available in this checkout.

## Raw files

- [`control.jsonl`](control.jsonl) and [`treatment.jsonl`](treatment.jsonl):
  all 64 per-case rows per arm.
- [`paired.jsonl`](paired.jsonl): paired outcomes, work, wall time, and failure
  status.
- [`summary.json`](summary.json): hashes, aggregate metrics, accounting, and
  technical failure text.
- `technical-failure-*.jsonl`: the identical case rerun in main and treatment
  both with the benchmark switch off and on.
- [`SHA256SUMS`](SHA256SUMS): packet file hashes.

Knowledge impact: records the first available post-correction frozen hard-fight
replay evidence and its shared technical exclusion. The result does not change
the Silver default or establish complete N64 confirmation.
