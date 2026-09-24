# Silver rollout-cost corrected DEV follow-up

**Status:** the planned first-action DEV screen is complete under the disclosed
execution seed transform. The fixed-work primary mean was directionally
non-worse, the conditional 1,100-versus-1,000 screen was positive, and separate
uninstrumented CPU pairs were faster with B. An audit found the executed seed
transform differed from the literal transform in the committed protocol; exact
preregistration fidelity is unresolved. This is bounded DEV evidence only. It
does not qualify gameplay, establish holdout performance, or promote B; the
runtime default remains off.

## Frozen inputs and implementation

The protocol was committed before the follow-up searches at implementation
SHA `1e63068ff548abb18638e4b02d60e7e0d6dc936c` and is preserved in
[`PROTOCOL.md`](PROTOCOL.md), with an execution deviation appended after an
independent evidence review. It uses the frozen 64-row
[`hard64-dev-snapshots.jsonl`](../../silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl),
SHA-256 `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`.
The status-only smoke fixed the eligible mask at 59 roots; five rows returned
`transactional_selection_required` and were excluded from every teacher and
arm. The mask was not selected using actions or outcomes.

The protocol and implementation commit called this experiment §343 on the
then-current main. After current main advanced with §§343–347 on active Lizard
work, this report is appended as §349 in the merged branch. This ledger
renumbering does not change the protocol baseline or experiment data.

The tested baseline was current `main` `01f6f164a0fe757ec174738ac3a2f0fb98c2462d`.
The reviewed candidate implementation was frozen at
`1e63068ff548abb18638e4b02d60e7e0d6dc936c`. B is enabled only by the explicit
`--unsorted-rollout-piles` opt-in. The actual current-main Release replay
binary SHA-256 is
`58a8b80a857bedcb8773f2f26d4390d7f0ec720a9f3984e201821d0714fbdc05`; the
frozen-candidate Release replay binary SHA-256 is
`f0367213d95300dac94fcef486aee0ca9ad3b57b30243b1a7c5e060b78323773`.

The baseline build helper could not build a `git archive` because this
repository's CMake configure reads `git rev-parse HEAD`. The baseline was then
built from the exact `01f6f164...` archive with the pinned submodule archives
and minimal temporary Git metadata pointing at that exact commit; the build
succeeded without changing tracked source. This limitation and workaround are
recorded so the baseline provenance is explicit.

Before the follow-up, the candidate with B disabled matched the actual current
main binary's selected-action fingerprint on all 59 eligible roots at 1,000
simulations. The 1-simulation status smoke also reproduced the same five
technical failures. The parity and status rows are retained under `raw/`.

### Seed-transform deviation

The seed transform in the protocol committed at the frozen implementation SHA
used path components such as `teacher-01/01` and `arm-01/01`. The retained
input helper generated `teacher/01` and `arm/01` instead. The output manifest
matches the helper's recipe for 413/413 root-identity entries and the committed
protocol recipe for 0/413. The helper and manifest have filesystem mtimes
before the result rows, but no durable pre-collection protocol amendment was
retained; the reason for the change is unknown. This exact preregistration
deviation is material and remains unresolved.

All generated seeds are still deterministic hashes of the fixed case ID and
state-bound `benchmark_seed`; three teacher and four arm identities are
pairwise distinct per root, and the same arm identity was paired across
control/B. The results are therefore reported under the executed transform,
with the independent-seed property preserved, but should not be described as an
exact reproduction of the committed seed recipe.

## Independent teachers and matched fixed work

The adapter used by the frozen candidate supplies an `isolated_search_seed`
while preserving each snapshot's state-bound `benchmark_seed`. The three
10,000-simulation teachers used independent seed identities, diagnostics off,
and B disabled. All 177 teacher rows succeeded (1,770,000 simulations). The
four arm identities were reused pairwise across control and B at 1,000
simulations; diagnostics and search timing were off. Every arm produced 59
successful rows.

Three teachers agreed by majority on 52 of 59 roots; seven roots had no
majority. On the 52 consensus roots, first-action agreement was:

| Measure | Control | B | B minus control |
| --- | ---: | ---: | ---: |
| Consensus action agreement | 54.3% | 58.7% | +4.3 pp |
| All-teacher agreement, all 59 roots | 49.6% | 51.7% | +2.1 pp |

