# PR 295 DeepSets transition-encoder reuse

## Scope and hypothesis

This is a runtime-only optimization of the unqualified all-DeepSets candidate
from PR 295. The candidate artifact installs one shared transition encoder in
the maxHP, signed-HP, and potion groups. Reusing that representation during
prepared CTM construction should remove two of four encoder evaluations while
leaving predictions, support, sampled state, and planner RNG unchanged.

No model, checkpoint, architecture, support, estimator, OOC search, RNG, or
production default changed. Phase 3 profiling and candidates A-D were not run:
Phase 2 produced a clear fixed-input gain, which is the handoff's stop rule.

## Provenance

- Current PR 295 source head: `ae167e1e2eef6e988a61a12a2ef00d5d2d44a301`.
- Local `main` was fast-forwarded to `aa09f75e6be837f7f39a2e31dde234bfd2c2ef08`.
- Candidate code tree: `e2e7206a90f6dfc66d7bb1722ebf43c78717dee7`.
- Optimization commit: `bc535b541524f0ee3cc5654e58c9fe5e3e49d47d`.
- Candidate artifact SHA-256:
  `3f6d174950f1e4a8b042cebc78bd8525c7e112a13e31865670a39df4b0f2f586`.
  This is PR 295's provenance-hardened re-export; its tensor payload is
  byte-identical to the originally profiled artifact.
- Original fixture: `tests/fixtures/combat_transition_near_full.jsonl`, SHA-256
  `d464bcc043bd3f9964a2300696f05356a602eb3fb98f01070800cb025e9226ee`.
- Fixed fixture used here sets only each row's `draws` field to 128; its SHA-256
  is `a78db761198b56cb8b57eff11b0bbbfbf6fa2c0dd741e3565d28c1b6d90ae720`.
- Timing fixture is the first supported row with `draws=128`, SHA-256
  `c0100a7d22e4110328e7b5e8c396ca08329e2b5f33554530d181eec01085c960`.
- Full pre-change and candidate outputs are independently retained as
  gzip files `identical-runtime-outputs-baseline.jsonl.gz` and
  `identical-runtime-outputs-candidate.jsonl.gz`. Their unmodified output
  fields compare byte-for-byte. The stored canonical form removes the
  deterministic 256-word lookahead array per draw; `wordsUsed`, outcomes, and
  complete sampled states remain, and the probe verifies planner RNG equality
  directly. The probe reports `maxHpEncoding` on both runs to expose the
  shared-representation check.

## Shared tensor and representation evidence

The candidate artifact contains 28 encoder tensors in each of
`max_hp.encoder.*`, `hp.encoder.*`, and `potion_encoder.encoder.*`. The raw
tensor bytes are identical across all three groups. Their ordered concatenated
SHA-256 is `4a86d77cdcd49ab5909ce77128bcfbb50de8debef5ac3cb8cece96f2d9df38a2`.
The exporter writes all three groups from the same checkpoint
`bee6800dd7230b180c2b4894c0f01763efca4b7799e3f36a805333c3003dc663`.

The Release probe evaluates `maxHpEncoding`, `hpEncoding`, and
`potionEncoding` on all 28 supported fixtures. All 64 values are identical for
each input. `tensor-identity.json` records the artifact and fixture hashes and
the byte-level tensor comparison.

## Implementation and correctness

For the exact PR 295 DeepSets artifact identity, `prepare()` now computes the
survival encoder once and computes the shared transition representation once.
That representation feeds the maxHP head and is retained for the signed-HP and
potion heads. The standard attention branch retains its previous four-call
preparation and the original `maxHp(input)` implementation.

Before/after `near-full` probe output covers 31 fixtures: 28 supported and 3
unsupported. Each supported fixture has 128 prepared/reference draws (3,584
total). The outcomes, full deterministic outputs, support classifications,
complete persistent post-states, and planner RNG post-state checks match. Both
full output files have SHA-256
`a0f8cb9e5d08c995f90489c6e878bbf25c31533010ab25cf6dfbe3da344a36da`. The
baseline and candidate were rebuilt from the current PR 295 head with and
without only the reuse branch; complete JSONL output is byte-for-byte equal.

The fixed-fixture prepared/reference probe also reports 128 draws, equal
support, full persistent-state equality, planner RNG equality, and an exact
prepared encoder call count of 2. The pre-change `NativePrepared` call graph
made four calls: survival, maxHP, HP encoding, and potion encoding. The
post-change call graph makes two: survival and shared transition encoding.

## Release preparation timing

Each measurement used the same single fixed fixture and candidate artifact. The
existing probe timed `prepare()` once per process, then checked 128 sampled
draws. There were 30 independent Release process repetitions per version.

| Version | Median | p10-p90 | Range | Encoder calls |
| --- | ---: | ---: | ---: | ---: |
| PR 295 current-head baseline | 284,427 ns | 280,665-336,479 ns | 280,254-357,929 ns | 4 |
| Shared encoder | 142,541 ns | 140,252-149,509 ns | 140,062-265,236 ns | 2 |

Median preparation time fell by **49.88%**. The observed ranges do not overlap.
Raw samples are in `prepare-baseline.json` and `prepare-candidate.json`.

For bounded context, PR 295's one-seed DeepSets profile attributed 11.962 s of
83.772 s MCTS CPU to CTM preparation (14.28%). Applying the fixed-fixture
reduction to that same-work profile projects about **7.12% less MCTS CPU**, or
approximately 1.077x speed, if all other work remains constant. This is an
inference from unlike scopes, not a measured whole-search speedup; no gameplay
or same-workload MCTS claim is made.

## Commands and results

- Release configure and `combat_transition_runtime_probe` build: PASS.
- Release `one_combat` build: PASS. Existing warnings include third-party
  missing-return warnings, a narrowing warning, and an LTO ODR warning.
- Full fixed-fixture `near-full` probe before and after: PASS; 31 rows and 128
  draws per supported row. Output equality as described above.
- Fixed-fixture `smoke-and-parity` probe: PASS for each of 30 timing
  repetitions; 128 draws, support/state/RNG parity, 2 prepared encoder calls.
- Focused CTest: `ctest --test-dir build/linux-gcc-release -R
  'combat_transition_runtime_loader|combat_transition_near_full_artifact'
  --output-on-failure`: PASS, 2/2.
- Standard attention artifact smoke: PASS on the same fixed fixture; preparation
  remains at 4 encoder calls with equal support, persistent state, and planner
  RNG. Raw probe output is `attention-unchanged-smoke.jsonl`.
- A separate `smoke-and-parity` invocation over all 31 rows returned
  `invalid_relic_counter`; the `near-full` mode completed the same rows and
  performs the required prepared/reference state and RNG comparisons. The
  focused CTests and fixed one-row repetitions passed.
- Full CTest and GitHub Actions Linux GCC were not run. No game seeds were run.

Knowledge impact: benchmark evidence only; no maintained runtime contract,
qualification, or default changed.
