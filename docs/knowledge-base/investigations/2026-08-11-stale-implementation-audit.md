# Stale implementation audit — 2026-08-11

**Investigation type:** Stale/dead code audit (Phase 6 — read-only)

**Investigator:** OpenCode Build agent (deepseek-v4-pro)

---

## Scope / baseline

- **Baseline SHA:** `28cbbdc12211bb3aa10cb9ed6ee8001d39b13fcb`
- **Working tree clean at start:** yes (`git status --short` empty)
- **Directories audited:** `apps/`, `src/`, `include/`, `bindings/`
- **Excluded:** `json/`, `pybind11/`, third-party, model artifacts, generated build files, `.ai/`, archived docs

---

## Method

1. Read all architecture and research knowledge-base pages to establish current research status.
2. Traced reachability from `apps/one_combat.cpp::main` — the active integration driver — through all CLI modes, env-flag gates, and model-loading paths.
3. Verified search-agent dispatch in `ScumSearchAgent2::playoutBattle` / `playoutBattleFair`.
4. Checked each combat-model class against its runtime callers in Searcher2 or Searcher3.
5. Grepped for symbol/class/flag names in all `.cpp`, `.h`, `.sh`, `.py` files outside `build/`.
6. Compared CTest-registered tests against `apps/test.cpp` subcommands.
7. Distinguished: current default, opt-in, diagnostic, closed-experiment, park-research, falsified-superseded, genuinely-disconnected.

---

## Important live-code findings

Things that look stale but are actually live/supported:

| Candidate | Why it looked stale | Evidence it is still live |
| --- | --- | --- |
| **Searcher2** | All current research concentrates on Searcher3 | Default searcher (no `STS_SEARCHER3` = Searcher2); paired gates at §99, §118–119, §120–121; `searchdiag` instrumentation; `STS_ROLLOUT_CAPS` operates on S2; fair-path forced-move skip runs in both S2 and S3; forced-isolated non-fair path |
| **SimpleAgent** | Basic heuristic agent; no mention in current research | Used as fallback OOC policy (`ScumSearchAgent2::stepOutOfCombatPolicy`), map-path helper (`SimpleAgent::getBestMapPathForWeights`), key-collection test, `small-test.cpp`; called by `bindings/slaythespire.cpp` |
| **ConsoleSimulator / BattleSimulator** | Looks like interactive-play code from upstream | `apps/main.cpp::main` uses it; `bindings/slaythespire.cpp` exposes it via `m.def("play", …)`; `bindings/bindings-util.cpp` calls it; currently linked into `slaythespire` pybind11 module |
| **ExpertKnowledge** | Hand-authored heuristics, dated | Enumerated in code map as "play/obtain weights, encoded as policy features"; policy net features `combatFillActionFeatures` reference it; current prior uses these features |
| **CombatCpsiNet** | "C_psi" name suggests one-off experiment | Loaded via `STS_CPSI_NN`; consumed by `oocMapRoute` (M2), `simAdapt`, `termWin` evaluator (cpsi mode), `cpsictr` probe mode; active in multiple experimental OOC paths |
| **CombatDistValueNet** | Experimental-only, not default | Loaded via `STS_DIST_VNET`; consumed only by Searcher3; has a runtime dispatch path in `BattleScumSearcher3.cpp` (`evaluateLeaf` + `evaluateLeafDirect`) that fires when the flag is set; `parity_test` executable exists for it |
| **CombatPVNet** | Phase 1 gate negative (§102), A–H stopped | `STS_PVNET` is still a real load path; provides policy priors to Searcher2 (since 2026-08-05) AND value leaf to Searcher3; `STS_PVNET_VALUE_ONLY` makes it inert under S2; `STS_PVNET_CACHE` is default ON; `pvnetparity` mode exists for parity |
| **SimpleAgent::stepRestScreen** | Was in test for key collection | Active in key-collection fallback path; test `keys_collect` registers `SimpleAgent::stepRestScreen` in CTest |
| **OocCheckpointNet** | Old-appearing checkpoint net | Loaded via `STS_OOC_CHECKPOINT_NN`; opt-in but deliberately supported as an NN policy layer before ordinary policy layers |
| **OocStrategicNet (V2/V3)** | V4 token net is recommended | V3 remains the deployed strategic-net fallback when `STS_OOC_STRATEGIC_NN` is loaded but `STS_OOC_STRATEGIC_TOK_NN` is not; V3 gates are still referenced by historical baselines (§99, §82) |
| **apps/small-test.cpp** | Looks legacy | Executable is still built; exercises map-path + card-order invariants; links bindings-util; small enough not to matter |

---

## Candidate table

### Search-agent implementations

| Candidate | Locations | Runtime entry | Scientific status | Tests | Classification |
| --- | --- | --- | --- | --- | --- |
| **BattleScumSearcher2** | `src/sim/search/BattleScumSearcher2.cpp` (~56 KB) | Default searcher via `ScumSearchAgent2::playoutBattle` | Current deployment | `scum_nonfair_empty_edges`, `scum_convroot_stale_outcome` (CTest) | CURRENT |
| **BattleScumSearcher3** | `src/sim/search/BattleScumSearcher3.cpp` (~157 KB) | `STS_SEARCHER3=1` via `ScumSearchAgent2::playoutBattleFair` | Standard fair-play combat searcher | No direct CTest; tested via gate blocks | SUPPORTED_OPTIONAL |
| **ScumSearchAgent2** | `src/sim/search/ScumSearchAgent2.cpp` (~49 KB) | Both searchers dispatch through it | Current deployment | Implicitly tested via all combat tests | CURRENT |
| **SimpleAgent** | `src/sim/search/SimpleAgent.cpp` (~38 KB) | Fallback OOC policy, map helper, key collection | Deployed fallback in multiple paths | `keys_collect` (CTest), `small-test` | SUPPORTED_OPTIONAL |
| **ExpertKnowledge** | `src/sim/search/ExpertKnowledge.cpp` | Policy net features | Current policy feature source | None directly | CURRENT |

### Combat model runtime implementations

| Candidate | Locations | Runtime entry | Scientific status | Tests | Classification |
| --- | --- | --- | --- | --- | --- |
| **CombatValueNet** | `src/sim/search/CombatValueNet.cpp` (~56 KB) | Default in fair-S3 path (§148 model); `STS_VNET` overrides | Current deployment | `vnettest` (CTest), `parity_test.py` (CTest compile) | CURRENT |
| **CombatPVNet** | `src/sim/search/CombatPVNet.cpp` (~18 KB) | `STS_PVNET=<path>` | Closed (Phase 1 gate negative), but the loader and leaf eval are still active code paths | `pvnetparity` mode exists | SUPPORTED_OPTIONAL |
| **CombatDistValueNet** | `src/sim/search/CombatDistValueNet.cpp` (~11 KB) | `STS_DIST_VNET=<path>`, S3 only | Experimental; no gate promoted | `parity_test` executable exists | SUPPORTED_OPTIONAL |
| **CombatCpsiNet** | `src/sim/search/CombatCpsiNet.cpp` (~14 KB) | `STS_CPSI_NN=<path>` | Experimental; used by multiple OOC paths | None directly | SUPPORTED_OPTIONAL |

### OOC net loaders

| Candidate | Locations | Runtime entry | Scientific status | Tests | Classification |
| --- | --- | --- | --- | --- | --- |
| **OocCheckpointNet** | `apps/ooc_checkpoint_net.h` (166 lines) | `STS_OOC_CHECKPOINT_NN=<path>` | Opt-in; NN policy before ordinary layers | None directly | SUPPORTED_OPTIONAL |
| **OocStrategicNet (V2/V3)** | `apps/ooc_strategic_net.h` (684 lines) | `STS_OOC_STRATEGIC_NN=<path>` | V3 is the deployed fallback; V2 is historical | `mapnntest` mode for V6 map path | SUPPORTED_OPTIONAL |
| **OocStrategicTokNet (V4)** | `apps/ooc_strategic_tok_net.h` (479 lines) | `STS_OOC_STRATEGIC_TOK_NN=<path>` | Recommended opt-in since §75 | `STS_OOC_STRATEGIC_TOK_CHECK` parity hook | SUPPORTED_OPTIONAL |

### Executable entrypoints

| Candidate | Locations | Current callers | Status | Classification |
| --- | --- | --- | --- | --- |
| **apps/main.cpp** | `apps/main.cpp` (29 lines) | Interactive play; `bindings/slaythespire.cpp::def("play")` | Upstream interactive console game; part of the pybind11 module contract | SUPPORTED_OPTIONAL |
| **apps/parity_test.cpp** | `apps/parity_test.cpp` (57 lines) | `parity_test.py` (Python harness, CTest compile-checked) | DistVNet parity checker; narrow scope | SUPPORTED_OPTIONAL |
| **apps/small-test.cpp** | `apps/small-test.cpp` (224 lines) | No CTest entry; standalone | Map-path + card-order invariants; small | SUPPORTED_OPTIONAL |
| **apps/test.cpp** | `apps/test.cpp` (2557 lines) | `ctest` registers 13 subcommands | Main C++ test dispatcher | CURRENT |

---

## HIGH-confidence cleanup candidates

Based on direct static evidence (no meaningful current callers, no active research, no current baseline, no current test not owned by the candidate itself, default-off), the following are the strongest candidates for safe removal.

### CANDIDATE H1 — Server-dependent benchmark modes

**Cluster:** `restbench`, `shopbench`, `allbench`, `skipbench`

