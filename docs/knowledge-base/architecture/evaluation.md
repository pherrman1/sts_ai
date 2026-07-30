# Evaluation and experiment reporting

Last verified: 2026-07-30 against the current working tree, including
uncommitted implementation changes.

## Primary evaluation paths

`one_combat bestbench <sims> <nSeeds> <asc> [seedOffset] [resultsFile]` runs the
current OOC stack across a seed block and optionally appends per-seed CSV rows
(`apps/one_combat.cpp`, `bestBench` and `main` `bestbench` branch).
`runtrace` executes a separate `runTraceRun` loop for one seed. It resembles
but does not match `runFullRunOOC`: event and treasure NN scores are not used,
some policy layers are omitted, and draft logging uses the server-only `M`
endpoint (`apps/one_combat.cpp`, `runFullRunOOC`, `runTraceRun`, `tr_logDraft`,
and `main` `runtrace` branch). Other modes such as `evalcombat`, `runbench`,
`bestbench`, and policy-specific benches are dispatched by the same `main`.

`bestBench` currently writes:
`seed,won,floor,act,hpEnd,maxHp,fightsLost,deathCombat,deathEncounter,sec`
(`apps/one_combat.cpp`, `bestBench` results header and row writer). Aggregate
output reports wins, floors, HP, and elapsed/process timing from the same
function.

## Honest-play and comparison rules

`STS_FAIR=1` causes `ScumSearchAgent2::playoutBattle` to use
`playoutBattleFair` and commit one root action per rebuilt search. Searcher2 is
still the default: its determinization changes draw order plus shuffle/card RNG
only. `STS_SEARCHER3=1` opts into the six-stream particle implementation, which
has an unconditioned/no-op belief update (`src/sim/search/ScumSearchAgent2.cpp`,
`playoutBattle`, `playoutBattleFair`; `src/sim/search/BattleScumSearcher2.cpp`,
`determinize`; `src/sim/search/CombatObservation.cpp`, `Belief::update`). Fair
and known-RNG results are distinct project regimes, but “fair” is not proof
that every hidden variable is modeled.

The self-play gate compares candidates and baseline on common seed ranges and
uses dense `floor + 100 * WIN_WEIGHT * won` differences plus confidence bounds
(`selfplay/loop.sh`, `run_gate_batch`, `gate_stats`). With the checked-in
`WIN_WEIGHT=0.1`, a win contributes ten score units (`selfplay/config.env`,
`WIN_WEIGHT`). The meta and policy margin snapshot is +0.5; the value arm uses
-0.5 non-inferiority (`selfplay/config.env`, `PROMOTE_MARGIN`,
`VALUE_MARGIN`).

The `Z=2.58` interval is recalculated at every adaptive look without a
sequential/multiplicity correction. More importantly, the current meta arm's
candidate server is bypassed by default native OOC inference, so its paired
rows do not prove candidate V_win/rest use (`selfplay/loop.sh`, policy env and
`start_server`; `apps/one_combat.cpp`, native startup and rest queries). The
mechanical pairing is implemented; meta-arm validity is not.

## Reporting ownership

`EXPERIMENTS.md` is the chronological evidence log. New benchmarked ideas,
negative outcomes, later corrections, and invalidations belong there. This
knowledge base records only the current recommendation and durable evaluation
mechanics (`EXPERIMENTS.md`, numbered entries; `AGENTS.md`,
“Experiment-recording rules”).

`paired_analysis.py` performs paired summaries, bootstrap intervals, and
win-rate intervals from result CSVs (`paired_analysis.py`, `load`,
`bootstrap_ci`, and `main`).

## Test coverage status

There is no `enable_testing()` or `add_test()` in `CMakeLists.txt`, and no
pytest/unittest suite is present. The `test` target is a manual command
dispatcher (`apps/test.cpp`, `main`). `apps/parity_test.cpp` is a manual native
inference utility but has no CMake target.

**Discrepancy:** `parity_test.py` constructs a freshly initialized
`CombatDistNet` and never loads a checkpoint, then compares that random
PyTorch network with C++ inference from `build/v_combat_dist.txt`. It also
expects `./build/parity_test.elf`, which CMake does not build
(`parity_test.py`, model construction and subprocess call; `CMakeLists.txt`,
target declarations). Its PASS result cannot establish trained-model parity.

## Known reporting discrepancy

`paired_analysis.py` currently reads zero-based column 3 as HP and column 4 as
elapsed seconds (`paired_analysis.py`, `load`). The current `bestBench` schema
uses those columns for `act` and `hpEnd`; elapsed seconds is zero-based column
9 (`apps/one_combat.cpp`, `bestBench`). Therefore both HP and timing summaries
are misaligned for current bestbench CSVs. Win and floor fields still align.

The README's fair-play headline and the older known-RNG figures summarized in
AGENTS.md use different regimes (`README.md`, “Current state”; `AGENTS.md`,
“Current best known configuration”). They must not be presented as directly
comparable.

`EXPERIMENTS.md` entry 66i records 39/128 on seeds 126700--126827 but cites an
absent raw-results directory, describes a PUCT/V-combat stack without pinning
every model path, and has no exact command. Running the same seed block with
current defaults is a new measurement, not a strict reproduction of that
headline (`EXPERIMENTS.md`, entry 66i; tracked `build/` artifacts).

## Minimal validation ladder

1. Build the affected target from `CMakeLists.txt`.
2. Run a launch/argument smoke check for the relevant executable
   (`apps/test.cpp` `main` or `apps/one_combat.cpp` `main`).
3. Run model parity/schema validation where a model boundary changed.
4. Use a small fixed-seed `STS_FAIR=1 bestbench` smoke for integration.
5. Use paired common seeds and the documented budget before making a policy
   quality claim (`selfplay/loop.sh`, gate section).

## Relevant code

- `apps/one_combat.cpp` — `bestBench`, `runFullRunOOC`, `main` modes.
- `src/sim/search/ScumSearchAgent2.cpp` — fair versus known-RNG dispatch.
- `selfplay/loop.sh` — `gate_stats`, `run_gate_batch`, adaptive gate.
- `paired_analysis.py` — paired CSV consumer.
- `apps/test.cpp` — manual `test` harness.
- `apps/parity_test.cpp` and `parity_test.py` — incomplete parity path.
- `EXPERIMENTS.md` — canonical evidence log.
