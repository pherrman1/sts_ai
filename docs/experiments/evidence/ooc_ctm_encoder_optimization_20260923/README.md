# OOC CTM encoder optimization screen (2026-09-23)

## Scope and baseline

Both candidates were developed independently from source baseline
`3d28adfcf3c989e338eff9ef85e4a5c6d8794497` and then combined for the PR
candidate. Candidate 1 computes Q only for the global token in encoder layer 2;
K and V for every token remain. Candidate 2 flattens token/QKV/next buffers and
reuses scratch vectors while retaining loop and accumulation order. No gameplay
seed was run for candidates 1 or 2.

Input fixture: `tests/fixtures/combat_transition_near_full.jsonl`, SHA-256
`d464bcc043bd3f9964a2300696f05356a602eb3fb98f01070800cb025e9226ee`.
Native model: `combat_transition_near_full_except_smoke_v2.native`, SHA-256
`e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.

## Candidate 1: final global token only

A fixed supported fixture was timed in Debug, with ten component calls per
process and three process repetitions. Median summed encoder time changed from
26.695 ms to 16.465 ms (-38.3%). This is one fixture and a Debug microbenchmark;
it does not measure end-to-end combat preparation or generalize to other token
counts. The three paired raw JSONL files are in `raw/final-token-*.jsonl`.

The 31-row probe output was byte-identical before and after. Both files have
SHA-256 `dbcee67b1037c86e3f9e96b99c2baac47437e812ebb2629feb257a692fe2dd26`.
The probe checks prepared/reference output, persistent state, and RNG parity for
128 draws per supported fixture.

## Candidate 2: contiguous workspace

Three Release fixed-fixture samples were recorded per arm. Median total
preparation changed from 5.812681 ms to 5.788186 ms (+0.42% faster); this is
noise-sized and not a demonstrated overall speedup. Median component times
(changed relative to baseline) were: survival 1.420455 -> 1.436635 ms,
max-HP 1.461003 -> 1.428701 ms, HP 1.466406 -> 1.432039 ms, potion
1.448413 -> 1.419364 ms. Treat component-level differences of this size as
inconclusive. Raw timing outputs are in `raw/workspace-*.json`.

The independent Release probe output matched across all 31 rows before and
after; baseline, candidate, and combined outputs each have SHA-256
`dbcee67b1037c86e3f9e96b99c2baac47437e812ebb2629feb257a692fe2dd26`.
The combined candidate was built separately in Release and passed the focused
near-full artifact test. Its 31-row output also matches the baseline hash.
No separate timing was collected for the combined implementation.

## Commands and limits

Focused checks for the combined candidate:

```text
cmake -S . -B /tmp/ooc-ctm-combined-release -DCMAKE_BUILD_TYPE=Release
cmake --build /tmp/ooc-ctm-combined-release --target combat_transition_runtime_probe -j2
STS_COMBAT_TRANSITION_PROBE=/tmp/ooc-ctm-combined-release/combat_transition_runtime_probe python3 -m unittest tests.test_combat_transition_near_full_artifact -v
```

Both near-full artifact tests passed. The independently run native-contract test
fails during Python import with `RuntimeError: native write-back set changed;
repeat legality audit`; it was reproduced at the untouched baseline and is not
attributed to these changes. No whole-project CI run or gameplay-quality
comparison was performed. These results are a bounded optimization screen,
not a gameplay or production qualification.
