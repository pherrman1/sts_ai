# Build and debugging

Last verified: 2026-09-08 against the current working tree.

## Purpose

Document the actual CMake graph, checkout-specific dependency limitations,
manual checks, model-load diagnostics, and tracing boundaries.

## Current implementation

`CMakeLists.txt` requires CMake 3.19 and C++17. All configurations retain
`-Wno-shift-count-overflow` and `-fopenmp`; Release adds `-O3 -flto`, while
Debug uses its normal assertion-enabled flags without forced optimization or
LTO. It recursively gathers `src/*.cpp` into the `sts_core_objects` OBJECT
library, which is reused by the native executables `main`, `one_combat`,
`parity_test`, `unit-test`, and `small-test`. When Python development headers
are present, a separate hidden/PIC `sts_core_pic_objects` collection supplies
the shared Python module; native Release executables therefore retain non-PIC
LTO inputs. The resulting targets are:

- pybind11 module `slaythespire` (only when CPython development headers are
  found; otherwise skipped with a warning);
- executables `main`, `one_combat`, `parity_test`, `test`, and `small-test`.

`json` and `pybind11` are real gitlinks after the 2026-08-02 restoration
(`json` at `2222d386`, `pybind11` at `63d627c5`). `json` is the header-only
Nlohmann JSON library used by native configuration, wire formats, and evidence
tools. `pybind11` builds the optional `slaythespire` Python extension; native
executables still use the repository without that extension when Python
development headers are unavailable.

Submodule checkouts are per worktree. Raw `git worktree add` therefore creates
a checkout whose dependency directories are initially empty, and raw removal
of a worktree containing initialized submodules is fragile on Windows Git. Use
the repository-owned lifecycle command for linked worktrees:

```powershell
python tools/agent/worktree.py create .worktrees/my-task --branch fix/my-task --start-point main
python tools/agent/worktree.py check .worktrees/my-task
python tools/agent/worktree.py remove .worktrees/my-task
```

`create` performs `git worktree add`, synchronizes the declared HTTPS URLs,
initializes both pinned dependencies, and verifies their revisions and metadata
roots. When the managing repository already has the pinned objects, sibling
worktrees seed from those local repositories and then restore their `origin`
URLs to HTTPS; this avoids an unnecessary network clone without sharing a
mutable checkout. A failed create attempts to remove its incomplete worktree
and newly created branch. `remove` refuses a dirty worktree, uses Git's required
forced worktree removal for the clean submodule checkout, then rechecks the
managing checkout.
It deliberately does **not** run `git submodule deinit`: submodule activation
configuration is shared by linked worktrees, so deinitializing one can make
healthy siblings appear uninitialized. It intentionally does not delete the
Git branch. `repair` is the idempotent setup command for an existing checkout:

```powershell
python tools/agent/worktree.py repair .
```

In a Codex-app-managed worktree, run the read-only preflight before the first
Git write:

```bash
python tools/agent/worktree.py preflight .
```

It identifies an app-managed checkout, detached or named HEAD, and whether the
linked worktree's Git directory/common directory are external and writable.
When it reports external read-only metadata, the Codex app must authorize the
branch, staging, and commit operations against that existing worktree. The
repository helper cannot grant sandbox permission and does not create another
worktree. Its publication line also preserves the distinction between a
DNS/transport failure, read reachability, and a platform policy decision about
private-code publication.

The checker rejects `-` (uninitialized), `+` (different commit), `U`
(conflict), a revision different from the superproject gitlink, or a dependency
whose `.git` metadata resolves to another checkout. Run these Git operations
with Windows Git before entering WSL. If lifecycle tooling itself is being
repaired, the equivalent fallback is `git submodule sync --recursive` followed
by `git submodule update --init --recursive`; verify with the lifecycle checker
before configuring. The pybind11 module guard in `CMakeLists.txt` means a
machine without `python3-dev` still builds the core executables; check
`find_package(Python)` results to know whether `slaythespire` exists.

