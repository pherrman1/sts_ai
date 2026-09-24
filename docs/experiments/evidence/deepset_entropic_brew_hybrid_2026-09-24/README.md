# Experimental DeepSets CTM with Entropic Brew fallback

Status: implementation/mechanism and fixed-fixture timing evidence only. The
paired OOC MCTS engineering screen has not run. No default changed and no
gameplay-quality conclusion is available.

## Provenance

- Baseline: `41c0f5af5711c452b6e133e6dc66c7756f50874c` (merged PR #303).
- Required specialist checkpoint: `W.pt`, SHA256
  `71d88a71cf7579e1092c3b3c27e000538a6aafe35bbf5228c10c15fa0edd4ace`,
  selected epoch 27. The checkpoint was already present at
  `/tmp/deepset-potion-specialist-20260923/W.pt` and was reused unchanged.
- Exported experimental native artifact SHA256:
  `a23c0f86593fef2380c3efee3cf75783bf2b5e714395ec93237fac19376bfd1a`.
- Current standard fallback artifact SHA256:
  `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.
- The exported artifact remains unqualified and does not change the default.

## Mechanism and parity

Specialist Python/native parity passed on all 31 frozen predictor fixtures at
absolute tolerance `1e-4`: maximum encoder error `7.75e-7`, maximum probability
error `4.77e-7`, and zero legal-mask mismatches. The fixtures cover acts 1/2/3,
capacities 3/5, boss/non-boss states, occupied potion counts 0/1/2/3/5, 18
Brew-labeled rows, and one Smoke row. This is numerical parity evidence, not an
offline Brew qualification.

The hybrid mechanism probe passed all 31 fixtures. Hybrid support, scalar and
prepared samples, complete RAW state, and RNG state matched the selected direct
child; routing consumed no planner RNG. Direct use of the specialist on a
pre-combat Brew input failed closed. The hybrid routed all 18 such fixture rows
to the standard sampler and 13 ordinary rows to DeepSets. Across repeated
probe calls it observed 14 unique Brew predictor states, 18 fallback
preparations, 36 fallback samples, 13 fast preparations, and 26 fast samples.
These fixture counts are deliberately not an estimate of live OOC frequency.

Why dispatch uses pre-combat inventory: the known recursive Brew trajectory
starts with Entropic Brew already visible in the initial inventory. Therefore
the wrapper routes that whole transition to standard CTM; it never switches
models after seeing generated trajectory outcomes.

## Fixed-input timing

Release benchmark command:

```sh
build/linux-gcc-release/combat_transition_runtime_probe --benchmark \
  /tmp/deepset-entropic-hybrid-specialist.native \
  selfplay/models/combat_transition_near_full_except_smoke_v2.native \
  tests/fixtures/combat_transition_near_full.jsonl 100
```

It used 10 warmups and 100 repetitions per input on the same 31-row fixture
file. The comparison now times standard and fast on the same 10 non-Brew rows
supported by fast DeepSets. Median preparation was 3,715 us for standard and
491 us for fast (7.57x); hybrid fast was 487 us on those same rows. Median
prepared sampling on those rows was 39.5 us standard and 35.0 us fast. On 18
supported Brew rows, standard preparation was 3,315 us and hybrid fallback
was 3,419 us; sampling was 41.7 and 44.4 us. Encoder calls per preparation
were 4 for standard/fallback and 3 for fast. The file's 18/31 Brew mix is
fixture-driven and heavily overrepresents the stated ~0.6% offline frequency;
neither its dispatch fraction nor a weighted runtime estimate represents OOC
search. The matched non-Brew subset shows a fixed-input preparation advantage,
while Brew preparations pay approximately standard cost.

## Checks and remaining evidence

- Release targets `combat_transition_runtime_probe` and `one_combat` built.
- Focused CTest selection `ooc_mcts_adapter|combat_transition_runtime_loader`:
  2/2 passed.
- Exporter and parity verifier Python compilation passed; `git diff --check`
  passed.
- Independent implementation review found no remaining design defect after
  requiring V2, non-experimental current-standard fallback metadata and exact
  source/cohort identities.
- The user-requested 64-pair OOC screen is pending. Its canonical seeds are
  `980000..980063`, but the run must wait for a reviewed commit SHA to be
  frozen under the repository's worktree Git-metadata workflow. Consequently
  win/loss, search-cost, fallback-frequency, and paired-discordance claims are
  all open.
- Full repository CI was not run. No live-game test or default promotion was
  performed.

Raw machine-readable outputs are `parity.json`, `mechanism.jsonl`,
`mechanism-summary.json`, and `fixed-fixture-benchmark-release.json`.
