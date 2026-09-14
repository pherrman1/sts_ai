# Exact OOC MCTS computation optimizations

Baseline: `210f347334898e7c2a85b8af0f30dedc4888ea88`, verified current main at
entry and again before publication. One clean Codex app worktree; no dependency
on PR #182 or combat-support expansion. Candidate executable/source hashes are
in [fixed-search-summary.json](fixed-search-summary.json); the draft PR records
the committed head. All model files, policies, model outputs, RNG distributions,
PUCT/widening formulas, horizons and native combat reconstruction are unchanged.

## Cheap cost measurements

The captured-model probe used 23 existing fixtures (16 supported, 7 unsupported).
Successful uncached samples averaged about 4.240 ms in the initial smoke.
Survival, max-HP, HP encoding and potion including its encoder each cost about
1.07–1.09 ms. HP/relic conditional heads cost about 10.7/4.5 microseconds.
[Initial raw probe](combat-baseline.jsonl), [prepared probe](combat-prepared.jsonl),
[summary and model/fixture hashes](combat-summary.json).

The baseline logic replay's first fixed root cost 419.230 ms. Temporary nested
timers subtract child time, giving this approximate split:

| Cost | Milliseconds | Fraction |
| --- | ---: | ---: |
| Tree bookkeeping and native primitive residual | 0.407 | 0.10% |
| Detached GameContext/map copying | 0.558 | 0.13% |
| Action enumeration, tokens and V4 prior | 0.716 | 0.17% |
| Combat inference/sampling, support and native postprocessing | 181.863 | 43.38% |
| Leaf continuation and native win value | 235.686 | 56.22% |

Copy timing excludes the small PathHistory array assignment. The residual also
includes primitive execution and timing overhead, so it is not a pure selection
timer. This depth-one synthetic fixture is not a representative whole-game
cost distribution. Throwaway timers exist only in ignored build evidence,
not maintained source.

The root made 80 combat samples across 3 unique combat edges (26.67 samples/edge),
created 81 stored states/decision nodes, and performed 592 detached copies.
Baseline calls: candidate enumeration 1,188; boundary checks 1,106; V4 prior/token
builds 1 each. Optimized metadata builds are 81; prior/token builds remain 1.
Original adapter fixture construction found zero sole-action roots among 41
supported fixture roots, including the two benchmark models. This synthetic
count does not estimate the live trivial-root fraction. A new forced sole-action
fixture separately proves the abort/fallback bypass contract.

## Exactness and performance

Prepared draws matched the uncached reference for 32 seeds and four sequential
draws per fixture: 2,944 full persistent-state JSON and mt19937_64 post-state
comparisons, including unsupported cases, 1,909 victories and 139 deaths.
All initial baseline probability outputs are exactly equal. Native reconstruction
and survival/maxHP/HP/potion/relic draw order are retained.

Uncached sampling averaged 4.393 ms; prepared draws 22.884 microseconds.
Preparation amortized over 128 draws averaged 60.328 microseconds/sample (72.82x).
Inferred expensive encoder calls fell from 7,775 to 64. These counts cover the
parity draws/preparations, excluding separate component/probability probes.

The same fixed native-search fixture ran baseline/optimized in interleaved
order three times, pinned to Linux CPU 0 with one OpenMP thread. GameContext
seed 42, search seed 20260914, Ironclad A0, 512 simulations, depth 1, PUCT 1.5,
widening k=2/alpha=0.5, V4 priors/native win leaves, checkpoint resolution enabled.
A native regain-control callback returns to MAP to isolate searched combat from
reward projection. Search timing excludes adapter construction/destruction and
live action execution; no real gameplay occurs.

Median baseline search: **387.760 ms**, optimized: **231.556 ms**; **1.675x**,
**40.28% lower wall time**. About 1,320 -> 2,211 simulations/sec and
206 -> 345 combat samples/sec. Encoders: 320 -> 12; all 80 samples and 81 states
remain. Every run had exactly equal selected action, IDs/order/priors, root
visits/Q, all unchanged tree counters, and every generated snapshot/PathHistory.
[Summary, repeated timings and payload digest](fixed-search-summary.json),
[raw baseline](fixed-search-baseline-1.log), [raw optimized](fixed-search-optimized-1.log).
Original unmodified baseline adapter self-test stdout also equals final stdout
byte for byte: [baseline](adapter-baseline.log), [final](adapter-final.log).

