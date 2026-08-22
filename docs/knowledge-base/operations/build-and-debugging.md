# Build and debugging

Last verified: 2026-08-14 against the current working tree.

## Purpose

Document the actual CMake graph, checkout-specific dependency limitations,
manual checks, model-load diagnostics, and tracing boundaries.

## Current implementation

`CMakeLists.txt` requires CMake 3.19, C++17, and applies
`-Wno-shift-count-overflow -O3 -fopenmp -flto` globally. It recursively gathers
`src/*.cpp` into the `sts_core_objects` OBJECT library, which is reused by
the native executables `main`, `one_combat`, `parity_test`, `unit-test`, and
`small-test`. The Python module continues to compile `${sts_lightspeed_SOURCES}`
independently because its pybind11/PIC/visibility requirements are kept
separate from the native object target. The resulting targets are:

- pybind11 module `slaythespire` (only when CPython development headers are
  found; otherwise skipped with a warning);
- executables `main`, `one_combat`, `test`, and `small-test`.

`json` and `pybind11` are real gitlinks after the 2026-08-02 restoration
(`json` at `2222d386`, `pybind11` at `63d627c5`); a fresh clone requires
`git submodule update --init`. The pybind11 module guard in `CMakeLists.txt`
means a machine without `python3-dev` still builds the core executables;
check `find_package(Python)` results to know whether `slaythespire` exists.

There is no reusable `sts`/`libsts.a` target; `sts_core_objects` is an internal
native build object collection rather than a library. CTest is registered:
`ctest --test-dir build` runs parse/syntax checks (`bash -n`, `py_compile`) and
`ctest` checks including `tools/verify/check_replay.py --self-test`; run `ctest -N` to list them. The `test` target
is named `unit-test` in CMake with `OUTPUT_NAME test` (CTest reserves the name
`test`); `apps/test.cpp::main` is a manual command dispatcher that with no
arguments prints `incorrect arguments` and exits successfully, and with a
subcommand runs the targeted Searcher3/terminal checks (see
[`architecture/combat-search.md`](../architecture/combat-search.md)).
`apps/parity_test.cpp` has a CMake target `parity_test`; `parity_test.py`
locates the binary via `STS_PARITY_BIN` or `build/parity_test`.

Normal configured commands are:

```bash
cmake --preset linux-gcc-release
cmake --build --preset linux-gcc-build

cmake --preset linux-gcc-debug
cmake --build --preset linux-gcc-debug-build
ctest --preset linux-gcc-test
```

`CMakePresets.json` is checked in for the verified Linux/WSL GCC-style
environment. `linux-gcc-release` uses Unix Makefiles, `g++`, and a Release
build in `build/linux-gcc-release`; `linux-gcc-build` selects that normal
build. `linux-gcc-debug` and `linux-gcc-debug-build` create a separate Debug
build in `build/linux-gcc-debug`; `linux-gcc-debug-build` is serialized to keep
that all-target Debug build reliable on constrained Linux/WSL hosts.
`linux-gcc-test` runs the existing CTest suite there because `cardqueue_overflow`
intentionally expects an assertion abort and therefore needs assertions enabled.
The preset file requires CMake 3.21 or newer; the source graph itself still
requires CMake 3.19. Native PowerShell/MSVC remains unverified and has no preset.

### Authoritative GitHub Actions verification

`.github/workflows/ci.yml` is the authoritative repository verification check.
Changes should reach `main` through a pull request only after the Linux GCC
check passes. It runs one public Linux GCC lane on pushes and pull requests:
recursive submodule checkout,
`build-essential`/CMake/CPython development prerequisites plus ccache, Python 3.12 and uv,
`uv lock --check`, `uv sync --locked`, the read-only `tools/agent/doctor.sh`,
and the checked-in Debug configure, build, and CTest presets. The workflow adds
the synced `.venv/bin` to `PATH` before CTest so its existing `python3` commands
use the locked default environment; all test failures remain fatal and CTest
prints failure output through its preset.

