# Build and debugging

Last verified: 2026-08-02 against the current working tree.

## Purpose

Document the actual CMake graph, checkout-specific dependency limitations,
manual checks, model-load diagnostics, and tracing boundaries.

## Current implementation

`CMakeLists.txt` requires CMake 3.19, C++17, and applies
`-Wno-shift-count-overflow -O3 -fopenmp` globally. It recursively gathers
`src/*.cpp` and compiles those sources directly into:

- pybind11 module `slaythespire` (only when CPython development headers are
  found; otherwise skipped with a warning);
- executables `main`, `one_combat`, `test`, and `small-test`.

`json` and `pybind11` are real gitlinks after the 2026-08-02 restoration
(`json` at `2222d386`, `pybind11` at `63d627c5`); a fresh clone requires
`git submodule update --init`. The pybind11 module guard in `CMakeLists.txt`
means a machine without `python3-dev` still builds the core executables;
check `find_package(Python)` results to know whether `slaythespire` exists.

There is no reusable `sts`/`libsts.a` target. CTest is registered:
`ctest --test-dir build` runs parse/syntax checks (`bash -n`, `py_compile`) and
`check_replay.py --self-test`; run `ctest -N` to list them. The `test` target
is named `unit-test` in CMake with `OUTPUT_NAME test` (CTest reserves the name
`test`); `apps/test.cpp::main` is a manual command dispatcher that with no
arguments prints `incorrect arguments` and exits successfully, and with a
subcommand runs the targeted Searcher3/terminal checks (see
[`architecture/combat-search.md`](../architecture/combat-search.md)).
`apps/parity_test.cpp` has a CMake target `parity_test`; `parity_test.py`
locates the binary via `STS_PARITY_BIN` or `build/parity_test`.

Normal configured commands are:

```bash
cmake -S . -B build
cmake --build build -j
```

The current `build/CMakeCache.txt` is a Release Unix Makefiles cache using
`/usr/bin/c++` under Linux/WSL. The ignored `build/one_combat` is the cached
CMake executable. `selfplay/loop.sh` defaults `BIN` to `build/one_combat`
(overridable via `ONE_COMBAT_BIN`/`STS_BIN`).

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

Long benchmark sweeps (128/256-seed gates, datagen) run on the GCP server
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

## Known limitations

- Native PowerShell/MSVC configuration is unverified; current flags are
  GNU-specific.
- `build/test` exists in the current cache (target `unit-test`).
- No repository dependency lock describes Python packages.
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
- `.gitmodules`; `.gitignore`
- `apps/main.cpp::main`
- `apps/one_combat.cpp::main`, `runTraceRun`, `bestBench`
- `apps/test.cpp::main`
- `apps/parity_test.cpp::main`; `parity_test.py`
- `check_replay.py`
- `selfplay/loop.sh::run_gate_batch`
- `src/sim/search/CombatPVNet.cpp` BLAS initialization
- `src/sim/search/CombatDistValueNet.cpp` BLAS initialization
