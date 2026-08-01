# Build and debugging

Last verified: 2026-07-31 against commit `67320b3` and the current working tree.

## Purpose

Document the actual CMake graph, checkout-specific dependency limitations,
manual checks, model-load diagnostics, and tracing boundaries.

## Current implementation

`CMakeLists.txt` requires CMake 3.19, C++17, and applies
`-Wno-shift-count-overflow -O3 -fopenmp` globally. It recursively gathers
`src/*.cpp` and compiles those sources directly into:

- pybind11 module `slaythespire`;
- executables `main`, `one_combat`, `test`, and `small-test`.

There is no reusable `sts`/`libsts.a` target and no CTest registration.
`apps/test.cpp::main` is a manual command dispatcher; with no arguments it
prints `incorrect arguments` and exits successfully. `apps/parity_test.cpp` has
a `main` but no CMake target.

Normal configured commands are:

```bash
cmake -S . -B build
cmake --build build -j
```

The current `build/CMakeCache.txt` is a Release Unix Makefiles cache using
`/usr/bin/c++` under Linux/WSL. The ignored `build/one_combat` is the cached
CMake executable. `selfplay/loop.sh` instead invokes `./one_combat.elf`; CMake
does not create that path.

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
STS_FAIR=1 ./build/one_combat bestbench 1000 8 0
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

## Known limitations

- `.gitmodules` declares `json/` and `pybind11/`, but the git index contains no
  gitlinks for either and both root directories are absent. A fresh configure
  from this checkout lacks required sources. A tracked standalone JSON header
  exists at `extern/nlohmann/json.hpp`, but CMake does not use it as a complete
  replacement for both subdirectories.
- Native PowerShell/MSVC configuration is unverified; current flags are
  GNU-specific.
- `build/test` is absent from the current cache even though the target exists in
  CMake.
- No repository dependency lock describes Python packages.
- `parity_test.py` expects an unbuilt binary and an unavailable trained PyTorch
  checkpoint path; it is not a valid parity check as written.
- Native PV/distribution code attempts a developer-specific SciPy OpenBLAS path
  before scalar fallback.

## Open questions

- Should dependencies become real gitlinks, vendored sources, or fetched CMake
  dependencies?
- Should OpenMP use `find_package(OpenMP)` for cross-platform configuration?
- Should parity/reproducibility utilities become registered tests?
- Should the self-play loop consume `build/one_combat` or define a supported
  copy/build step for `one_combat.elf`?

## Relevant code

- `CMakeLists.txt`
- `.gitmodules`; `.gitignore`
- `apps/main.cpp::main`
- `apps/one_combat.cpp::main`, `runTraceRun`, `bestBench`
- `apps/test.cpp::main`
- `apps/parity_test.cpp::main`; `parity_test.py`
- `selfplay/loop.sh::run_gate_batch`
- `src/sim/search/CombatPVNet.cpp` BLAS initialization
- `src/sim/search/CombatDistValueNet.cpp` BLAS initialization