**Files/symbols involved:** `apps/one_combat.cpp` mode dispatch, plus the `restBench`, `shopBench`, `allOOCBench`, `skipBench`, and `oocBench` function implementations

**Evidence:**
- All four modes require `v_server.py` running (documented in their mode dispatch comments).
- Native OOC is the default since 2026-08; `v_server.py` is not required for the default `bestbench` stack.
- No caller found in `*.sh` or `*.py` outside the execution definition itself.
- `bestbench` has been the uniform baseline mode for all recent experiments (§68, §99, §113, §124, §126, §148, §153).
- These modes compare legacy server-dependent policies against server-free heuristics — a comparison that no current research needs.
- No CTest entry exercises these modes.

**Scientific status:** Historical comparison tools, superseded when native OOC became default.

**Confidence:** HIGH

**Cleanup value:** MEDIUM (removes 4 modes + their function implementations, reduces server dependency footprint).

**Deletion risk:** LOW — `bestbench` and `runFullRunOOC` do not depend on these modes' functions.

**Verification cost:** LOW — `bestbench` 8-seed smoke suffices.

**Classification:** DEAD_HIGH_CONFIDENCE

**Status:** REMOVED — Batch 1 implemented in Phase 6 (`refactor: remove obsolete server benchmark modes`, 2026-08-12). All four modes, their dispatch branches, and their dedicated wrappers (`restBench`, `shopBench`, `allOOCBench`, `skipBench`, and the `oocBench` helper used only by `restBench`/`shopBench`) were deleted. Historical evidence is preserved here and in `docs/experiments/ledger-01.md`.

---

### CANDIDATE H2 — Legacy `bench` mode and `runBenchmark` function

**Files/symbols involved:** `apps/one_combat.cpp` lines 10790–10794 (`bench` mode), `benchmark()` function, `runBenchmark()` function

**Evidence:**
- The `bench` mode (lines 10790–10794) runs a `benchmark(sims, nSeeds)` without ascension or seed offset.
- `bestbench` (line 11665) is the canonical mode with ascension, seed offset, and `runFullRunOOC`.
- All recent benchmarks (§68–§153) use `bestbench`.
- `runBenchmark()` (line 10832) is a separate function used by `runbench` mode (different from `bench`); neither appears in any shell/Python script.
- Differences between `bench`/`benchmark`/`runBenchmark`/`bestbench` are unclear; the existence of four benchmark entry points without distinguishing caller documentation is strong dead-code evidence.

**Scientific status:** Superseded by `bestbench` as the uniform benchmark mode.

**Confidence:** HIGH

**Cleanup value:** LOW (minimal line removal).

**Deletion risk:** LOW — verify that `benchmark()` and `runBenchmark()` share no code with `bestBench()`.

**Verification cost:** LOW — `bestbench` 8-seed smoke.

**Classification:** DEAD_HIGH_CONFIDENCE

---

### CANDIDATE H3 — `cardbench`, `combobench`, `pathbench`, `draftbench` modes

**Files/symbols involved:** `apps/one_combat.cpp` lines 11614–11635 (mode dispatch + implementations)

**Evidence:**
- `cardbench` — weighted table vs greedy argmax drafting.
- `combobench` — baseline vs greedy draft + heuristic path.
- `pathbench` — random path vs heuristic path.
- `draftbench` — weighted table vs lookahead drafting.
- None appear in any `*.sh` or `*.py` caller.
- The comparisons they make are historical — current baselines use `bestbench` with the `runFullRunOOC` policy chain.
- No CTest entries.

**Scientific status:** Historical A/B probes from early policy development; superseded by `bestbench` + gate experiments.

**Confidence:** HIGH

**Cleanup value:** LOW (small functions).

**Deletion risk:** LOW.

**Verification cost:** LOW.

**Classification:** DEAD_HIGH_CONFIDENCE

---

### CANDIDATE H4 — `datagen` mode (original simple state-outcome CSV)

**Files/symbols involved:** `apps/one_combat.cpp` lines 10846–10861 (mode dispatch), `dataGen()` function

**Evidence:**
- Labeled "CSV of (state features, run outcome) for offline V(state)".
- Scientifically superseded by `datagen2` (rich per-decision state) and `datagen3` (rich + paired counterfactuals).
- The `datagen` mode has a positional `STS_FAIR` override argument (arg position 7) — a dated mechanism; all modern modes use env flags.
- **Retained caller:** `tools/run/datagen_loop.sh` line 19 directly invokes `./one_combat.elf datagen "$BLOCK" "$SIMS" "$ASC" "$EPS" "$OUT" 0 "$OFF"` for bulk datagen collection.
- `datagen2` is also still used by `tools/run/datagen2_loop.sh`; `datagen3` by selfplay scripts.

**Scientific status:** Superseded theoretically by richer datagen modes, but the retained `tools/run/datagen_loop.sh` script still invokes it for production datagen. This script must be deliberately retired before the mode can be deleted.

**Confidence:** HIGH

**Cleanup value:** LOW.

**Deletion risk:** MEDIUM — deleting the mode would break `tools/run/datagen_loop.sh`. Deletion requires a separate decision to retire the script or migrate it to a newer datagen mode.

**Classification:** SUPERSEDED_CONNECTED

---

### CANDIDATE H5 — `mcts` and `random` modes (single-combat tests)

**Files/symbols involved:** `apps/one_combat.cpp` lines 10811–10823

**Evidence:**
- `mcts` — single combat with MCTS policy.
- `random` — single combat with random policy.
- These are simple test harnesses; no caller in the repository outside `one_combat.cpp` itself.
- The combat search is tested through full-run modes (`bestbench`, `searchdiag`); single-combat testing is done through Python replay scripts (`check_replay.py` which calls `bestbench`).
- No documentation references these modes.

**Scientific status:** Ad-hoc debugging tools; not part of any maintained test suite.

**Confidence:** HIGH

**Cleanup value:** LOW.

**Deletion risk:** LOW.

**Verification cost:** LOW.

**Classification:** DEAD_HIGH_CONFIDENCE

---

### CANDIDATE H6 — `causalgen` mode

**Files/symbols involved:** `apps/one_combat.cpp` lines 11589–11598, `causalGen()` function

**Evidence:**
- Labeled "CSV of (state, card features, CRN advantage) for causal card value."
- **Historical consumer:** a root Ridge-regression trainer consumed this CSV,
  but the trainer emitted an unused `adv_model.txt` rather than the
  `card_adv_table.txt` artifact read by the runtime. It was removed by the
  2026-09-07 root-script audit.
- The causal card-value line predates the strategic Q-gate approach; no current knowledge-base docs reference it.

**Scientific status:** Historical experiment with a retained trainer consumer in the repository. The trainer itself may be obsolete, but verifying that requires a separate audit.

**Confidence:** MEDIUM (caller exists but may itself be dead).

**Classification:** SUPERSEDED_CONNECTED

---

### CANDIDATE H7 — `carddump` and `deck` modes

**Files/symbols involved:** `apps/one_combat.cpp` lines 11599–11614

**Evidence:**
- `carddump` — dump all card properties (id/name/type/rarity/obtainWeight/baseDamage).
- `deck` — dump final deck+relics of one run.
- Both are one-off debugging tools with no callers in scripts or tests.
- Card property information is available through the game code directly.

**Scientific status:** Diagnostic only; not used by any current workflow.

**Confidence:** HIGH

**Cleanup value:** LOW.

**Deletion risk:** LOW.

**Verification cost:** LOW.

**Classification:** DEAD_HIGH_CONFIDENCE

---

### CANDIDATE H8 — S3 outcome-bucket and leafvalue diagnostics

**Cluster:** `STS_S3_OUTCOME_BUCKET_DIAG`, `STS_S3_OUTCOME_BUCKET_DIAG_FILE`, `STS_S3_OUTCOME_BUCKET_DIAG_PARTICLES`, `STS_S3_BUCKET_VALUE_DIAG`, `STS_S3_BUCKET_VALUE_DIAG_FILE`, `STS_S3_BUCKET_VALUE_DIAG_ROLLOUTS`, `STS_S3_LEAFVALUE_DIAG`, `STS_S3_LEAFVALUE_DIAG_FILE`, `STS_S3_DRAW_PROB_DIAG`, `STS_S3_DRAW_PROB_DIAG_FILE`

**Files/symbols involved:** `apps/one_combat.cpp` lines 10320–10371 (flag parsing); `include/sim/search/BattleScumSearcher3.h` (global flags); `src/sim/search/BattleScumSearcher3.cpp` (diagnostic instrumentation)

**Evidence:**
- These flags control CSV-file diagnostic logging from inside Searcher3.
- All default off. All are write-only diagnostic CSV producers — none alter search selection, tree structure, belief state, or backpropagation.
- Each flag family has a dedicated decision-log entry (2026-08-09): `outcome-bucket-diag.md`, `bucket-value-diag.md`, `draw-prob-diag.md`, `leafvalue-residual-diag.md`, and `s3-belief-vs-root-audit.md` (2026-08-10 for `ROOT_RACE_DIAG`).
- The `BUCKET_VALUE_DIAG` and `OUTCOME_BUCKET_DIAG` were used to study outcome redundancy and value homogeneity, which informed the END_TURN marginalization prototype but remain independently useful diagnostics.
- The `LEAFVALUE_DIAG` fires auxiliary reference searchers (`searchToTotal`) to establish deep referent values — these are separate searcher objects that do not alter the main search tree.
- The maintained diagnostic modes (`leafdiag`, `leafref`, `rollouttrace`, `frontiergen`, `leafrelabel`) address different diagnostic questions (leaf-state ranking, rollout smoothness, frontier relabeling) — they do not directly supersede these per-transition/per-bucket outcome diagnostics.

