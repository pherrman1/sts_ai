# Native combat adapter parity and bounded smoke

Baseline: `d68545d50ea018f6e6d38cfb2c282c7e99e58edc`.
Exporter/native inference independently reviewed and frozen before export at
`ec30dbfda896867e78a3f5bc2fc519134b75e19b`. Probability tolerance fixed in
that commit: max absolute disagreement `1e-4`, CPU FP32, one thread, batch 1.
No training, gameplay seeds, data collection, architecture changes or policy tuning.

Decision: **RUNTIME_COMBAT_ADAPTER_READY**, for the combat boundary only.
The complete planner remains scientifically unqualified because other
stochastic OOC transitions execute from copied native hidden RNG.

## Provenance and fixture scope

[Machine-readable evidence](native_combat_adapter_2026-09-14.json) contains all
six source SHA256 identities, export size/hash, fixture receipt, per-component
errors, invalid counters and latency. The exporter verified every source hash
before loading and exported once. Real model/fixtures/raw output remain external:

`/home/philippherrmann/sts_sweep/runs/combat-transition-runtime-native-20260914/`

Native artifact `combat_transition_v1.native`: 2,134,285 bytes;
SHA256 `f9520a14b1fc42e2a22840c0c2cab0b13ebd8ab6285b5c943662f5e0e9cd9233`.

16 supported captured fixtures cover Acts 1/2/3, normal/elite/boss,
healing/loss/unchanged HP, nonzero maxHP delta, potion use/no use, and multiple
relic trajectory groups. Seven prestate mutations cover HP envelope, invalid
misc/potion RNG, Smoke Bomb, Entropic Brew, active Lizard Tail and Inserter.
Captured source TEST rows match their existing #174 preflight SHA receipt.
Inserter is a deliberate conservative runtime exclusion, applied to both
sides of support parity; it had zero qualification corpus tokens.

## Probability and support parity

23/23 support decisions match. Class domains match; explicit HP/potion legal
masks match and illegal probabilities are exactly zero. No NaN/Inf.

| Component | Maximum absolute probability error |
| --- | ---: |
| Survival | 1.1921e-7 |
| maxHP | 6.9849e-9 |
| signed HP | 2.0862e-7 |
| Potion | 1.7881e-7 |
| Relic turns | 1.1921e-7 |
| Relic attacks | 1.0431e-7 |
| Relic cards | 5.9605e-8 |
| Relic shuffles | 1.4901e-7 |

Parity ran before smoke; no tolerance, weight or network adjustment followed.

## Continuation and integration checks

Eight focused CTests pass: `ooc_mcts`, `ooc_mcts_adapter`,
`combat_transition_oracle`, `combat_predictor_input`,
`combat_predictor_input_contract`, `combat_transition_composed_selftest`,
`combat_transition_native_contract`, `combat_transition_runtime_loader`.
The adapter compares real deterministic native exit against injected RAW apply
plus one native continuation: exact OOC/persistent/reward/RNG fingerprints and
PathHistory. No-sampler/ordinary/unsupported successors preserve prior behavior;
death has exact terminal zero without rewards. Actual planner chance expansions
receive the expected planner RNG draws and retain progressive widening metrics.
A second BATTLE continuation remains a leaf. Root/maps remain detached.

Four direct RNG/relic parity tests cover every encounter, 60 shared-residue
combinations and a crafted bounded-rejection state where bare setCounter fails.
Malformed loader tests reject wrong magic/version/dimensions, truncated header
and incompatible predictor schema; external real-artifact tests also reject
truncated weights and trailing data. Missing artifact construction throws.

Default gameplay, `runFullRunOOC`, `bestbench`, V4 priors, leaf values, PUCT and
progressive widening implementation/configuration are unchanged. The artifact
is loaded only through an explicit sampler path; no default policy enables it.

## Sampling validity and latency

16 supported states × 32 independent draws = 512. Diagnostic frequencies:
480 victories, 32 deaths. All seven invalid counters are zero: illegal HP,
potion mutation, relic state, shared residue, inherited RNG, copy-through and
duplicate continuation. The smoke continuation uses a counted callback; the
separate adapter oracle validates actual native reward construction exactly.

One-thread batch-1 conditional mean sampler latency, including its own support
check: death 1.482 ms; victory 4.275 ms. Support alone 0.626 µs. Ten repeated
component calls per fixture average survival 1.090 ms, maxHP 1.084 ms,
signed-HP encoder 1.076 ms, potion encoder/head 1.084 ms, signed-HP head
0.0107 ms and relic decoder 0.00419 ms. Four separate Attention encoders dominate.
Conditional path averages use different state mixtures, so component averages
need not sum exactly to the victory conditional mean.

The native victory path is descriptively slower than #174's Python CPU reference
(~3.32 ms); fixture mixtures differ, so this is not a paired speed claim.
No optimization or encoder merging was attempted. Native Attention arithmetic
is the measured bottleneck for a later bounded optimization task.

## Reproduction

```sh
python3 tools/export_combat_transition_runtime.py --output "$RUN/combat_transition_v1.native"
python3 tools/qualify_combat_transition_runtime.py fixtures --source /home/philippherrmann/sts_sweep/runs/composed-transition-20260914/test_rows.jsonl --output "$RUN/fixtures.jsonl"
python3 tools/qualify_combat_transition_runtime.py parity --model "$RUN/combat_transition_v1.native" --probe build/linux-gcc-release-ccache/combat_transition_runtime_probe --fixtures "$RUN/fixtures.jsonl" --output "$RUN/parity.json"
# Only after parity passes:
python3 tools/qualify_combat_transition_runtime.py parity --model "$RUN/combat_transition_v1.native" --probe build/linux-gcc-release-ccache/combat_transition_runtime_probe --fixtures "$RUN/fixtures.jsonl" --output "$RUN/smoke-components.json" --smoke
ctest --test-dir build/linux-gcc-release-ccache -R '^(ooc_mcts|ooc_mcts_adapter|combat_transition_native_contract|combat_transition_runtime_loader|combat_transition_oracle|combat_predictor_input|combat_predictor_input_contract|combat_transition_composed_selftest)$' --output-on-failure
```

`RUN` denotes the external directory above. Exclusive export intentionally
rejects an existing model path. The full default CMake target set builds; the
full CTest suite and gameplay/win-rate benchmarks were not run. GitHub Linux GCC
CI remains authoritative for repository verification.