Prepared combat sampling accounts for the demonstrated native-search gain.
The optimized uncached control median is 397.117 ms; these three timings do not
demonstrate an isolated native wall-time benefit from metadata/arena changes.
Metadata eliminates repeated enumeration; the arena eliminates 80 individual
particle-node heap allocations in this fixture, while retaining container/map
allocations. A standalone synthetic planner suite measured 11.376 -> 10.380 ms
median/process in five batches of 30 (8.8% descriptive reduction); the final
optimized suite also includes additional lock tests. Optimization-only printed
stats matched baseline before those tests were added.
[Planner timing samples](planner-timings.json), [baseline](planner-baseline.txt),
[optimized](planner-optimized.txt).

The sole-root abort test executes the exact original fallback primitive and
preserves complete live state/RNG, with zero simulations/attempts/combat draws.
No live bypass speed estimate is made. The qualified non-aborting toy lock test
uses 52/100 simulations, saves 48, and selects the same action as full budget.
Equality, catchable challengers, mean-Q selection, one action, unsafe models,
late aborts and adversarial remaining allocations are tested. Locked-root
stopping is **dormant in OocGameContextModel**: unsupported combats, continuation
limits and forbidden native-imagination paths remain possible. No assumption
flag or observed-zero-abort shortcut is provided.

Copying is immaterial in the measured fixture, so no Map/GameContext ownership
refactor, copy-on-write, or deeper copy optimization was attempted. No conditional
head memoization was justified by the microsecond head timings. No gameplay
quality or full-game speed claim follows from these engineering measurements.

## Reproduction and checks

Use the release ccache preset; build `one_combat`, `ooc-mcts-test`, and
`combat_transition_runtime_probe` before checks. The offline probe command is
`combat_transition_runtime_probe MODEL FIXTURES smoke`. External frozen inputs:
`/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-native-20260914/`;
model `combat_transition_v1.native`, input `fixtures.jsonl`. They are not vendored
or modified. Their full SHA256s and the V4/win/rich model hashes are recorded.

Set `OMP_NUM_THREADS=1`, `STS_NATIVE_OOC=1`,
`STS_OOC_STRATEGIC_TOK_NN` to the tracked final V4 artifact, and
`STS_OOC_MCTS_MICROBENCH_MODEL` to the frozen native model. Invoke
`bash tools/seed_guard.sh build/linux-gcc-release-ccache/one_combat oocmctsselftest`.
The opt-in fixture prints MICROBENCH timing/counters and MICROBENCH_PARITY exact
root/tree/state/history JSON. The repeated baseline replay restored the baseline
adapter/planner implementation in this existing build directory, retaining final
telemetry ABI and the probe/getter. Its model class and three constructor probes
in otherwise unchanged main were renamed for independent linkage. Remaining
objects/model runtime used the same build; uncached runtime probability parity
against the initial baseline was proven. This is a baseline-logic replay, not a
pristine second full repository build. No additional worktree was created.

[Check receipt](checks.json), [core/runtime CTests](core-runtime-final-ctest.log),
[final adapter/startup CTests](adapter-startup-final-ctest.log). Eight selected
CTest checks pass; final GCC ASan+UBSan [planner run](planner-sanitizer.log) passes
176 checks. The initial two execution failures overlapped relinking
([raw log](ctest-link-overlap.log)); final reruns pass. Existing SimpleAgent/Silver
ODR and narrowing/LTO warnings were present in baseline builds as well.
Full local CTest and gameplay cohorts/canaries were not run. GitHub Linux GCC
is the authoritative repository check; its SHA-bound state belongs in the PR.

Knowledge impact: maintained OOC interfaces/architecture/telemetry, code-map
navigation, focused parity procedure, and this chronological microbenchmark.