There is no reusable `sts`/`libsts.a` target; `sts_core_objects` is an internal
native build object collection rather than a library. CTest is registered:
`ctest --test-dir build` runs maintained parse/syntax checks and focused
native/Python regressions including
`tools/verify/check_replay.py --self-test`; run `ctest -N` to list them. The `test` target
is named `unit-test` in CMake with `OUTPUT_NAME test` (CTest reserves the name
`test`); `apps/test.cpp::main` is a manual command dispatcher that with no
arguments prints `incorrect arguments` and exits successfully, and with a
known subcommand runs the targeted Searcher3/terminal checks; unknown
subcommands fail nonzero (see
[`architecture/combat-search.md`](../architecture/combat-search.md)).
`apps/parity_test.cpp` has a CMake target `parity_test`; `parity_test.py`
locates the binary via `STS_PARITY_BIN` or `build/parity_test`.

CTest labels provide smaller local verification tiers without weakening the
unfiltered CI gate:

```bash
ctest --preset linux-gcc-test -L smoke
ctest --preset linux-gcc-test -L core
ctest --preset linux-gcc-test -L integration
ctest --preset linux-gcc-test -L tooling
ctest --preset linux-gcc-test -L research-repro
```

`smoke` is the quickest cross-cutting subset; `core` covers deterministic
simulator regressions; `integration` covers search, Silver, model, and native
parity boundaries; `tooling` covers maintained operational utilities; and
`research-repro` preserves analyzer and evidence contracts. Tests may carry
more than one label. The unfiltered `linux-gcc-test` preset remains the full
CTest suite.

The Linux CI job owns the following complete `tests/agent` discovery as a
separate pre-build gate:

```bash
python3 -m unittest discover -s tests/agent -p 'test_*.py' --durations 20
```

Coding-agent evaluator preparation reuses a validated public tracked-export
cache below `.agent-eval/cache`, keyed by source HEAD and exact submodule
revisions. For phase attribution without changing normal stdout, set
`STS_AGENT_EVAL_TIMINGS=1` when invoking `tools/agent/eval.py prepare`.

Python 3.12's standard-library duration reporter prints the 20 slowest
individual test cases on successful and failed runs without changing discovery
or exit semantics. Those modules are not registered
again in CTest, and scripts exercised by a behavioral self-test are not given
a redundant `py_compile` process: executing or importing a Python module
already parses it. Standalone `py_compile` entries remain only where they
provide the script's sole automated coverage.

Evaluator tests that mutate Git state share one class-owned, immutable prepared
`guardrail-command-policy` baseline. Each mutable case derives an independent
shared-object clone with a sparse working tree containing the grader, its
public tests, and every path that the case creates or renames. The commit still
contains the complete candidate tree, so ancestry, rename, merge, scope, and
rewritten-history assertions use real Git. Do not add a mutable shared working
tree, make tests order-dependent, or replace those semantics with mocks. Tests
whose contract is candidate preparation itself continue to run the complete
export-and-initialize path.

The PR #105 Linux GCC reference run 33389737148 at `d9c6d7c6` reported a
114-second agent-test step (12:02:28--12:04:22 UTC), an 18.09-second CTest run,
and a 188-second job interval (12:02:01--12:05:09 UTC). PR #106 run
33395000182 at implementation SHA `8bdbb9e` reported 118 agent tests in
59.670 seconds, a 65-second agent-test step (13:05:22--13:06:27 UTC), a
17.42-second CTest run, and a 147-second job interval
(13:04:50--13:07:17 UTC). The observed step reduction was 49 seconds (43.0%)
and the observed job-interval reduction was 41 seconds (21.8%). Both runs had
warm ccache restores: the reference build recorded 119/121 hits and the
implementation run 120/121 hits. These are single hosted-runner samples, not a
stable performance distribution; the focused WSL-native ext4 comparison
supports the direction (193.113 seconds at `67a8a8c` versus 118.392 seconds at
`8bdbb9e`, with the same 118 discovered tests), while `/mnt/c` timings are not
representative.

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
build in `build/linux-gcc-debug`; `linux-gcc-debug-build` uses the build tool's
automatic parallelism (`jobs: 0`).
`linux-gcc-test` runs the existing CTest suite there because `cardqueue_overflow`
intentionally expects an assertion abort and therefore needs assertions enabled.
The preset file requires CMake 3.21 or newer; the source graph itself still
requires CMake 3.19. Native PowerShell/MSVC remains unverified and has no preset.

