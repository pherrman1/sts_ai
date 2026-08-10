# Issues

Last verified: 2026-08-10 against the current working tree.

This directory collects known issues extracted from the knowledge-base pages,
sorted by importance. Each entry records the symptom, evidence, why it matters,
and a candidate fix direction; nothing here is a decision or a completed
diagnosis. Entries are closed by a fixing commit or test, not by editing
history. Experiments invalidated by a fix are tracked in the
[rerun ledger](../evaluation/rerun-ledger.md).

## Importance tiers

- **Critical** — silently invalidates measurements, results, or model behavior.
- **High** — blocks operation, progress, or an experiment's validity.
- **Medium** — tooling or evidence gaps that waste effort or mislead readers.
- **Low** — debt and design questions without an immediate functional impact.

## Index

Sorted by importance; entry files are reverse-chronological in their own list.

| ID | Tier | Title | Status | Source pages |
| --- | --- | --- | --- | --- |
| [01](2026-08-02-issue-01-meta-arm-bypass.md) | Critical | Self-play meta arm bypasses its candidate models | closed | [selfplay-loop](../operations/selfplay-loop.md) |
| [02](2026-08-02-issue-02-no-current-benchmark.md) | Critical | No fresh benchmark on the current checkout | closed | [current-baselines](../evaluation/current-baselines.md) |
| [03](2026-08-02-issue-03-searcher3-composite-seeding.md) | Critical | Searcher3 composite seeding uses unassigned values | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [04](2026-08-02-issue-04-belief-conditioning-noop.md) | Critical | Searcher3 belief conditioning is a no-op | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [05](2026-08-02-issue-05-drawpile-order-ignored.md) | Critical | `HiddenBattleState::drawPileOrder` is never applied | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [06](2026-08-02-issue-06-pvnet-only-priors-zero.md) | Critical | PVNet-only multi-edge priors are zero | closed | [combat-search](../architecture/combat-search.md), [current-baselines](../evaluation/current-baselines.md) |
| [07](2026-08-02-issue-07-observation-identity-mismatch.md) | Critical | `CombatObservation` equality and hash disagree | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [08](2026-08-02-issue-08-ooc-checkpoint-truncated-load.md) | Critical | `OocCheckpointNet::load` reports success on truncated payloads | closed | [out-of-combat](../architecture/out-of-combat.md), [invariants](../behavior/invariants.md) |
| [09](2026-08-02-issue-09-paired-analysis-column-drift.md) | Critical | `paired_analysis.py` reads the wrong HP/time columns | closed | [benchmark-protocol](../evaluation/benchmark-protocol.md), [invariants](../behavior/invariants.md) |
| [10](2026-08-02-issue-10-fair-replay-nondeterminism.md) | Critical | Fair multi-thread replay is not bit-identical; no test | closed | [determinism-and-rng](../behavior/determinism-and-rng.md), [benchmark-protocol](../evaluation/benchmark-protocol.md) |
| [31](2026-08-05-issue-31-probe-cpsi-normalization.md) | Critical | `probe_cpsi.py` feeds C_psi raw scalars + sigmoided quantiles | closed | [ooc-strategic-v4](../architecture/ooc-strategic-v4.md), [ooc-continuation-contracts](../architecture/ooc-continuation-contracts.md) |
| [32](2026-08-05-issue-32-pvnet-untrained-heads.md) | Critical | PVNet `turns`/`potion` heads untrained but exported | closed | [combat-search](../architecture/combat-search.md), [training-and-inference](../architecture/training-and-inference.md) |
| [33](2026-08-05-issue-33-vwin-calibration-split-leak.md) | Critical | `fit_vwin_calibration.py` isotonic fit leaks the validation split | closed | [ooc-qwin-continuation](../architecture/ooc-qwin-continuation.md) |
| [34](2026-08-05-issue-34-searcher3-encode-buffer-overflow.md) | Critical | Searcher3 `computeEdgePriors` heap overflow for `entityDim` != 128 | closed | [combat-search](../architecture/combat-search.md) |
| [47](2026-08-05-issue-47-cardselect-enumeration-gaps.md) | Critical | CARD_SELECT legal-action enumeration gaps in S2/S3/canonical | closed | [combat-search](../architecture/combat-search.md) |
| [11](2026-08-02-issue-11-selfplay-snapshot-nonrunnable.md) | High | Checked-in self-play snapshot cannot run | closed | [selfplay-loop](../operations/selfplay-loop.md) |
| [12](2026-08-02-issue-12-clean-clone-configure-fails.md) | High | Clean clone cannot configure (json/pybind11 absent) | closed | [build-and-debugging](../operations/build-and-debugging.md) |
| [13](2026-08-02-issue-13-baseline-cache-provenance.md) | High | Baseline cache key omits fixed native trees | closed | [selfplay-loop](../operations/selfplay-loop.md), [determinism-and-rng](../behavior/determinism-and-rng.md) |
| [14](2026-08-02-issue-14-value-margin-misapplied.md) | High | `VALUE_MARGIN=-0.5` applies to every value candidate | closed | [selfplay-loop](../operations/selfplay-loop.md), [invariants](../behavior/invariants.md) |
| [15](2026-08-02-issue-15-gate-multiplicity.md) | High | Repeated gate looks are not multiplicity-adjusted | closed | [selfplay-loop](../operations/selfplay-loop.md), [benchmark-protocol](../evaluation/benchmark-protocol.md) |
| [16](2026-08-02-issue-16-pvnet-sweep-provenance.md) | High | PVNet sweep provenance is unverified | open | [current-baselines](../evaluation/current-baselines.md) |
| [17](2026-08-02-issue-17-guaranteed-death-pruning-unproven.md) | High | Aggressive guaranteed-death pruning is unproven | closed | [combat-search](../architecture/combat-search.md) |
| [35](2026-08-05-issue-35-state-bin-byte-size-reuse.md) | High | `_state.bin` reuse keyed on byte size only | closed | [ooc-strategic-v4](../architecture/ooc-strategic-v4.md), [training-and-inference](../architecture/training-and-inference.md) |
| [36](2026-08-05-issue-36-tok-glob-stats-columns.md) | High | Token-state glob 44–49 stats from wrong CSV columns | closed | [ooc-strategic-v4](../architecture/ooc-strategic-v4.md) |
| [37](2026-08-05-issue-37-pvnet-token-layout-mismatch.md) | High | PVNet dead-monster token layout differs train vs inference | closed | [combat-search](../architecture/combat-search.md), [training-and-inference](../architecture/training-and-inference.md) |
| [38](2026-08-05-issue-38-tok-exporter-config-flags.md) | High | `export_strategic_tok` ignores non-default config flags | closed | [ooc-strategic-v4](../architecture/ooc-strategic-v4.md) |
| [39](2026-08-05-issue-39-dist-val-split-unused.md) | High | `train_combat_dist` validation split never used | closed | [training-and-inference](../architecture/training-and-inference.md) |
| [40](2026-08-05-issue-40-checker-map-encoder.md) | High | `check_vwin_calibration` has no map-encoder support | closed | [ooc-map-route-contracts](../architecture/ooc-map-route-contracts.md) |
| [41](2026-08-05-issue-41-s3live-ablation-noop.md) | High | `g_s3Live=0` ablation arm measured nothing | closed | [combat-search](../architecture/combat-search.md) |
| [42](2026-08-05-issue-42-crn-rewarm-tree-reuse.md) | High | CRN warm start destructively re-warms the tree-reuse path | closed | [combat-search](../architecture/combat-search.md) |
| [48](2026-08-05-issue-48-multiselect-subset-regression.md) | High | Multi-select full-subset enumeration "regresses" win rate at fixed budgets — actually a **control S3 battle-skip exploit** (§113); no multi-select regression; fixed enumerator + `exitBattle` UNDECIDED guard deployed | closed | [combat-search](../architecture/combat-search.md), [decision-log `2026-08-05-cardselect-parity-fix.md`](../decision-log/2026-08-05-cardselect-parity-fix.md) |
| [49](2026-08-05-issue-49-term-win-mt-crash.md) | Medium | `STS_TERM_WIN=1` terminal-leaf bonus segfaults ~2/6 at 12 threads (0 output lines; 1-thread and ASAN clean; repro on Phase-1 too — pre-existing). Opt-in only; TERM_WIN stays off; needs a debugger session | open | [combat-search](../architecture/combat-search.md), [decision-log `2026-08-05-phase3-terminal-value-stage2.md`](../decision-log/2026-08-05-phase3-terminal-value-stage2.md) |
| [50](2026-08-09-issue-actionqueue-overflow.md) | High | ActionQueue capacity-50 overflow crashes long-running datagen/benchmarks under fair-S3+vnet | closed | [combat-search](../architecture/combat-search.md) |
| [51](2026-08-09-issue-cardqueue-silent-overflow.md) | High | CardQueue capacity-10 overflow silently corrupts under NDEBUG (assert not guarded by `sts_asserts`) | closed | [combat-search](../architecture/combat-search.md) |
| [50](2026-08-10-issue-50-thorns-retaliation-flips-win.md) | High | Lethal Thorns retaliation after the killing blow flips win to loss | closed | [invariants](../behavior/invariants.md), [decision-log `2026-08-10-thorns-retaliation-and-awakened-one-outcome-fix.md`](../decision-log/2026-08-10-thorns-retaliation-and-awakened-one-outcome-fix.md) |
| [51](2026-08-10-issue-51-awakened-one-premature-victory.md) | High | Awakened One stage 1 death with both Cultists grants premature victory (stage 2 skipped) | closed | [invariants](../behavior/invariants.md), [decision-log `2026-08-10-thorns-retaliation-and-awakened-one-outcome-fix.md`](../decision-log/2026-08-10-thorns-retaliation-and-awakened-one-outcome-fix.md) |
| [53](2026-08-10-issue-53-fairy-bark-revive-wrong-hp.md) | High | Sacred Bark + Fairy in a Bottle revives at 1 HP instead of 60% max HP (ternary precedence) | closed | [decision-log `2026-08-10-fix-53-63-64.md`](../decision-log/2026-08-10-fix-53-63-64.md) |
| [63](2026-08-10-issue-63-toke-peace-pipe-noop.md) | Medium | TOKE (Peace Pipe) removes nothing: screen closed before any pick | closed | [decision-log `2026-08-10-fix-53-63-64.md`](../decision-log/2026-08-10-fix-53-63-64.md) |
| [64](2026-08-10-issue-64-cf-branch-rng-pollution.md) | Medium | Event-fight `regainControlAction` lambdas consume the original context's RNG when a CF branch inherits them | closed | [decision-log `2026-08-10-fix-53-63-64.md`](../decision-log/2026-08-10-fix-53-63-64.md) |
| [55](2026-08-10-issue-55-s3-leaf-cache-stale-obs.md) | High | Searcher3 depth-cap leaf cache serves wrong-world values | closed | [combat-search](../architecture/combat-search.md), [decision-log `2026-08-10-issue-55-58-71-fixes.md`](../decision-log/2026-08-10-issue-55-58-71-fixes.md) |
| [58](2026-08-10-issue-58-s3-belief-collapse.md) | Medium | Searcher3 belief collapse admitted "broken" and default ON | closed | [combat-search](../architecture/combat-search.md), [determinism-and-rng](../behavior/determinism-and-rng.md), [decision-log `2026-08-10-issue-55-58-71-fixes.md`](../decision-log/2026-08-10-issue-55-58-71-fixes.md) |
| [71](2026-08-10-issue-71-s3-puct-pvnet-value-only.md) | Low | Searcher3 PUCT gate missing `!g_pvnetValueOnly` | closed | [combat-search](../architecture/combat-search.md), [decision-log `2026-08-10-issue-55-58-71-fixes.md`](../decision-log/2026-08-10-issue-55-58-71-fixes.md) |
| [68](2026-08-10-issue-68-multiselect-stale-validation.md) | Low | Multi-select EXHAUST_MANY/GAMBLE masks validate with a stale task outside CARD_SELECT | closed | [decision-log `2026-08-10-issue-68-fix.md`](../decision-log/2026-08-10-issue-68-fix.md) |
| [54](2026-08-10-issue-54-s2-convroot-hang.md) | High | Searcher2 `searchToTotalRootStable` infinite loop on zero-growth config | closed | [combat-search](../architecture/combat-search.md), [decision-log `2026-08-10-issue-54-70-s2-fixes.md`](../decision-log/2026-08-10-issue-54-70-s2-fixes.md) |
| [70](2026-08-10-issue-70-s2-stale-outcome-rexpand.md) | Low | Searcher2 stale `outcome` on fair-mode re-expansion breaks `outcome != 0 → edges.empty()` | closed | [combat-search](../architecture/combat-search.md), [decision-log `2026-08-10-issue-54-70-s2-fixes.md`](../decision-log/2026-08-10-issue-54-70-s2-fixes.md) |
| [76](2026-08-10-issue-76-pvnet-silent-cpu.md) | Low | `train_combat_pvnet.py` silently falls back to CPU with no `device:` line | closed | [training-and-inference](../architecture/training-and-inference.md), [decision-log `2026-08-10-issue-76-81-fixes.md`](../decision-log/2026-08-10-issue-76-81-fixes.md) |
| [81](2026-08-10-issue-81-vserver-unlocked-predict.md) | Low | v_server `decide_nn` calls `WIN_BOOSTER.predict` outside the global `LOCK` | closed | [out-of-combat](../architecture/out-of-combat.md), [decision-log `2026-08-10-issue-76-81-fixes.md`](../decision-log/2026-08-10-issue-76-81-fixes.md) |
| [82](2026-08-10-issue-82-loop-gate-server-dependency.md) | Low | Value/policy gates start v_server even though they are native-OOC (`STS_NATIVE_OOC=1`) | closed | [selfplay-loop](../operations/selfplay-loop.md), [decision-log `2026-08-10-issue-82-fix.md`](../decision-log/2026-08-10-issue-82-fix.md) |
| [65](2026-08-10-issue-65-shopv-event-removal.md) | Medium | Shop-V intercepts event/Neow/relic removals (REMOVE select not shop-scoped) | closed | [out-of-combat](../architecture/out-of-combat.md), [decision-log `2026-08-10-issue-65-73-74-75-83-fixes.md`](../decision-log/2026-08-10-issue-65-73-74-75-83-fixes.md) |
| [73](2026-08-10-issue-73-winnettest-duplicate.md) | Low | Second `winnettest` mode branch unreachable (dead full-run parity check) | closed | [decision-log `2026-08-10-issue-65-73-74-75-83-fixes.md`](../decision-log/2026-08-10-issue-65-73-74-75-83-fixes.md) |
| [74](2026-08-10-issue-74-datagen-fair-override.md) | Low | `datagen` silently overrides `STS_FAIR` with its positional arg | closed | [decision-log `2026-08-10-issue-65-73-74-75-83-fixes.md`](../decision-log/2026-08-10-issue-65-73-74-75-83-fixes.md) |
| [75](2026-08-10-issue-75-sts-win-net-silent-failure.md) | Low | `STS_WIN_NET` load failure silent (return value ignored) | closed | [decision-log `2026-08-10-issue-65-73-74-75-83-fixes.md`](../decision-log/2026-08-10-issue-65-73-74-75-83-fixes.md) |
| [83](2026-08-10-issue-83-datagen-pre-map-share.md) | Low | Datagen `pre` snapshot shares map pointer with live run | closed | [decision-log `2026-08-10-issue-65-73-74-75-83-fixes.md`](../decision-log/2026-08-10-issue-65-73-74-75-83-fixes.md) |
| [67](2026-08-10-issue-67-potion-slots-invalid.md) | Low | Default potion slots INVALID instead of EMPTY | closed | [decision-log `2026-08-10-issue-67-72-84-fixes.md`](../decision-log/2026-08-10-issue-67-72-84-fixes.md) |
| [72](2026-08-10-issue-72-reuse-always-q-dead.md) | Low | `STS_REUSE_ALWAYS_Q` dead code (counter never incremented) | closed | [combat-search](../architecture/combat-search.md), [decision-log `2026-08-10-issue-67-72-84-fixes.md`](../decision-log/2026-08-10-issue-67-72-84-fixes.md) |
| [84](2026-08-10-issue-84-anycardbottled-inverted.md) | Low | `Deck::anyCardBottled` logic inverted | closed | [decision-log `2026-08-10-issue-67-72-84-fixes.md`](../decision-log/2026-08-10-issue-67-72-84-fixes.md) |
| [18](2026-08-02-issue-18-bestbench-banner-stale.md) | Medium | `bestBench` banner/comment describe an older stack | closed | [out-of-combat](../architecture/out-of-combat.md), [benchmark-protocol](../evaluation/benchmark-protocol.md) |
| [19](2026-08-02-issue-19-parity-test-invalid.md) | Medium | `parity_test.py` cannot run as written | closed | [build-and-debugging](../operations/build-and-debugging.md), [training-and-inference](../architecture/training-and-inference.md) |
| [20](2026-08-02-issue-20-runtrace-divergence.md) | Medium | `runtrace` is not a mirror of `runFullRunOOC` | closed | [out-of-combat](../architecture/out-of-combat.md), [build-and-debugging](../operations/build-and-debugging.md) |
| [21](2026-08-02-issue-21-v-server-stale-comments.md) | Medium | `v_server.py` comments describe an old layout | closed | [out-of-combat](../architecture/out-of-combat.md), [training-and-inference](../architecture/training-and-inference.md) |
| [22](2026-08-02-issue-22-no-automated-invariant-tests.md) | Medium | No automated invariant/test suite exists | closed | [invariants](../behavior/invariants.md), [overview](../architecture/overview.md) |
| [23](2026-08-02-issue-23-fairgen-name-misleading.md) | Medium | `fairgen` does not enable the fair path itself | closed | [training-and-inference](../architecture/training-and-inference.md) |
| [24](2026-08-02-issue-24-isbattleover-trap.md) | Medium | `isBattleOver` is never set true | closed | [invariants](../behavior/invariants.md) |
| [25](2026-08-02-issue-25-blas-hardcoded-path.md) | Medium | Native inference probes a hard-coded OpenBLAS path | closed | [combat-search](../architecture/combat-search.md), [build-and-debugging](../operations/build-and-debugging.md) |
| [43](2026-08-05-issue-43-pvnet-s3-doc-staleness.md) | Medium | `STS_PVNET`/`STS_S3_*` documentation stale or absent | closed | [combat-search](../architecture/combat-search.md), [AGENTS.md](../../../AGENTS.md) |
| [44](2026-08-05-issue-44-tok-pipeline-hygiene.md) | Medium | Token-pipeline hygiene: dead gather, GELU mismatch, NaN-loss zeroing | open | [ooc-strategic-v4](../architecture/ooc-strategic-v4.md) |
| [45](2026-08-05-issue-45-eval-train-hygiene-batch.md) | Low | Eval/train hygiene batch: stale defaults, import safety, misc | open | [training-and-inference](../architecture/training-and-inference.md) |
| [46](2026-08-05-issue-46-bestbench-append-dedup.md) | Medium | `bestbench` appends without dedup — scripts must truncate | open | [benchmark-protocol](../evaluation/benchmark-protocol.md) |
| [26](2026-08-02-issue-26-one-combat-centralization.md) | Low | `one_combat.cpp` centralizes policy and experiments | open | [overview](../architecture/overview.md), [out-of-combat](../architecture/out-of-combat.md) |
| [27](2026-08-02-issue-27-python-deps-unpinned.md) | Low | No dependency lock for Python packages | open | [training-and-inference](../architecture/training-and-inference.md), [build-and-debugging](../operations/build-and-debugging.md) |
| [28](2026-08-02-issue-28-expert-hand-authored-features.md) | Low | Policy input includes hand-authored Expert features | closed | [combat-search](../architecture/combat-search.md) |
| [29](2026-08-02-issue-29-python-combat-bindings.md) | Low | Python cannot issue card-by-card combat actions | open | [out-of-combat](../architecture/out-of-combat.md), [overview](../architecture/overview.md) |
| [30](2026-08-02-issue-30-selfplay-bootstrap-policy.md) | Low | Self-play bootstrap policy for stale `state.env` is undefined | closed | [selfplay-loop](../operations/selfplay-loop.md) |

## Conventions

- An entry's status changes to `closed` with a note of the fixing commit or
  test. Do not rewrite the entry's evidence.
- When a candidate investigation in
  [`investigations/`](../investigations/README.md) is promoted to a completed
  diagnosis, link it from the relevant issue entry.
- New issues found in the knowledge base are appended to the index and get a
  new entry file dated with the day they were recorded.