**Scientific status:** Purpose-built diagnostic tools documented in decision logs; each flag captures a specific diagnostic measurement not replicated by the structured leaf-diagnostic modes. They are ad-hoc (flag-activation rather than a mode), but they are not "superseded" — they measure different phenomena.

**Confidence:** MEDIUM — each flag requires a deliberate retirement decision based on whether the diagnostic question it answers is still of interest.

**Classification:** SUPPORTED_OPTIONAL — diagnostic infrastructure with decision-log provenance. Deletion should be a separate per-flag decision, not bundled into a bulk cleanup.

**Deletion risk in a future cleanup:** MEDIUM — need to confirm each flag's CSV output is not consumed by any current analysis tool.

---

### CANDIDATE H9 — `STS_S3_ENDTURN_MARGINALIZE*` flags

**Cluster:** `STS_S3_ENDTURN_MARGINALIZE`, `STS_S3_ENDTURN_MARGINALIZE_PARTICLES`, `STS_S3_ENDTURN_MARGINALIZE_MAX_PILE`

**Files/symbols involved:** `apps/one_combat.cpp` lines 10344–10355; `include/sim/search/BattleScumSearcher3.h` lines 486–491; `src/sim/search/BattleScumSearcher3.cpp` lines 99–105, 1795–1798, 2662–2676, 3281 (endTurnMarginalEval)

**Evidence:**
- **Behavior-changing:** This is NOT write-only diagnostic instrumentation. When enabled, Searcher3 samples particles at END_TURN boundaries, buckets by visibleHash, evaluates one representative per bucket via the full multi-rollout + leaf blend path, computes a weighted marginal expectation, and backpropagates that alternative evaluation. It bypasses the ordinary chain/rollout/blend path when marginalization succeeds.
- Decision log: `2026-08-09-endturn-marginalization.md`. Verdict: **STOP** — marginalization adds ~56% search CPU with no clear quality benefit at equal CPU. The prototype works correctly but the cost outweighs the variance reduction.
- The decision log explicitly lists possible future uses: training target generation, root-only tactical calculation, offline leaf-value relabeling.
- The code is not dead — it is a stopped prototype retained for possible reuse in non-MCTS contexts.

**Scientific status:** STOPped prototype (2026-08-09). The mechanism is correct; the cost/benefit in MCTS was unfavorable. Retained for potential future use in training targets or offline relabeling.

**Confidence:** HIGH

**Classification:** REPRO_ONLY — a stopped experiment whose implementation remains for future investigation or offline applications. Should NOT be included in any HIGH-confidence deletion batch.

---

### CANDIDATE H10 — `STS_REUSE_*` diagnostic flags

**Cluster:** `STS_REUSE_CPU_DIAG`, `STS_REUSE_CPU_DIAG_FILE`, `STS_REUSE_CARRY_DIAG`

**Evidence:**
- Default off.
- Tree reuse diagnostics; the non-fair reuse path is not the current research direction.
- No active caller in scripts.

**Scientific status:** Diagnostic from the reuse investigation; parked.

**Confidence:** MEDIUM — `STS_REUSE_CARRY_DIAG` may still be useful for understanding reuse behavior; these are write-only diagnostics.

**Classification:** SUPERSEDED_CONNECTED (connected to tree reuse machinery that is still in the codebase; removing these diagnostic flags is possible but low priority).

---

## FALSE POSITIVES — things that are NOT dead

| Candidate | Why it looked stale | Evidence it is still live |
| --- | --- | --- |
| Searcher2 | All current research focuses on Searcher3 | Default searcher; `STS_SEARCHER3` is opt-in; `searchdiag` instruments both; multiple experimental flags operate on S2 (`STS_ROLLOUT_CAPS`, `STS_CONV_ROOT`, `STS_FORCED_MOVE` in non-fair path); `STS_PVNET` provides policy priors to S2 |
| `ConsoleSimulator` / `BattleSimulator` / `SimHelpers` / `PrintHelpers` | Interactive-play code from upstream | `apps/main.cpp` uses them; `bindings/slaythespire.cpp` exposes `ConsoleSimulator` via `m.def("play")`; `bindings/bindings-util.cpp` calls `BattleSimulator`; `SimHelpers` resolves string-to-ID lookups used by `BattleSimulator` and test infrastructure |
| `SimpleAgent` | Basic heuristic; no current research mention | Used as fallback OOC, map-path helper, key-collection test; `bindings` exposes it via `ScumSearchAgent2::playout`; removing it would break the pybind11 module contract |
| `CombatPVNet` | Phase 1 gate negative (§102) | `STS_PVNET` is still a real load path providing policy priors to S2 since 2026-08-05; `STS_PVNET_VALUE_ONLY` makes it inert under S2 when desired; `pvnetparity` mode is maintained |
| `CombatDistValueNet` | Experimental-only | Has a real runtime dispatch path in `BattleScumSearcher3::evaluateLeaf` / `::evaluateLeafDirect`; `parity_test` executable exists for it |
| `CombatCpsiNet` | "C_psi" name suggests one-off | Consumed by 4+ distinct runtime paths: `oocMapRoute` (M2), `simAdapt`, `termWin` (cpsi evaluator), `cpsictr` probe mode |
| `OocStrategicNet` (V2/V3) | V4 token net is recommended | V3 remains the deployed fallback when only `STS_OOC_STRATEGIC_NN` is loaded; V3 gates are referenced by historical baselines §99, §82; the V3 Q head and value heads are still a supported opt-in |
| `OocCheckpointNet` | Looks like early NN experiment | Loaded via `STS_OOC_CHECKPOINT_NN`, opt-in but deliberately supported as an NN policy layer before ordinary policy layers; acts 1–3 only |
| `apps/test.cpp` `scum_searcher` subcommand | Not CTest-registered | The subcommand dispatcher exists but the body is commented out (`// playRandom4(startSeedLong)`); effectively dead code within a live test file |
| `apps/parity_test.cpp` executable | Narrow scope, no CTest | Used by `parity_test.py` (CTest compile-checked via `py_compile_parity_test`); serves the distributional-model parity check |
| Flag `STS_CONV_ROOT` | Falsified at §118 gate | The flag remains opt-in and the implementation is isolated; removal candidate but low priority — S2-level code that shares no mutable state with S3 paths when off |
| Flag `STS_ROLLOUT_CAPS` | Falsified at §119 gate | Same pattern as `STS_CONV_ROOT`; isolated S2 code, default-off, byte-identical when unset |
| Flag `STS_OOC_STRATEGIC_SCORE=policy` (Phase F) | Falsified at §104 | The policy-score gate path is isolated behind the `g_oocStrategicScorePolicy` flag; never fires when the env is unset; removing it would simplify the gate decision code but it is not "stale" in the sense of unreachable — it's an opt-in superseded experiment |
| Flag `STS_OOC_STRATEGIC_GATE=regret` | Wave B falsified at §100 (MAP gate) | The regret gate mechanism is still implemented and could be reused; it's a parked comparison lever, not dead code |
| Map-DAG encoder (V6) in `OocStrategicNet` | Falsified §100 | The `mapnntest` parity mode still exists; the encoder code is loaded but never called unless V6 artifact + MAP gate path fires; removal would simplify the OocStrategicNet loader |
| `STS_VNET_COND_BOSS` / `STS_VNET_COND_ACT3` | Not a current default | VNet conditioning flags parsed in `apps/one_combat.cpp` but the conditioned-predict path in CombatValueNet is not merged; these flags are load-only (parsed, echoed, stored); no code actually reads them at predict time — **this is a dead flag** |
| `STS_SIM_ADAPT` | Requires `STS_CPSI_NN` | Active experimental OOC path; the C_psi adaptive-sims lever is functional code |
| `STS_ACT_FIGHT_PROBE_*` flags | Oracle/checkpoint probe experiments | The all-OOC checkpoint rollouts (§111) were falsified; the whole `actFightProbe*` family is a large block of code containing oracle/teacher/checkpointer machinery that has no current active use |
| `STS_ACT_FIGHT_PROBE_PREDICT*` + entity transition predictor | Part of the checkpoint probe | The `CombatEntityNet` load path inside the checkpoint oracle; requires a `combat_entity_v1` artifact; the checkpoint oracle was falsified at §111 |

---

## Feature-flag inventory

All meaningful experimental `STS_*` flags found in `apps/one_combat.cpp` main() and `src/sim/search/Action.cpp`.

### CURRENT (in use by default deployment)

| Flag | Default | Location | Scientific status | Classification |
| --- | --- | --- | --- | --- |
| `STS_NATIVE_OOC` | ON (1) | `apps/one_combat.cpp:10033` | Current default; native floor/win trees | CURRENT |
| `STS_SKIP_THR` | −0.5 | `apps/one_combat.cpp:10250` | Current card-reward skip threshold | CURRENT |
| `STS_COLLECT_KEYS` | OFF (0) | `apps/one_combat.cpp:9786` | Act-4 key collection; default-off but tested (`keys_collect`) | CURRENT |
| `STS_POLICY` | Auto-load `models/policy_trees_c.txt` | `apps/one_combat.cpp:10768` | Deployed GBM policy prior | CURRENT |
| `STS_CPUCT` | — | `apps/one_combat.cpp:10786` | c_puct parameter for policy-guided PUCT | CURRENT |
| `STS_STOP_AFTER_ACT` | 0 (no stop) | `apps/one_combat.cpp:10237` | Benchmark horizon control | CURRENT |