For a host-independent entry point, use the small build wrapper. It prefers a
native `cmake` executable and, when Windows has no native CMake, maps the active
worktree path and runs the complete Linux preset sequence through one WSL
shell. This removes the need to rediscover or hand-convert the worktree path:

```powershell
python tools/agent/build.py --target one_combat
python tools/agent/build.py --no-configure --target one_combat --target test
```

Override `--configure-preset` and `--build-preset` together for Debug or ccache
presets. Before using either checked-in ccache pair, the wrapper verifies that
`ccache` exists and that the preset's `$HOME/.cache/sts_ai/ccache` location (or
its nearest existing parent) is writable. If not, it prints
`ccache_fallback=...` and selects the matching ordinary Release or Debug pair
before configuration. The wrapper does not initialize submodules or hide other
build failures. The probe runs in the selected build environment: native Linux
for a native route, or inside WSL for a Windows-to-WSL route. If fallback is
needed with `--no-configure`, the wrapper forces configuration of the newly
selected ordinary binary directory before building it.

For repeated local builds across sibling Git worktrees, install `ccache` in the
WSL/Linux environment and use the opt-in cache presets:

```bash
cmake --preset linux-gcc-debug-ccache
cmake --build --preset linux-gcc-debug-ccache-build
ctest --preset linux-gcc-ccache-test

cmake --preset linux-gcc-release-ccache
cmake --build --preset linux-gcc-release-ccache-build
```

They keep ordinary presets unchanged and configure a bounded 1 GiB cache under
`$HOME/.cache/sts_ai/ccache`. `CCACHE_BASEDIR` is set to the common parent of
the current source worktree, which has been verified to share Debug entries
across sibling worktrees: at the same SHA, the first 61-call build had 61
misses and the second had 59 direct hits (96.72%) and 2 misses. Verify the
active cache explicitly when diagnosing a different toolchain or path layout:

```bash
ccache --dir "$HOME/.cache/sts_ai/ccache" --zero-stats
cmake --build --preset linux-gcc-debug-ccache-build --target one_combat
ccache --dir "$HOME/.cache/sts_ai/ccache" --show-stats
```

During iteration, build only affected focused targets; perform the required
complete build/test pass once before handoff. Never share one CMake binary
directory between worktrees.

To build a clean baseline executable without registering another worktree, use
the archive helper:

```bash
python tools/agent/baseline_build.py BASELINE_REF --target one_combat
```

It resolves the ref to a commit, exports the superproject plus the two pinned
submodule revisions into a temporary directory, configures/builds the ordinary
Release preset, and copies the executable to
`build/baselines/<commit-prefix>/one_combat`. It refuses to overwrite an
existing artifact. The required submodule commit objects must already exist in
the current checkout; the helper does not fetch or mutate Git metadata. For a
CMake target whose executable uses a different `OUTPUT_NAME`, pass that name
explicitly, for example `--target unit-test --artifact-name test`.

For the Linux Debug ccache lane, the intended focused-then-full sequence is:

```bash
# Repeat focused builds while implementing.
cmake --preset linux-gcc-debug-ccache
cmake --build --preset linux-gcc-debug-ccache-build -j2 --target one_combat

# Before full CTest, build every default target so all test executables exist.
cmake --build --preset linux-gcc-debug-ccache-build -j2
PATH="$PWD/.venv/bin:$PATH" \
  ctest --preset linux-gcc-ccache-test --output-on-failure
```

Do not run the full CTest preset after building only `one_combat`; CTest
registers other native executables and correctly reports them missing.

On this Windows-hosted repository, use Windows Git for Git operations in linked
worktrees created by Windows Git. Their `.git` files contain Windows paths that
WSL Git may not resolve. Use WSL for the checked-in Linux/GCC CMake presets,
compiler, CTest, and Bash/Python checks; do not assume the two Git clients are
interchangeable until `git rev-parse --show-toplevel` succeeds in the chosen
environment.