The primary root-cluster bootstrap 95% interval for the paired consensus
difference was **−1.4 to +10.1 pp** (10,000 replicates, seed `20260925`). It
crosses zero. The preregistered directional rule checked whether the primary
mean was non-negative; it was **+4.3 pp**, so the conditional equal-time
screen was run. The all-teacher paired difference interval was −2.3 to
+6.5 pp. Counts across consensus roots were 16 B-positive, 9 B-negative, and
27 tied.

## Conditional equal-time-equivalent screen

The four matched identities were replayed at 1,000 control versus 1,100 B
simulations per root, with diagnostics off and all 59 roots successful. On 52
consensus roots:

| Measure | Control, 1,000 | B, 1,100 | B minus control |
| --- | ---: | ---: | ---: |
| Consensus action agreement | 54.3% | 61.5% | +7.2 pp |
| All-teacher agreement, all 59 roots | 49.6% | 54.0% | +4.4 pp |

The primary paired root-cluster bootstrap 95% interval was **+1.0 to +13.5 pp**.
The all-teacher paired interval was −0.3 to +8.9 pp. Across consensus roots,
20 favored B, 8 favored control, and 24 tied. This is a conditional DEV
first-action screen; it is not a full-combat or gameplay result. From the
external timing log, mean user CPU was approximately 0.760 s control versus
0.738 s B, and mean elapsed time was 0.775 s versus 0.758 s. B was faster in
aggregate, though its user CPU was higher in two of the four paired timings;
the equal-time characterization is therefore a close bounded proxy.

## Uninstrumented CPU confirmation

Four 1,000-simulation control/B pairs used the same 59 roots and matched arm
identities, with rollout diagnostics and search timing disabled. Commands were
pinned to CPU 2 with `OMP_NUM_THREADS=1`; process CPU and elapsed time were
collected externally. Mean user CPU was **0.740 s control versus 0.675 s B**
(−8.8%); medians were 0.740 s versus 0.665 s (−10.1%). B had lower user CPU
in all four pairs. The mean is below the task's 15% target and just below its
approximate 10% materiality guide; the median reaches 10%. The positive paired
equal-time first-action result is the evidence that makes this small candidate
worth review, while the speed estimate remains bounded to this machine and
cohort. The per-run CPU and elapsed measurements are in
[`raw/timings.tsv`](raw/timings.tsv), and the derived summary is
[`raw/cpu_summary.json`](raw/cpu_summary.json).

The guarded command shape for the first-decision searches was:

```sh
taskset -c 2 env OMP_NUM_THREADS=1 bash tools/seed_guard.sh \
  "$REPLAY_BIN" "$INPUT_JSONL" "$BUDGET" --first-decision-only > "$RAW_JSONL"
```

For B arms only, append `--unsorted-rollout-piles`; control and teacher runs
omit it.

For the CPU confirmation, `/usr/bin/time` wrapped that guarded command; no
replay timing or rollout telemetry was enabled. `prepare_inputs.py` recreates
the seven independent-seed JSONL inputs and the manifest from the frozen
snapshots plus the retained status smoke. The scripts and raw inputs/results
are included in this packet. `analyze_results.py` revalidates result membership,
status, budget, treatment flag, diagnostics state, and both seed fields before
calculating the summaries.

## Checks and limits

- Exact current-main versus candidate B-off action parity: 59/59 at 1,000
  simulations.
- Candidate Debug focused CTests: `silver_search_optimization`,
  `silver_bridge_boundary`, `card_pile`, and `card_pile_engine` passed (4/4).
- Agent seed-guard Python tests passed (5/5); CLI smoke confirmed default-off
  B and diagnostics, opt-in B, diagnostics output when requested, and a high-bit
  unsigned 64-bit isolated seed.
- The guard accepted the 59-row screen inputs and enforces the 128-root local
  cap. All planned arm outputs (8 fixed-work, 8 equal-time, and 8 CPU files)
  validated with expected status, seed, and configuration metadata; the
  analysis validator also checked all teacher outputs.
- `git diff --check` passed before the report was finalized.

The full CTest suite and GitHub Actions were not part of this local evidence
collection; Linux GCC CI is the PR verification gate. No holdout snapshot,
complete-combat replay, gameplay seed, or additional tuning was used. Keep B
default-off and treat the result as DEV evidence pending the ordinary PR review
and CI process.

[`raw/SHA256SUMS`](raw/SHA256SUMS) records hashes for every raw row, manifest,
summary, and timing file in this packet.

**Knowledge impact:** current research and §349 record the corrected result,
the shared-reference-RNG invalidation, and the limits of this first-action DEV
screen. No runtime default or gameplay qualification changes.