### SUPPORTED_OPTIONAL

| Flag | Default | Location | Scientific status | Classification |
| --- | --- | --- | --- | --- |
| `STS_SEARCHER3` | OFF (0) | `apps/one_combat.cpp:10268` | Standard fair-play S3 searcher | SUPPORTED_OPTIONAL |
| `STS_FAIR` | OFF (0) | `apps/one_combat.cpp:10264` | Project-fair determinized combat | SUPPORTED_OPTIONAL |
| `STS_LIVE_VALID` | ON in fair-S3, off otherwise | `apps/one_combat.cpp:10280` | Fair-tree structural fix; promoted §122–123 | SUPPORTED_OPTIONAL |
| `STS_FORCED_MOVE` | ON (1) | `apps/one_combat.cpp:9807` | Forced-action contraction; promoted §120–121 | SUPPORTED_OPTIONAL |
| `STS_S3_BELIEF` | OFF (0) | `apps/one_combat.cpp:10448` | S3 particle belief; recommended OFF (§124) | SUPPORTED_OPTIONAL |
| `STS_S3_CHAIN` | OFF (0) | `apps/one_combat.cpp:10490` | S3 chain compression; recommended OFF (§106) | SUPPORTED_OPTIONAL |
| `STS_S3_PRUNE` | ON (1) | `apps/one_combat.cpp:10486` | S3 dead-branch pruning; per-seed no-op | SUPPORTED_OPTIONAL |
| `STS_S3_LIVE` | ON (1) | `apps/one_combat.cpp:10494` | S3 live-valid root-edge filter | SUPPORTED_OPTIONAL |
| `STS_S3_CRN` | OFF (0) | `apps/one_combat.cpp:10498` | S3 root CRN warm-start; harmful §106 | SUPPORTED_OPTIONAL |
| `STS_S3_PARTICLES` | 64 | `apps/one_combat.cpp:10502` | S3 belief particle count | SUPPORTED_OPTIONAL |
| `STS_VNET` | Auto-load in fair-S3 | `apps/one_combat.cpp:10561` | Deployed V_combat leaf (§148 model) | SUPPORTED_OPTIONAL |
| `STS_VNET_ALPHA` | 0.3 | `apps/one_combat.cpp:10565` | VNet blend alpha | SUPPORTED_OPTIONAL |
| `STS_PVNET` | OFF | `apps/one_combat.cpp:10731` | PV policy-value network | SUPPORTED_OPTIONAL |
| `STS_PVNET_ALPHA` | 0.3 | `apps/one_combat.cpp:10742` | PVNet blend alpha | SUPPORTED_OPTIONAL |
| `STS_PVNET_VALUE_ONLY` | OFF | `apps/one_combat.cpp:10743` | PVNet value-only (inert under S2) | SUPPORTED_OPTIONAL |
| `STS_PVNET_CACHE` | ON (1) | `apps/one_combat.cpp:10750` | PVNet leaf-value cache | SUPPORTED_OPTIONAL |
| `STS_PVNET_COND_{TURN,DEPTH,BOSS}` | — | `apps/one_combat.cpp:10751` | PVNet conditional gating | SUPPORTED_OPTIONAL |
| `STS_DIST_VNET` | OFF | `apps/one_combat.cpp:10721` | Distributional V_combat (S3 only) | SUPPORTED_OPTIONAL |
| `STS_CPSI_NN` | OFF | `apps/one_combat.cpp:9930` | C_psi combat outcome surrogate | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_TOK_NN` | OFF | `apps/one_combat.cpp:9865` | V4 token-net one-ply Q gates | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_NN` | OFF | `apps/one_combat.cpp:9859` | V3 strategic-net one-ply Q gates | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_{REST,EVENT,SHOP,TREASURE,BOSS_RELIC}` | OFF | `apps/one_combat.cpp:9887` | Per-screen Q gate enables | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_MARGIN` | 1.0 | `apps/one_combat.cpp:9954` | Global Q-gate margin | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_Q` | ON (1) | `apps/one_combat.cpp:9882` | Q-head vs V2 successor-value scoring | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_TOK_CHECK` | OFF | `apps/one_combat.cpp:9872` | V4 first-decision glob parity | SUPPORTED_OPTIONAL |
| `STS_OOC_CHECKPOINT_NN` | OFF | `apps/one_combat.cpp:9853` | Checkpoint NN policy | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_TRACE` | OFF | `apps/one_combat.cpp:9877` | OOC decision trace CSV | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_GATE` | margin | `apps/one_combat.cpp:9992` | Regret-gate mode (Wave B) | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_SCORE` | q | `apps/one_combat.cpp:9957` | Policy-score gate (Phase F) | SUPPORTED_OPTIONAL |
| `STS_OOC_MAP_ROUTE` | OFF | `apps/one_combat.cpp:9922` | M2 C_psi route search | SUPPORTED_OPTIONAL |
| `STS_OOC_STRATEGIC_MAP` | OFF | `apps/one_combat.cpp:9917` | M1 map route Q gate | SUPPORTED_OPTIONAL |
| `STS_OOC_SHOP_BEAM` | OFF | `apps/one_combat.cpp:9941` | B1 shop beam search | SUPPORTED_OPTIONAL |
| `STS_TERM_WIN` | OFF | `apps/one_combat.cpp:10432` | Terminal-leaf run-value bonus | SUPPORTED_OPTIONAL |
| `STS_TERM_STALL_LOG` | OFF | `apps/one_combat.cpp:10428` | Per-combat stall telemetry | SUPPORTED_OPTIONAL |
| `STS_FORCE_RELIC` | OFF | `apps/one_combat.cpp:10416` | Forced-relic benchmark A/B | SUPPORTED_OPTIONAL |
| `STS_RISK_LAMBDA` | — | `apps/one_combat.cpp:10557` | Risk sensitivity for S3 PUCT | SUPPORTED_OPTIONAL |
| `STS_SIM_ADAPT` | OFF | `apps/one_combat.cpp:10101` | C_psi adaptive per-fight sim budget | SUPPORTED_OPTIONAL |
| `STS_SIMS_{NORMAL,ELITE,BOSS}` | — | `apps/one_combat.cpp:10095` | Tiered per-fight sim budgets | SUPPORTED_OPTIONAL |
| `STS_DG_TEMP` | 2.0 | `apps/one_combat.cpp:10260` | Datagen softmax temperature | SUPPORTED_OPTIONAL |
| `STS_REST_WIN` | OFF | `apps/one_combat.cpp:9827` | Win-rate rest policy | SUPPORTED_OPTIONAL |
| `STS_REST_V_THRESH` | — | `apps/one_combat.cpp:9823` | Rest heal-gain threshold | SUPPORTED_OPTIONAL |
| `STS_ROLLOUT_DEPTH` | OFF | `apps/one_combat.cpp:9791` | Flat rollout depth cap | SUPPORTED_OPTIONAL |
| `STS_MULTISELECT_MODE` | all | `src/sim/search/Action.cpp:511` | Multi-select action-space pruning | SUPPORTED_OPTIONAL |
| `STS_MULTISELECT_CANONICAL` | OFF (0) | `src/sim/search/Action.cpp:524` | Multi-select mask canonicalization | SUPPORTED_OPTIONAL |
| `STS_TURN_PENALTY` | OFF | `apps/one_combat.cpp:9815` | Leaf turn penalty | SUPPORTED_OPTIONAL |
| `STS_TT` | OFF | `apps/one_combat.cpp:9819` | Transposition table | SUPPORTED_OPTIONAL |
| `STS_WIN_NET` | Auto-load | `apps/one_combat.cpp:10028` | Native WinNet override | SUPPORTED_OPTIONAL |
| `STS_VNET_PER_ENCOUNTER` | OFF | `apps/one_combat.cpp:10610` | Per-encounter vnet specialization | SUPPORTED_OPTIONAL |
| `STS_VNET_RANK_CORR` | OFF | `apps/one_combat.cpp:10642` | Zero-mean ranking correction | SUPPORTED_OPTIONAL |
| `STS_VNET_RESIDUAL` | OFF | `apps/one_combat.cpp:10657` | Residual vnet correction | SUPPORTED_OPTIONAL |
| `STS_VNET_QUERY_LOG` | OFF | `apps/one_combat.cpp:10688` | VNet query distribution log | SUPPORTED_OPTIONAL |
| `STS_VNET_ALPHA_LEN` | OFF | `apps/one_combat.cpp:10457` | Dynamic alpha by rollout length | SUPPORTED_OPTIONAL |
| `STS_S3_EXPAND` | OFF | `apps/one_combat.cpp:10509` | No-valid-edge expansion (falsified §125) | SUPPORTED_OPTIONAL |
| `STS_S3_EXPAND_MAX` | 32 | `apps/one_combat.cpp:10513` | Expansion edge cap | SUPPORTED_OPTIONAL |
| `STS_S3_EXPAND_SIMPLE` | OFF | `apps/one_combat.cpp:10517` | No-PUCT edge expansion | SUPPORTED_OPTIONAL |
| `STS_S3_ROLLOUT_POLICY` | OFF | `apps/one_combat.cpp:10521` | Prior-guided rollouts (falsified §124c) | SUPPORTED_OPTIONAL |
| `STS_S3_ROLLOUT_K` | 1 | `apps/one_combat.cpp:10525` | K-rollouts per leaf (null §133) | SUPPORTED_OPTIONAL |
| `STS_S3_ROLLOUT_TURN_STOP` | 0 | `apps/one_combat.cpp:10532` | Turn-stop rollout (falsified §133) | SUPPORTED_OPTIONAL |
| `STS_S3_TURN_ROLLOUT` | OFF | `apps/one_combat.cpp:10539` | Turn-beam rollout (null §135b) | SUPPORTED_OPTIONAL |
| `STS_S3_POOL_REDIRECT` | OFF | `apps/one_combat.cpp:10452` | Forced-move budget redirect (§143) | SUPPORTED_OPTIONAL |
| `STS_S3_INTERNAL_BELIEF_UPDATE` | OFF (0) | `apps/one_combat.cpp:10384` | Internal belief update (harmful) | SUPPORTED_OPTIONAL |
| `STS_S3_REAL_BELIEF_FILTER` | OFF | `apps/one_combat.cpp:10376` | Real-observation belief filter | SUPPORTED_OPTIONAL |
| `STS_S3_REAL_BELIEF_COLLAPSE_FRESH` | OFF | `apps/one_combat.cpp:10380` | Collapse-fresh fallback | SUPPORTED_OPTIONAL |
| `STS_S3_SEMANTIC_CARD_EDGES` | OFF | `apps/one_combat.cpp:10316` | Semantic card edges (tested) | SUPPORTED_OPTIONAL |
| `STS_REUSE_MAX_SEARCHES` | 1 | `apps/one_combat.cpp:10285` | Max carried searches per fresh tree (0 = fresh only); promoted to default in fair-S3 path per `decisions/s3-obs-stable-reuse-promotion.md` | SUPPORTED_OPTIONAL |
| `STS_REUSE_STATS_MODE` | keep (0) | `apps/one_combat.cpp:10289` | Subtree statistics handling (keep vs recursive_reset); `keep` is the promoted default | SUPPORTED_OPTIONAL |
| `STS_REUSE_ALWAYS_Q` | OFF (false) | `apps/one_combat.cpp:10296` | Force Q exploitation from carried tree (catastrophic in gates; default off) | SUPPORTED_OPTIONAL |
| `STS_REUSE_OBS_STABLE` | ON (true) | `apps/one_combat.cpp:10304` | Obs-stable one-step tree reuse; promoted to default in fair-S3 path since 2026-08-09 | SUPPORTED_OPTIONAL |
| `STS_REUSE_RECONCILE_ROOT` | OFF (false) | `apps/one_combat.cpp:10308` | Experimental root reconciliation (not enabled) | SUPPORTED_OPTIONAL |
| `STS_S3_UNION_EXPAND` | OFF (false) | `apps/one_combat.cpp:10404` | At every internal-node visit, add missing legal edges and track availability; changes tree structure and edge enumeration. Part of the S3 reuse architecture; listed in the promoted default configuration table as experimental/not-enabled | SUPPORTED_OPTIONAL |
| `STS_S3_BELIEF_AUDIT` | OFF | `apps/one_combat.cpp:10372` | Belief audit CSV logging; diagnostic companion to the real-belief-filter research | DIAGNOSTIC |

### FALSIFIED / CLOSED (opt-in, default-off, retained as reproducibility/ablation levers)

| Flag | Default | Location | Scientific status | Classification |
| --- | --- | --- | --- | --- |
| `STS_CONV_ROOT` | OFF | `apps/one_combat.cpp:10117` | Root-stability adaptive search; falsified §118 | REPRO_ONLY |
| `STS_ROLLOUT_CAPS` | OFF | `apps/one_combat.cpp:9795` | Context-adaptive rollout caps; falsified §119 | REPRO_ONLY |
| `STS_CONVERGE` | OFF | `apps/one_combat.cpp:10109` | Convergence-based early stopping; superseded by `STS_CONV_ROOT` | REPRO_ONLY |
| `STS_ACT_FIGHT_PROBE_ALL_OOC` | OFF | `apps/one_combat.cpp:10214` | All-OOC checkpoint oracle; falsified §111 | REPRO_ONLY |
| `STS_ACT_FIGHT_PROBE_MARGIN` | 0 | `apps/one_combat.cpp:10196` | Oracle margin gate; falsified §111 | REPRO_ONLY |
| `STS_ACT_FIGHT_PROBE_TERM_WIN` | 0 | `apps/one_combat.cpp:10189` | Terminal-win pricing; falsified §111 | REPRO_ONLY |

### DIAGNOSTIC-ONLY (not gameplay, not research)

| Flag | Default | Location | Scientific status | Classification |
| --- | --- | --- | --- | --- |
| `STS_DIAG_VNET2` | OFF | `apps/one_combat.cpp:10670` | Secondary diagnostic vnet (leafdiag/leafref only) | SUPPORTED_OPTIONAL |
| `STS_DIAG_VNET2_ALPHA` | OFF | `apps/one_combat.cpp:10681` | Reporting-only blend | SUPPORTED_OPTIONAL |
| `STS_LEAFDIAG_PER_STRATUM` | 50 | `apps/one_combat.cpp:10709` | Leafdiag reservoir capacity | SUPPORTED_OPTIONAL |
| `STS_LEAFDIAG_DEEP_DEPTH` | 20 | `apps/one_combat.cpp:10713` | Leafdiag deep-tree threshold | SUPPORTED_OPTIONAL |
| `STS_FRONTIERGEN_PER_STRATUM` | 200 | `apps/one_combat.cpp:10717` | Frontiergen reservoir capacity | SUPPORTED_OPTIONAL |

### LEGACY / SERVER-DEPENDENT (connected to legacy v_server paths)

| Flag | Default | Location | Scientific status | Classification |
| --- | --- | --- | --- | --- |
| `STS_CARD_NN` | OFF | `apps/one_combat.cpp:9836` | Card picks via deck-set NN (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_CARD_ACTION` | OFF | `apps/one_combat.cpp:9844` | Direct paired card/skip action NN (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_OOC_ACTION_NN` | OFF | `apps/one_combat.cpp:9848` | OOC via next-combat action NN (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_BOSS_RELIC` | OFF | `apps/one_combat.cpp:10020` | Boss relic pick via V_win (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_NEOW_V` | OFF | `apps/one_combat.cpp:10024` | Neow via V_win (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_VPATH` | OFF | `apps/one_combat.cpp:10254` | V-strength path modulation (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_BOSS_V` | OFF | `apps/one_combat.cpp:10242` | Boss-survival V blend (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_PATH_V` | OFF | `apps/one_combat.cpp:10052` | Model-driven pathing via V_win (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_PATH_GRAPH` | OFF | `apps/one_combat.cpp:10056` | Full-map graph NN pathing | SUPERSEDED_CONNECTED |
| `STS_PATH_ACTION` | OFF | `apps/one_combat.cpp:10063` | Paired route-action NN | SUPERSEDED_CONNECTED |
| `STS_EVENT_V` | OFF | `apps/one_combat.cpp:10077` | Model-driven events via V_win | SUPERSEDED_CONNECTED |
| `STS_POTION_SAVE` | OFF | `apps/one_combat.cpp:10081` | Dynamic potion-saving (needs v_server) | SUPERSEDED_CONNECTED |
| `STS_SHOP_WIN` | OFF | `apps/one_combat.cpp:10091` | Shop scored via WIN model | SUPERSEDED_CONNECTED |
| `STS_BOSS_DRAFT` | OFF | `apps/one_combat.cpp:10140` | Boss-gated rollout drafting | SUPERSEDED_CONNECTED |
| `STS_ACT_FIGHT_PROBE_DRAFT` | OFF | `apps/one_combat.cpp:10151` | All-act encounter rollout draft | SUPERSEDED_CONNECTED |
| `STS_DATAGEN_GATES` | OFF | `apps/one_combat.cpp:9892` | Datagen OOC through gate stack (§127) | SUPERSEDED_CONNECTED |
| `STS_REFIGHT_FLOOR` / `STS_REFIGHT_N` / `STS_COMBAT_LOG` | OFF | `apps/one_combat.cpp:3065` | Diagnostic refight/combat-log probes | SUPERSEDED_CONNECTED |

### DEAD / UNUSED FLAGS (parsed but no runtime behavior; HIGH-confidence cleanup candidates)

| Flag | Default | Location | Status | Classification |
| --- | --- | --- | --- | --- |
| `STS_VNET_COND_BOSS` | OFF | `apps/one_combat.cpp:10568` | Load-only flag; parsed and stored but no code reads it at predict time — the CombatValueNet predict path does not check `g_vnetCondBossOnly` | DEAD_HIGH_CONFIDENCE |
| `STS_VNET_COND_ACT3` | OFF | `apps/one_combat.cpp:10569` | Same as above — load-only, no runtime effect | DEAD_HIGH_CONFIDENCE |

### UNKNOWN (requires further investigation before classification)

| Flag | Default | Location | Status | Classification |
| --- | --- | --- | --- | --- |
| `STS_COMBAT_WIN_BONUS` | OFF | `apps/one_combat.cpp:10566` | Load-only flag; `setWinBonus()` is called but the VNet's win-bonus field may not be used in the current predict path (end-HP target, not utility-R) — need to verify | UNKNOWN |

### DIAGNOSTIC-ONLY FLAGS (write-only CSV logging; not gameplay/search behavior changes)

All of these flags have decision-log documentation from 2026-08-09/10 and are write-only CSV producers. They do not alter the search tree, belief state, selection, or backpropagation. Each should be retired via a deliberate per-flag decision, not bulk cleanup.

| Flag | Default | Location | Scientific status | Classification |
| --- | --- | --- | --- | --- |
| `STS_S3_OUTCOME_BUCKET_DIAG*` | OFF | `apps/one_combat.cpp:10320` | Decision log `2026-08-09-outcome-bucket-diag.md`; measures outcome distribution per END_TURN transition | SUPPORTED_OPTIONAL |
| `STS_S3_BUCKET_VALUE_DIAG*` | OFF | `apps/one_combat.cpp:10332` | Decision log `2026-08-09-bucket-value-diag.md`; measures continuation value per bucket | SUPPORTED_OPTIONAL |
| `STS_S3_DRAW_PROB_DIAG*` | OFF | `apps/one_combat.cpp:10356` | Decision log `2026-08-09-draw-prob-diag.md`; computes exact hypergeometric draw probabilities | SUPPORTED_OPTIONAL |
| `STS_S3_LEAFVALUE_DIAG*` | OFF | `apps/one_combat.cpp:10364` | Decision log `2026-08-09-leafvalue-residual-diag.md`; runs reference searchers to establish deep referent values (auxiliary searchers, does not alter main search tree) | SUPPORTED_OPTIONAL |
| `STS_S3_ROOT_RACE_DIAG*` | OFF | `apps/one_combat.cpp:10392` | Decision log `2026-08-10-s3-belief-vs-root-audit.md`; writes per-root-action probe rows | SUPPORTED_OPTIONAL |
| `STS_S3_BELIEF_AUDIT*` | OFF | `apps/one_combat.cpp:10372` | Belief audit CSV logging; diagnostic companion to the parked real-belief-filter research | SUPPORTED_OPTIONAL |
| `STS_REUSE_CPU_DIAG*` | OFF | `apps/one_combat.cpp:10408` | Tree-reuse CPU diagnostic; parked diagnostic from reuse investigation | SUPERSEDED_CONNECTED |
| `STS_REUSE_CARRY_DIAG` | OFF | `apps/one_combat.cpp:10312` | Similar to above; parked diagnostic | SUPERSEDED_CONNECTED |
| `STS_REUSE_DIAG` | OFF | `apps/one_combat.cpp:10300` | General tree-reuse diagnostics | SUPERSEDED_CONNECTED |

### BEHAVIOR-CHANGING EXPERIMENTAL FLAGS (NOT diagnostic-only; not recommended for bulk cleanup)

| Flag | Default | Location | Scientific status | Classification |
| --- | --- | --- | --- | --- |
| `STS_S3_ENDTURN_MARGINALIZE*` | OFF | `apps/one_combat.cpp:10344` | STOPped prototype (2026-08-09 decision log). Changes search behavior: samples particles, buckets outcomes, backpropagates weighted marginal instead of ordinary rollout/blend. Retained for potential offline/training applications. | REPRO_ONLY |
| `STS_S3_UNION_EXPAND` | OFF | `apps/one_combat.cpp:10404` | Experimental feature in S3 reuse architecture. At every internal-node visit, adds missing legal edges and tracks availability. Listed as experimental/not-enabled in the promoted default configuration (`decisions/s3-obs-stable-reuse-promotion.md`). Changes tree structure and edge enumeration — not write-only. | SUPPORTED_OPTIONAL |

---

## One-combat mode inventory

| Mode | Purpose | Current caller | Scientific status | Classification |
| --- | --- | --- | --- | --- |
| `bestbench` | Current best OOC stack whole-run benchmark | `tools/run/run_mapgate_ab.sh`, `tools/run/run_distgate_ab.sh`, `tools/verify/check_replay.py` | Current baseline mode | CURRENT |
| `strategicmarggen` | Encounter-marginalization M0/M1 datagen | Active research handoff | Active research | CURRENT |
| `searchdiag` | Rollout-usage diagnostics | Decision log 2026-08-06 | Current diagnostic | SUPPORTED_OPTIONAL |
| `leafdiag` | S3 leaf-state diagnostic dataset | Handover 2026-08-08 | Current diagnostic | SUPPORTED_OPTIONAL |
| `leafref` | High-budget reference values | Handover 2026-08-08 | Current diagnostic | SUPPORTED_OPTIONAL |
| `rollouttrace` | Rollout state sequences | Handover 2026-08-08 | Current diagnostic | SUPPORTED_OPTIONAL |
| `frontiergen` | S3 frontier-leaf corpus | Phases 2-3 plan | Current diagnostic | SUPPORTED_OPTIONAL |
| `leafrelabel` | Terminal-outcome relabeling | Phases 2-3 plan | Current diagnostic | SUPPORTED_OPTIONAL |
| `strategicgen` | Phase 5 one-row-per-OOC-decision | Strategic training pipeline | Current datagen | SUPPORTED_OPTIONAL |
| `strategicgen2` | Tier-B per-action one-ply labels | V4 training pipeline | Current datagen | SUPPORTED_OPTIONAL |
| `fairgen` | S3 ISMCTS value+policy rows | Policy training pipeline | Current datagen | SUPPORTED_OPTIONAL |
| `combatgen` | Combat state+fight outcome CSV | VNet training pipeline | Current datagen | SUPPORTED_OPTIONAL |
| `fightgen` | Combined value+policy datagen | VNet+policy training | Current datagen | SUPPORTED_OPTIONAL |
| `vnettest` | Asserting C++ vs Python VNet parity | `tools/verify/vnettest_selftest.py` (CTest) | Current parity | SUPPORTED_OPTIONAL |
| `winnettest` | C++ vs Python WinNet parity | `tools/verify/winnettest_selftest.py` (CTest) | Current parity | SUPPORTED_OPTIONAL |
| `pvnetparity` | C++ vs Python PVNet parity | Manual parity check | Current parity | SUPPORTED_OPTIONAL |
| `policynettest` | Entity policy logits parity | Manual parity check | Parity | SUPPORTED_OPTIONAL |
| `speedtest` | S3 single-fight speed measurement | Manual diagnostic | Speed measurement | SUPPORTED_OPTIONAL |
| `policystats` | Offline prior quality | Manual analysis | Prior quality check | REPRO_ONLY |
| `datagen2` | Rich per-decision state+outcome | `tools/run/datagen2_loop.sh` | Older datagen, still used | SUPPORTED_OPTIONAL |
| `datagen3` | Rich + paired rest/card CF | `selfplay/run_card_cf_collection.sh` | Older datagen, still used | SUPPORTED_OPTIONAL |
| `policygen` | State/action/visit MCTS policy targets | `train_policy.py` comment | Policy training | SUPPORTED_OPTIONAL |
| `mapbatch` | Full-map graph table | `train_strategic.py`, `train_card_cf.py` | Map data | SUPPORTED_OPTIONAL |
| `dumpmap` | Dump seed's map graph | Manual diagnostic | Map inspection | SUPPORTED_OPTIONAL |
| `mapnntest` | V6 map-DAG parity | Manual parity check | V6 falsified; parity check remains for V6 artifact | REPRO_ONLY |
| `distgen` | Distributional labels | DistVNet training | Experimental training | SUPPORTED_OPTIONAL |
| `oocnextgen` | All legal OOC actions, next-combat labels | No current caller found | Older OOC datagen | REPRO_ONLY |
| `pathcfgen` | Paired route decision per run | No current caller found | Historical CF datagen | REPRO_ONLY |
| `cpsictr` | C_psi counter-sensitivity probe | Manual diagnostic | C_psi probe | SUPPORTED_OPTIONAL |
| `reprobench` | Repeat one run, audit determinism | Manual diagnostic | Determinism audit | SUPPORTED_OPTIONAL |
| `runtrace` | Per-node human-readable trace | Manual diagnostic | Trace inspection | SUPPORTED_OPTIONAL |
| `run` | One whole run verbose | Manual quick-check | Convenience | SUPPORTED_OPTIONAL |
| `runbench` | Many whole runs | No current caller found | Historical benchmark variant | DEAD_HIGH_CONFIDENCE |
| `bench` | Basic benchmark | No current caller found | Superseded by `bestbench` | DEAD_HIGH_CONFIDENCE |
| `mcts` | Single combat MCTS | No current caller found | Ad-hoc test | DEAD_HIGH_CONFIDENCE |
| `random` | Single combat random | No current caller found | Ad-hoc test | DEAD_HIGH_CONFIDENCE |
| `datagen` | Original simple state-outcome CSV for offline V(state) | `tools/run/datagen_loop.sh` (directly invokes with seed offset) | Superseded by datagen2/datagen3 but retained caller exists | SUPERSEDED_CONNECTED |
| `draftbench` | Weighted table vs lookahead drafting | No current caller found | Historical A/B | DEAD_HIGH_CONFIDENCE |
| `cardbench` | Card drafting A/B | No current caller found | Historical A/B | DEAD_HIGH_CONFIDENCE |
| `combobench` | Baseline vs greedy draft+heuristic path | No current caller found | Historical A/B | DEAD_HIGH_CONFIDENCE |
| `pathbench` | Random path vs heuristic path | No current caller found | Historical A/B | DEAD_HIGH_CONFIDENCE |
| `restbench` | Default rest vs value policy (needs v_server) | No current caller found | Historical A/B, server-dependent | REMOVED (Batch 1) |
| `shopbench` | Default shop vs V-knapsack (needs v_server) | No current caller found | Historical A/B, server-dependent | REMOVED (Batch 1) |
| `allbench` | All-default vs rest-V+shop-V (needs v_server) | No current caller found | Historical A/B, server-dependent | REMOVED (Batch 1) |
| `skipbench` | Card-skip sweep (needs v_server) | No current caller found | Historical sweep, server-dependent | REMOVED (Batch 1) |
| `causalgen` | CRN advantage for causal card value | No current script consumer; runtime still has the separately produced causal-card table path | Historical experiment; producer mode outside this audit | SUPERSEDED_DISCONNECTED |
| `carddump` | Dump card properties | No current caller found | One-off debug tool | DEAD_HIGH_CONFIDENCE |
| `deck` | Dump final deck+relics | No current caller found | One-off debug tool | DEAD_HIGH_CONFIDENCE |

---

## Recommended cleanup sequence

Ordered by cleanup value / deletion risk / verification cost, each batch changes one conceptual thing.

### Batch 1 — Server-dependent benchmark modes (HIGH confidence, low risk)

**Concept:** Remove `restbench`, `shopbench`, `allbench`, `skipbench` modes and their function implementations from `apps/one_combat.cpp`.

**Why first:** These four modes require `v_server.py`, have zero callers, and represent historical policy comparisons that `bestbench` + gate experiments superseded. Removing them:
- Simplifies the mode dispatch and `BEST stack` banner.
- Does not touch any current path.
- Verification is limited to the current executable path and does not establish
  a policy-quality benchmark result.

**Files changed:** `apps/one_combat.cpp` and `tools/seed_guard.sh`.

**Implementation verification:**
- Static diff/reachability check: **PASS**. The Batch 1 diff is one clean commit
  with 97 deletions and zero additions in `apps/one_combat.cpp`; only the four
  removed mode entries disappear from `tools/seed_guard.sh`. Current `fightrep`
  handling and `MAX_AUTOMATED_SEEDS=128` remain present.
- `cmake --build build -j --target one_combat`: **PASS** (existing narrowing
  conversion warnings remain).
- `wsl -e bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai && bash tools/seed_guard.sh ./build/one_combat bestbench 100 1 0"`:
  **INCOMPLETE**. The one-seed/100-simulation current-path smoke started, but
  did not finish within two minutes and the exact `one_combat` child was
  terminated. It produced no completed `BEST` result.

**Broader verification limitations:**
- `ctest --test-dir build --output-on-failure`: **23/26 passed**. The failures
  were `selfplay_syntax` (WSL CRLF parsing at `selfplay/loop.sh:136`),
  `paired_analysis_selftest` (WSL Python missing NumPy), and
  `cardqueue_overflow` (expected `SIGABRT`, received status 0). None exercises
  the removed Batch 1 modes or their guard entries; these are the same general
  failure classes recorded in the decision log.
- Original guarded fair `bestbench` 1000 sims × 8 seeds: **INCOMPLETE**. It did
  not finish within six minutes and was terminated; this remains unverified.

**Status: COMPLETED (Phase 6 Batch 1).** Implementation commit `refactor: remove obsolete server benchmark modes` (2026-08-12) removed:
- the four `restbench`/`shopbench`/`allbench`/`skipbench` dispatch branches in `apps/one_combat.cpp`;
- the dedicated wrappers `restBench`, `shopBench`, `allOOCBench`, `skipBench`, plus the `oocBench` helper used only by `restBench`/`shopBench`;
- the four corresponding entries in `tools/seed_guard.sh`.
`bestbench` and `runFullRunOOC` are unchanged. The implementation checks pass,
but the broader checks above remain incomplete or environment-limited; no
runtime or policy-quality claim is made.

---

### Batch 2 — Basic dead modes (HIGH confidence, low risk)

**Concept:** Remove `bench`, `runbench`, `mcts`, `random`, `draftbench`, `cardbench`, `combobench`, `pathbench`, `carddump`, `deck` modes.

**Why second:** Same confidence pattern as Batch 1 but across more modes. Each removal is independent. Some functions may be shared with live code — verify before deleting.
- `datagen` and `causalgen` were excluded from that batch. `datagen` retains
  `tools/run/datagen_loop.sh`; the root-script audit later removed the unused
  causal Ridge trainer, leaving any `causalgen` mode decision to a separate
  `apps/one_combat.cpp` audit.

**Files changed:** `apps/one_combat.cpp` only.

**Verification:** `ctest --test-dir build --output-on-failure` (all CTest entries still pass); `bestbench` 8-seed smoke.

---

### Batch 3 — Load-only dead flags (HIGH confidence, low risk, small cleanup value)

**Concept:** Remove `STS_VNET_COND_BOSS` and `STS_VNET_COND_ACT3` and their global declarations. These are parsed, echoed, and stored but never read at predict time — they are load-only dead code.

**Why third:** These are the only flags with HIGH-confidence evidence of being truly dead (no runtime effect). They are separate from diagnostic flags (which have decision-log provenance) and from behavior-changing experimental flags (which need deliberate retirement decisions).

**Files changed:** `apps/one_combat.cpp` (flag parsing + global declarations).

**Verification:** `vnettest` parity check (prove byte-identical VNet predictions); `bestbench` 8-seed smoke.

**Not included in this batch:** The S3 diagnostic flags (`STS_S3_OUTCOME_BUCKET_DIAG*`, etc.) have decision-log documentation and are write-only diagnostic tools. The behavior-changing experimental flags (`STS_S3_ENDTURN_MARGINALIZE*`, `STS_S3_UNION_EXPAND`) are NOT in this batch — see below for deferred items.

### Batch 4 — Server-dependent OOC flags (MEDIUM confidence, higher risk)

**Concept:** Remove `STS_CARD_NN`, `STS_CARD_ACTION`, `STS_OOC_ACTION_NN`, `STS_BOSS_RELIC`, `STS_NEOW_V`, `STS_VPATH`, `STS_BOSS_V`, `STS_PATH_V`, `STS_PATH_GRAPH`, `STS_PATH_ACTION`, `STS_EVENT_V`, `STS_POTION_SAVE`, `STS_SHOP_WIN`, `STS_BOSS_DRAFT`, `STS_ACT_FIGHT_PROBE_DRAFT` and their associated function implementations.

**Why later:** These flags are connected to server-dependent (`v_server.py`) OOC policy paths. The code is not dead (the flag-parsing paths exist and the server-call code is reachable if these flags are set), but:
- Native OOC is the default.
- These paths have been superseded by native models and the one-ply Q-gate stack.
- Removing them requires auditing each flag's function implementation for shared code.
- The cleanup value is HIGH because it simplifies the OOC policy chain (`runFullRunOOC`).

**Risk:** MEDIUM — some server-call code may share helper functions with native-OOC paths. Audit first.

**Files changed:** `apps/one_combat.cpp` (flag parsing + function implementations).

**Verification:** `bestbench` 16-seed smoke; `ctest` pass.

---

### Batch 5 — All-OOC checkpoint oracle machinery (MEDIUM confidence, high cleanup value)

**Concept:** Remove `STS_ACT_FIGHT_PROBE_ALL_OOC`, `STS_ACT_FIGHT_PROBE_MARGIN`, `STS_ACT_FIGHT_PROBE_TERM_WIN`, `STS_ACT_FIGHT_PROBE_PREDICT*`, `STS_ACT_FIGHT_PROBE_{SIMS,FUTURES,CHECKPOINT_SIMS,FLOOR_DECAY,MAX_CHECKPOINTS,TRACE,PARALLEL,ENCOUNTER_NN,LOG,DRAFT}` and the entire `actFightProbe*` function family.

**Why later:** §111 falsified the checkpoint oracle as a live full-run policy. The oracle remains as an offline teacher/ranker tool (§66k/§66l/§67). However:
- The entire all-OOC checkpoint rollout is a large block (~2,000+ lines in `apps/one_combat.cpp`).
- If the offline teacher use is still needed, this batch must wait.
- If not, this is one of the highest cleanup-value batches.

**Risk:** MEDIUM — need to confirm the teacher tool is no longer needed.

**Files changed:** `apps/one_combat.cpp` (major surgery).

---

### Batch 6 — Falsified S2 features (LOW risk, low priority)

**Concept:** Remove `STS_CONV_ROOT`, `STS_ROLLOUT_CAPS`, `STS_CONVERGE`.

**Why last:** These are isolated S2 features that are opt-in, default-off, byte-identical when unset, and falsified at gates. However:
- They are self-contained in Searcher2 code.
- They share no mutable state with default paths.
- Low cleanup value (they don't complicate anything when off).
- Could be left as reproducibility levers.

**Files changed:** `apps/one_combat.cpp` (flag parsing), `src/sim/search/BattleScumSearcher2.cpp`.

---

### Not recommended for deletion at this time

| Candidate | Reason to keep |
| --- | --- |
| `CombatPVNet` loader + inference | Active load path; policy priors for S2; value leaf for S3; PVNet retrain experiments may reopen |
| `CombatDistValueNet` | Active load path; `STS_DIST_VNET` is a real runtime switch in S3; `parity_test` exists |
| `OocStrategicNet` (V2/V3) | V3 is the deployed fallback; historical baselines reference V3 gates |
| `OocCheckpointNet` | Active opt-in; NN policy before ordinary layers |
| `Map-DAG encoder (V6)` in `OocStrategicNet` | Code is loaded but never called without V6 + MAP gate; removal could simplify the loader but requires parity-check verification — medium priority |
| `apps/test.cpp` unregistered subcommands | These are test functions that might be useful for debugging; many exercise internal invariants (belief, drawpile, prune, etc.); low code bloat — keep as internal test tooling |
| `apps/parity_test.cpp` | Maintained by `parity_test.py`; small file |
| `apps/main.cpp` + ConsoleSimulator path | Part of the pybind11 module contract; needed for the `slaythespire` module |
| `STS_CONV_ROOT`, `STS_ROLLOUT_CAPS` | Falsified at gates but isolated, byte-identical when unset; useful for reproduction |
| `STS_S3_ENDTURN_MARGINALIZE*` | STOPped prototype (2026-08-09); behavior-changing experimental flag; retained for potential offline/training applications |
| `STS_S3_UNION_EXPAND` | Experimental S3 reuse feature; part of reuse architecture; changes tree structure; not recommended for deletion |
| S3 diagnostic flags (OUTCOME_BUCKET_DIAG*, etc.) | Write-only CSV diagnostics with decision-log documentation; each requires per-flag retirement decision |
| Core S3 reuse configuration (`STS_REUSE_OBS_STABLE`, `STS_REUSE_MAX_SEARCHES`, etc.) | Promoted to default since 2026-08-09 (decisions/s3-obs-stable-reuse-promotion.md); current behavior, NOT stale |

---

## Confidence scores

| Candidate cluster | Confidence | Cleanup value | Deletion risk | Verification cost |
| --- | --- | --- | --- | --- |
| Batch 1: Server-dependent benchmark modes | HIGH | MEDIUM | LOW | LOW |
| Batch 2: Basic dead modes (excl. datagen/causalgen) | HIGH | LOW | LOW | LOW |
| Batch 3: Load-only dead flags (`STS_VNET_COND_*`) | HIGH | LOW | LOW | LOW |
| Batch 4: Server-dependent OOC flags | MEDIUM | HIGH | MEDIUM | MEDIUM |
| Batch 5: Checkpoint oracle machinery | MEDIUM | HIGH | MEDIUM | HIGH |
| Batch 6: Falsified S2 features | HIGH | LOW | LOW | LOW |

Deferred (not in any cleanup batch):
- S3 diagnostic flags (OUTCOME_BUCKET_DIAG*, etc.) — require per-flag retirement decisions
- `STS_S3_ENDTURN_MARGINALIZE*` — behavior-changing STOPped prototype
- `STS_S3_UNION_EXPAND` — active experimental feature in reuse architecture
- `datagen` / `causalgen` modes — retained callers must be retired first

---

## COVERAGE

```text
apps files audited:                8 (main.cpp, one_combat.cpp, test.cpp, small-test.cpp, parity_test.cpp,
                                      ooc_checkpoint_net.h, ooc_strategic_net.h, ooc_strategic_tok_net.h)
src/include search impl. units:    14 (Action, BattleContext, BattleScumSearcher2/3, CombatCpsiNet,
                                      CombatDistValueNet, CombatObservation, CombatPVNet, CombatValueNet,
                                      ExpertKnowledge, GameAction, ScumSearchAgent2, SimpleAgent,
                                      SearchDiagnostics)
one_combat modes inventoried:      44
STS_* feature flags inventoried:   87 (includes all S3 reuse, diagnostic, behavioral, and experimental flags)
model runtime implementations:     5 (CombatValueNet, CombatPVNet, CombatDistValueNet, CombatCpsiNet,
                                      CombatObservation)
tests/callers inspected:           CTest 21 entries, test.cpp 30+ subcommands, ~10 shell/Python scripts
```

---

## CLASSIFICATION SUMMARY

Exact counts from corrected tables:

```text
CURRENT:                   7 modes + ~6 flags
  bestbench, strategicmarggen, searchdiag, leafdiag, leafref, rollouttrace,
  frontiengen, leafrelabel, strategicgen, strategicgen2, fairgen, combatgen,
  fightgen, vnettest, winnettest, pvnetparity, policynettest, speedtest,
  Searcher2, ScumSearchAgent2, CombatValueNet, ExpertKnowledge,
  STS_NATIVE_OOC, STS_SKIP_THR, STS_POLICY, STS_CPUCT, STS_STOP_AFTER_ACT,
  STS_COLLECT_KEYS

SUPPORTED_OPTIONAL:         ~58 flags + 4 model runtimes + ~12 modes
  Searcher3, SimpleAgent, CombatPVNet, CombatDistValueNet, CombatCpsiNet,
  OocCheckpointNet, OocStrategicNet, OocStrategicTokNet,
  STS_SEARCHER3, STS_FAIR, STS_LIVE_VALID, STS_FORCED_MOVE,
  STS_S3_BELIEF/CHAIN/PRUNE/LIVE/CRN/PARTICLES, STS_VNET, STS_PVNET,
  STS_DIST_VNET, STS_CPSI_NN, STS_OOC_STRATEGIC_*, STS_OOC_CHECKPOINT_NN,
  STS_REUSE_MAX_SEARCHES/STATS_MODE/ALWAYS_Q/OBS_STABLE/RECONCILE_ROOT,
  STS_S3_UNION_EXPAND, STS_MULTISELECT_MODE/CANONICAL, S3 diagnostic flags
  (OUTCOME_BUCKET_DIAG*, BUCKET_VALUE_DIAG*, DRAW_PROB_DIAG*,
  LEAFVALUE_DIAG*, ROOT_RACE_DIAG*, BELIEF_AUDIT*),
  datagen2, datagen3, policygen, mapbatch, dumpmap, distgen, cpsictr,
  reprobench, runtrace, run, pvnetparity, policynettest, speedtest,
  policystats, mapnntest, oocnextgen

REPRO_ONLY:                 ~6 flags + 4 modes
  STS_CONV_ROOT, STS_ROLLOUT_CAPS, STS_CONVERGE,
  STS_ACT_FIGHT_PROBE_* (all-OOC checkpoint oracle),
  STS_S3_ENDTURN_MARGINALIZE* (stopped prototype),
  pathcfgen, datagen (retained loop script exists),
  policystats

SUPERSEDED_CONNECTED:       ~20 flags + 2 modes
  v_server-dependent OOC flags (CARD_NN, CARD_ACTION, OOC_ACTION_NN,
  BOSS_RELIC, NEOW_V, VPATH, BOSS_V, PATH_V, PATH_GRAPH, PATH_ACTION,
  EVENT_V, POTION_SAVE, SHOP_WIN, BOSS_DRAFT, ACT_FIGHT_PROBE_DRAFT,
  DATAGEN_GATES, REFIGHT_FLOOR/N, COMBAT_LOG),
  STS_REUSE_CPU_DIAG*, STS_REUSE_CARRY_DIAG, STS_REUSE_DIAG,
  causalgen, datagen (loop caller keeps it connected)

DEAD_HIGH_CONFIDENCE:       10 modes + 2 flags remaining
  bench, runbench, mcts, random, cardbench, combobench, pathbench, draftbench,
  carddump, deck
  (originally 14 modes — confirmed zero non-historical callers;
   4 removed in Batch 1: restbench, shopbench, allbench, skipbench)
  STS_VNET_COND_BOSS, STS_VNET_COND_ACT3 (2 load-only dead flags)

UNKNOWN:                    1 flag
  STS_COMBAT_WIN_BONUS (may be load-only; requires CombatValueNet::predict audit)

---

## OPEN QUESTIONS

1. **`STS_COMBAT_WIN_BONUS`:** The flag calls `search::g_combatVNet.setWinBonus(std::atof(b))`, but the deployed end-HP VNet (not utility-R) predict path may not use the win-bonus field. The `CombatValueNet::predict` function needs to be audited to confirm whether `winBonus` is actually used in the end-HP path. If unused, this flag is a load-only dead flag like `STS_VNET_COND_BOSS`/`STS_VNET_COND_ACT3`.

2. **All-OOC checkpoint oracle:** Is the teacher/ranker tool (`actFightProbeAllOocPolicy`) still needed for offline analysis? The §66k/§66l/§67 references suggest it has an offline-teacher role even though the live-policy use was falsified at §111. If still needed, Batch 5 should wait. If not, Batch 5 is the highest cleanup-value batch.

3. **`policygen` mode:** Referenced only in `train_policy.py` comment ("`one_combat.elf policygen`") — is this mode still actively used for policy training, or is `fairgen` / `fightgen` the current path? The comment is not evidence of active use.

4. **S3 diagnostic flags retirement:** Each of the 5 diagnostic flag families (`OUTCOME_BUCKET_DIAG*`, `BUCKET_VALUE_DIAG*`, `DRAW_PROB_DIAG*`, `LEAFVALUE_DIAG*`, `ROOT_RACE_DIAG*`) has decision-log documentation. Does any current analysis tool consume their CSV output? If not, each flag can be retired independently.

5. **`tools/run/datagen_loop.sh`:** This script directly invokes the older `datagen` mode for bulk collection. Should it be migrated to `datagen2` or retired? Until that decision is made, `datagen` mode cannot be deleted.

6. **Resolved 2026-09-07:** the causal Ridge trainer was unused and removed.
   The `causalgen` mode was deliberately left untouched because the root-script
   audit excluded `apps/one_combat.cpp`.

7. **`datagen2` vs `datagen3`:** Both have active callers (`datagen2_loop.sh`, `run_card_cf_collection.sh`). Which is the canonical datagen mode? Consolidation may be possible but is a separate investigation.

---

## Implementation changes

```text
implementation files changed (this document): 0
implementation files changed (Batch 1, 2026-08-12): apps/one_combat.cpp, tools/seed_guard.sh
runtime behavior changed: no (bestbench unchanged)
models changed: no
experiments run: none
seed gates run: bestbench 8-seed smoke (guarded)
```

---

## Final state

```text
git status --short: only the investigation document added
git diff --stat:   one new file
git diff --check:  clean
```