Use this boundary when working from PowerShell; replace the WSL path with the
absolute `/mnt/<drive>/...` path for the active worktree:

```powershell
# Windows Git: checkout, submodules, status, and publication.
git status --short --branch
git rev-parse --show-toplevel
python tools/agent/worktree.py repair .

# WSL: one explicit Linux build/test command; do not run Git here.
wsl.exe -e bash -lc 'cd /mnt/c/path/to/worktree && cmake --preset linux-gcc-debug && cmake --build --preset linux-gcc-debug-build && ctest --preset linux-gcc-test --output-on-failure'

# Windows Git again: final review before staging or publication.
git diff --check
git status --short --branch
```

For initial repository searches, prefer tracked and scoped paths so generated
build trees, ignored experiment data, and model artifacts do not consume the
context budget:

```bash
git grep -n "pattern" -- src include apps tools docs/knowledge-base
```

Before trusting an analyzer result, verify the locked Python environment and
run the analyzer's self-test. Add the dependency group required by the script;
for `paired_analysis.py`, use:

```bash
uv sync --locked --extra analysis
uv run --locked --extra analysis python paired_analysis.py --self-test
```

A build line such as `Linking CXX executable one_combat` is progress, not proof
of completion. Retain the running command/session, poll until it exits, and
record the exit status. For ordinary compile-and-smoke-test iteration, that exit
status and the expected executable path are sufficient; use `file` when the
path or binary format is uncertain. Record `sha256sum` only when freezing a
binary for benchmark or other reproducibility/provenance evidence.

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
compilation time; local builds gain the same behavior only through the opt-in
`*-ccache` presets above. In CI, ccache is installed from Ubuntu packages and
activated via
`CMAKE_CXX_COMPILER_LAUNCHER=ccache` and `CCACHE_COMPILERCHECK=content` at the
job level. The
`${{ github.workspace }}/.ccache` directory is cached by `actions/cache@v4`
with a per-commit key `ccache-${{ runner.os }}-${{ runner.arch }}-gcc-${{ github.sha }}`
and a restore-key prefix `ccache-${{ runner.os }}-${{ runner.arch }}-gcc-`; the
cache is bounded to 1 GiB via `CCACHE_MAXSIZE`. Statistics are zeroed before
the build and printed after the build (with `if: always`) for measurement.

After pushing, inspect CI with a nonblocking `gh run view` or `gh pr checks`
query. Do not use an unbounded foreground `--watch`; poll at a bounded interval
so the session remains responsive while a run is queued or executing.

### Decision-bearing GCP run preflight

For a multi-arm research run, copy
`tools/agent/research_run_manifest.example.json` to a task-scoped file and fill
in the frozen full Git SHA, remote checkout/build paths, executable and artifact
SHA-256 hashes, exact `bestbench` seed block, required environment, and every
arm's unique result/log path. Keep parameters shared across arms in
`common_env` and `command`; arm-local `env` should contain only the intended
treatment. If Silver telemetry is expected, retain both
`expect_silver_telemetry: true` and `STS_SILVER_TELEMETRY` in `required_env`.
The validator rejects an absent, empty, or zero telemetry setting before a
seed can run.

Use this sequence after CI and before gameplay:

```bash
python tools/agent/gcp_benchmark.py manifest-check path/to/run-manifest.json
python tools/agent/gcp_benchmark.py copy-to local/model.txt artifacts/model.txt --expect-sha256 <sha256>
python tools/agent/gcp_benchmark.py exact-sha-preflight path/to/run-manifest.json
python tools/agent/gcp_benchmark.py run-manifest path/to/run-manifest.json A --foreground --guard-only
python tools/agent/gcp_benchmark.py run-manifest path/to/run-manifest.json A
```

The exact-SHA preflight fails unless the designated checkout has the frozen
HEAD, no tracked modifications, a CMake cache bound to that checkout, and the
declared binary/artifact hashes. The manifest launcher routes through the
existing seed guard and refuses any arm whose result, metadata sidecar, or log
already exists. It does not replace the experiment-specific post-run canary:
validate completed results with `tools/agent/check_benchmark_canary.py` and the
required scientific analyzer before interpreting them.