This lane deliberately does not run statistical gameplay seed benchmarks, access
private GCP resources, use ignored training checkpoints, or deploy. The default
uv dependency group is sufficient for every registered CTest check and the
doctor; trained-model parity remains outside CI because it requires a produced
checkpoint (see [Known limitations](#known-limitations)).

The CI job enables ccache (v4+) as a C++ compiler launcher to reduce repeated
compilation time. ccache is installed from Ubuntu packages, activated via
`CMAKE_CXX_COMPILER_LAUNCHER=ccache` and `CCACHE_COMPILERCHECK=content` at the
job level only; local and release builds outside CI are **not** affected. The
`${{ github.workspace }}/.ccache` directory is cached by `actions/cache@v4`
with a per-commit key `ccache-${{ runner.os }}-${{ runner.arch }}-gcc-${{ github.sha }}`
and a restore-key prefix `ccache-${{ runner.os }}-${{ runner.arch }}-gcc-`; the
cache is bounded to 1 GiB via `CCACHE_MAXSIZE`. Statistics are zeroed before
the build and printed after the build (with `if: always`) for measurement.

`selfplay/loop.sh` still defaults to `build/one_combat` (overridable via
`ONE_COMBAT_BIN`/`STS_BIN`). Set either variable to
`build/linux-gcc-release/one_combat` when using the checked-in preset.

### Python tooling environment

`pyproject.toml` and `uv.lock` describe direct dependencies used by maintained
repository scripts; this repository is not packaged as a Python module. The
default environment contains only NumPy. The Linux GCC CI job additionally
installs the locked `analysis` extra because CTest includes pandas/SciPy
self-tests. Install additional direct-dependency groups only for the tooling
that needs them:

```bash
uv sync --locked                         # default: NumPy and stdlib tooling
uv sync --locked --extra analysis        # pandas, SciPy, scikit-learn, XGBoost
uv sync --locked --extra ml              # PyTorch, XGBoost
uv sync --locked --extra research        # CatBoost, Optuna
uv sync --locked --all-extras            # every maintained tooling group
uv run --extra analysis python paired_analysis.py --self-test
uv run --extra ml python train_combat_pvnet.py --help
```

Use `uv run` for direct maintained Python commands so they execute against the
locked project environment. Existing CMake/CTest commands intentionally retain
their `python3` invocation and are not changed by this infrastructure phase.

Run the read-only prerequisite diagnostic before configuring a new machine:

```bash
tools/agent/doctor.sh
```

It checks the repository root, expected checkout paths, initialized submodules,
`cmake`/`g++`/`python3`/`uv` availability, and `uv lock --check`. It reports
problems but never installs, initializes, deletes, or otherwise repairs local
state.

### Phase 2 reproducibility verification (2026-08-14)

The following commands were run in this Linux/WSL GCC-style checkout with
`uv 0.12.3`, CMake 4.4.2, GCC 13.3.0, and Python 3.12.3:

```bash
uv lock --check
UV_PROJECT_ENVIRONMENT=/tmp/sts-ai-phase2-uv-sync uv sync --locked
uv run --locked python paired_analysis.py --self-test
cmake --preset linux-gcc-release
cmake --build --preset linux-gcc-build
cmake --preset linux-gcc-debug
cmake --build --preset linux-gcc-debug-build
ctest --preset linux-gcc-test --output-on-failure
tools/agent/doctor.sh
git diff --check
```

Results: the lock was consistent; the isolated sync installed NumPy 2.5.2;
the `paired_analysis.py` self-test passed; the Release preset built `main`,
`one_combat`, `parity_test`, `test`, `small-test`, and `slaythespire`; the
serialized Debug preset built the same targets; CTest passed all 27 tests; the
doctor reported all checks passed; and `git diff --check` was clean. Both builds
reported pre-existing narrowing warnings in `apps/one_combat.cpp` and
`src/sim/search/BattleScumSearcher3.cpp`; no build errors occurred.

### Phase 6 native core object reuse (2026-08-14)

Phase 6 introduced `sts_core_objects` to compile each common `src/*.cpp`
translation unit once and reuse its object files across the five native
executables. The deliberately separate `slaythespire` target still compiles
the common source glob itself. The serial Debug measurement used
`CCACHE_DISABLE=1` and `/usr/bin/time -p`:

| Configuration | Build directory | Result | real | user | sys |
| --- | --- | --- | ---: | ---: | ---: |
| Before | `build-phase6-before-2` | success | 286.27s | 258.09s | 23.39s |
| After | `build-phase6-after-1` | success | 78.21s | 72.07s | 5.86s |

Before evidence in `build-phase6-before-2` showed 36
`CMakeFiles/<target>/src/...` compile lines for each native target, or 180
common translation-unit compilations total. After evidence in
`build-phase6-after-1` showed the 36 common objects under
`CMakeFiles/sts_core_objects.dir/src/...` once, followed by linking of the
five executables against those objects. CTest passed all 27 tests and the five
expected executable paths were present. The timing is coarse supporting
evidence; the primary result is the build-graph compilation ownership.

## Important data flow

1. Configure loads root `json/` and `pybind11/` through `add_subdirectory`.
2. CMake globs simulator/search sources into every declared target.
3. Executable startup parses environment flags and loads named model artifacts.
4. Startup output is part of verification: native OOC, policy, combat value,
   distribution, and PVNet messages show what loaded.
5. `bestbench` or a focused mode exercises the integration path; per-seed
   output can be inspected using the benchmark protocol.

Useful focused checks after the relevant target exists:

```bash
./build/test
./build/test seed_contract 0
./build/small-test isbattleover
STS_FAIR=1 ./build/one_combat bestbench 1000 8 0
ctest --test-dir build --output-on-failure
bash -n selfplay/loop.sh
bash -n selfplay/status.sh
python3 -m py_compile paired_analysis.py
```

Do not use `./build/one_combat` without arguments as a launch-only smoke check:
it defaults to `bench` (100 seeds at 2,000 simulations) after loading default
models (`apps/one_combat.cpp::main`).

## Invariants and assumptions

- Do not claim a clean build unless it was performed in the environment being
  reported.
- Shared `Node`, `Edge`, searcher, or other header-layout changes require a
  rebuild of every including translation unit.
- A file existing is not enough; verify runtime load messages.
- CMake output and tracked model artifacts share `build/`; do not remove
  that directory indiscriminately.
- Resolve the exact server PID before stopping it; never use broad
  `pkill -f v_server.py`.
- Commands in this page assume a Bash/WSL-style environment unless explicitly
  described otherwise.

## Debugging interfaces

`runtrace` accepts:

```text
./build/one_combat runtrace <seed> <sims> <asc>
```

Useful flags include `STS_STOP_AFTER_ACT`, `STS_REFIGHT_FLOOR`, and
`STS_REFIGHT_N`. With `STS_OOC_CHECKPOINT_NN`, tracing prints scores on several
OOC screens.

`runTraceRun` does not execute exactly the same policy as `runFullRunOOC`:
its event/treasure scores are diagnostic, some fallthrough layers are omitted,
and draft logging calls the server-only `M` endpoint and can retry when no
server is present (`apps/one_combat.cpp::runTraceRun`, `tr_logDraft`). Treat it
as a debugger, not baseline reproduction.

`reprobench` repeats one seed in one process and appends current `bestbench`
rows. It is the closest current manual determinism probe
(`apps/one_combat.cpp::main` `reprobench` branch).

## GCP benchmark server (sts-test)

Large benchmark sweeps and datagen run on the GCP server
`sts-test` (preemptible, c4-highcpu-24, 24 threads, zone `europe-west3-c`,
project `sts-ai-502709`, user `philippherrmann`). Recorded facts about
reaching it (verified 2026-08-05):

- **Only working client:** the gcloud SDK bundled with the Windows Google
  Cloud SDK install. It is **not on PATH** in PowerShell or WSL — use the
  full path:
  `C:\Users\pherrman\AppData\Local\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd`
  (a second copy exists under `C:\Program Files (x86)\Google\Cloud SDK\...`).
- Plain `ssh philippherrmann@sts-test` does **not** resolve; WSL has no route
  to the server IP. `gcloud compute ssh` (bundled plink + IAP tunnel) is the
  only working route:
  `gcloud.cmd compute ssh philippherrmann@sts-test --zone=europe-west3-c --command "<cmd>"`
  (use `--project=sts-ai-502709` if the default project is not set).
- **Working tree:** `/home/philippherrmann/sts_sweep` is a non-git rsync
  copy, not a clone. Sync changed sources and model artifacts with
  `gcloud.cmd compute scp` (same full path), then build with
  `cmake --build build -j 24`. Tracked `.native` models also come from a
  `git pull`-style handoff per `AGENTS.md`.
- **Workflow:** run sweeps on the server with `nohup` (long runs survive the
  SSH session), pull per-seed CSVs back to `build/` with scp, then analyze
  with `paired_analysis.py` locally.
- **Failure modes:** the instance is preemptible — a plink exit code 1 /
  IAP tunnel error often just means it is down; probe with a trivial
  `hostname; uptime` command first. Before a long run, check the box is free
  (`ps aux | wc -l` / leftover `one_combat` processes from another agent).

### Canonical agent workflow

Use the tracked launcher rather than reconstructing raw gcloud commands:

```bash
python3 tools/agent/gcp_benchmark.py status
python3 tools/agent/gcp_benchmark.py start-instance
python3 tools/agent/gcp_benchmark.py probe
```

The launcher defaults to project `sts-ai-502709`, instance `sts-test`, zone
`europe-west3-c`, user `philippherrmann`, and remote root
`/home/philippherrmann/sts_sweep`. Read-only `status`/`probe` options may be
overridden for troubleshooting. Expensive or mutating `run` and
`start-instance` operations reject any project, zone, instance, user, or remote
root other than this designated target. It never creates, deletes, resizes, or
reconfigures cloud resources.

For a research command, first state the hypothesis/question, baseline and
treatment, seed regime, simulation/particle budget, fair-vs-known-RNG regime,
model hashes/configuration, intended seed count, and decision rule. Then launch
through the helper; it checks for an active `one_combat` process and refuses to
stack a run unless `--allow-parallel` is explicitly supplied:

```bash
python3 tools/agent/gcp_benchmark.py run -- \
  ./build/one_combat bestbench 1000 2000 0
```

For the non-executing remote acceptance proof, add `--foreground
--guard-only`; this validates the 2,000-seed command and exits without running
gameplay:

```bash
python3 tools/agent/gcp_benchmark.py run --foreground --guard-only -- \
  ./build/one_combat bestbench 1000 2000 0
```

`run` changes to the remote root and invokes
`bash tools/seed_guard.sh --gcp-research ...`, so the GCP path retains argument
validation but has no numeric seed ceiling. Detached runs use `nohup`, print
`remote_pid` and `remote_log`, and survive SSH disconnects. Retrieve output with
the printed log path through the same launcher/SSH route, for example:

```bash
gcloud compute ssh philippherrmann@sts-test --project=sts-ai-502709 \
  --zone=europe-west3-c --command 'tail -n 50 /home/philippherrmann/sts_sweep/logs/<log>'
```

There is no repository credential: the helper uses the user's existing local
gcloud authentication. If gcloud is absent or unauthenticated, report that
one-time external blocker rather than creating credentials. Large N is not
scientific evidence by itself; preserve paired common seeds, regime separation,
budget comparability, provenance, schema validation, raw results, and ledger
recording.

## Known limitations

- Native PowerShell/MSVC configuration is unverified; current flags are
  GNU-specific.
- `build/test` exists in the current cache (target `unit-test`).
- The checked-in presets cover only the verified Linux/WSL GCC-style workflow.
  MSVC and other toolchains remain unverified.
- `parity_test.py` needs a produced checkpoint to be a real parity check; its
  missing-binary/checkpoint failures are loud, but trained-model parity is not
  yet exercised.
- Native PV/distribution code attempts a developer-specific SciPy OpenBLAS path
  before scalar fallback; the active backend is printed at load time.

## Open questions

- Should OpenMP use `find_package(OpenMP)` for cross-platform configuration?
- Should parity/reproducibility utilities become registered tests?

## Relevant code

- `CMakeLists.txt`
- `CMakePresets.json`; `pyproject.toml`; `uv.lock`
- `.gitmodules`; `.gitignore`
- `tools/agent/doctor.sh`
- `apps/main.cpp::main`
- `apps/one_combat.cpp::main`, `runTraceRun`, `bestBench`
- `apps/test.cpp::main`
- `apps/parity_test.cpp::main`; `parity_test.py`
- `tools/verify/check_replay.py`
- `selfplay/loop.sh::run_gate_batch`
- `src/sim/search/CombatPVNet.cpp` BLAS initialization
- `src/sim/search/CombatDistValueNet.cpp` BLAS initialization