`selfplay/loop.sh` still defaults to `build/one_combat` (overridable via
`ONE_COMBAT_BIN`/`STS_BIN`). Set either variable to
`build/linux-gcc-release/one_combat` when using the checked-in preset.

### Python tooling environment

`pyproject.toml` and `uv.lock` describe direct dependencies used by maintained
repository scripts; this repository is not packaged as a Python module. The
default environment contains only NumPy. The Linux GCC CI job additionally
installs the locked `analysis` extra because CTest includes pandas/SciPy
self-tests.

Sibling worktrees can reuse one locked environment rather than reinstalling
the CTest dependencies in every ignored `.venv`. Bootstrap it from any
checkout:

```bash
tools/agent/bootstrap_python.sh
```

The command hashes `uv.lock`, syncs the locked `analysis` environment under the
parent of uv's cache directory (normally
`~/.cache/sts_ai/venvs/<lock-hash>`), and creates an ignored `.venv` symlink in
the current checkout. Worktrees with the same lock share an environment;
branches with different locks cannot mutate each other's packages. Set
`STS_AI_SHARED_VENV_ROOT` to override the cache root. The command refuses to
overwrite an existing private `.venv`; move that environment aside explicitly
before switching to the shared one.

For Codex-app-managed worktrees, add this command after the existing submodule
check/repair commands in the project's Linux Environment setup script:

```bash
tools/agent/bootstrap_python.sh
```

Codex runs that setup for each new app-managed worktree. The first invocation
creates or refreshes the shared locked environment; later worktrees reuse it
and create only their local `.venv` link. Keep this in the Codex Environment
configuration rather than a Git hook so ordinary checkouts do not silently run
environment setup. `.codex/environments/environment.toml` is generated by the
app and must not be edited manually.

Install additional direct-dependency groups only for tooling that needs them;
these direct commands use a checkout-local environment unless
`UV_PROJECT_ENVIRONMENT` points at the shared environment:

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

### Core object reuse (2026-08-14, extended 2026-08-24)

Phase 6 introduced `sts_core_objects` to compile each common `src/*.cpp`
translation unit once and reuse its object files across the five native
executables. The 2026-08-24 follow-up initially reused PIC objects in
`slaythespire`, but a matched Release throughput check measured an 8.8% CPU
slowdown in the native executable. The accepted design keeps native objects
non-PIC and gives `slaythespire` a separate hidden/PIC object collection; this
preserves native Release throughput at the cost of one module-side core
compilation when Python development headers are enabled. The original serial
Debug measurement used
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

`./build/one_combat` requires an explicit mode. Use a focused non-seed mode for
launch-only checks, or route any game-seed execution through
`tools/seed_guard.sh` (`apps/one_combat.cpp::main`).

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

### Exact-SHA remote worktree and runtime provenance

Do not treat a binary built after copying a few files into the designated
remote root as frozen-SHA evidence. The root may have an older surrounding
source/link graph, and a copied CMake cache can retain an absolute source path
to a different preserved run tree. In non-manifest runs where
`STS_EXECUTABLE_GIT_SHA` is unset, executable provenance falls back to
`git rev-parse HEAD` and can therefore describe the launcher's unrelated
working-directory checkout. Manifest-bound runs avoid that ambiguity by
requiring the declared executable SHA to equal the frozen SHA.

For a reviewed scientific run, create a clean, uniquely named remote worktree
at the exact reviewed commit and configure a new cache inside it. Prefer a
normal fetch when the remote clone can reach the task branch. Some preserved
run clones intentionally use an offline bundle as `origin`; if the branch is
absent there, create a local Git bundle for the reviewed branch and upload it
with `copy-to`, then fetch that bundle into the preserved clone. Example
placeholders below must be replaced with the recorded task values:

```bash
# Local: bundle only when the preserved remote clone cannot fetch the branch.
git bundle create build/<experiment>/<sha>.bundle <task-branch>
python3 tools/agent/gcp_benchmark.py copy-to \
  build/<experiment>/<sha>.bundle runs/<sha>.bundle

# Remote through `gcp_benchmark.py run --foreground --`:
git -C runs/<preserved-clone> fetch \
  /home/philippherrmann/sts_sweep/runs/<sha>.bundle \
  <task-branch>:refs/remotes/bundle/<experiment>
git -C runs/<preserved-clone> worktree add --detach \
  ../<experiment>-<sha> <full-reviewed-sha>
cmake -S runs/<experiment>-<sha> \
  -B runs/<experiment>-<sha>/build-release \
  -DCMAKE_BUILD_TYPE=Release
cmake --build runs/<experiment>-<sha>/build-release \
  --target one_combat <focused-test-target> -j 24
```

Initialize the new worktree's pinned submodules before configuring. If the
preserved offline clone cannot update them normally, copying their contents
from the verified baseline clone is a mechanical fallback only after checking
that the gitlink SHAs match; never use dependency presence as proof of the
expected revision.

The launcher must still start from the designated root so
`tools/seed_guard.sh --gcp-research` can verify its host/root context. Supply
the exact worktree's Git metadata to the benchmark process so runtime sidecars
resolve the reviewed SHA rather than the designated root's SHA. Obtain the
absolute git directory from the worktree's `.git` pointer or with
`git -C runs/<experiment>-<sha> rev-parse --absolute-git-dir`, then include:

```bash
/usr/bin/env \
  GIT_DIR=/absolute/path/to/the/worktree/gitdir \
  GIT_WORK_TREE=/home/philippherrmann/sts_sweep/runs/<experiment>-<sha> \
  STS_EXECUTABLE_GIT_SHA=<full-reviewed-sha> \
  runs/<experiment>-<sha>/build-release/one_combat \
  bestbench <sims> <nSeeds> <asc> <seedOffset> <results.csv>
```

`STS_EXECUTABLE_GIT_SHA` supplies the reviewed executable identity to training,
benchmark, and OOC producer provenance, including teacher validation and
result sidecars. `GIT_DIR` and `GIT_WORK_TREE` remain required for Git-derived
dirty-state diagnostics and commands other than the executable SHA. Before a
cohort:

1. run the focused executable test from the exact-SHA build;
2. hash the exact binary and every model/config artifact;
3. run one fresh treatment canary through the guarded launcher;
4. retrieve its CSV, `.meta.json`, and persisted launcher log; and
5. run `tools/agent/check_benchmark_canary.py` with the expected full Git SHA,
   binary SHA-256, backend, seed, simulations, thread count, fair regime, and
   reuse-cap mode.

The canary is invalid if its sidecar names another Git SHA even when the binary
hash is recorded. Use a fresh output filename for every corrected canary;
`bestbench` deliberately refuses overlapping rows in an existing result file.
Keep invalid canary attempts in the evidence record rather than silently
replacing them.

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
`remote_pid` and `remote_log`, and survive SSH disconnects. Inspect the PID and
retrieve or upload one file through the same designated-target launcher. Remote
paths are relative to the designated root; absolute and parent-traversing paths
are rejected. Each path component is limited to ASCII letters, digits, `.`,
`_`, and `-`, so SCP glob, control, and remote-shell syntax is rejected:

```bash
python3 tools/agent/gcp_benchmark.py job-status <remote-pid>
python3 tools/agent/gcp_benchmark.py copy-from logs/<log> ./local-run.log
python3 tools/agent/gcp_benchmark.py copy-from pilot-artifacts/<run>/summary.json ./summary.json
python3 tools/agent/gcp_benchmark.py copy-to ./runner.sh pilot-artifacts/<run>/runner.sh
```

`job-status` reports `running` only while the operating-system PID exists;
`not_running_or_unknown` means the process is absent, not that it necessarily
succeeded. Use the fetched log and validated output artifacts for completion.
Transfer confinement is lexical and assumes the maintained designated checkout
does not place escaping symlinks in paths supplied to these commands.

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
