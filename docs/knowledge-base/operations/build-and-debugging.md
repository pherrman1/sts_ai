# Build and debugging

Last verified: 2026-10-08 for the actual CI trigger and label selection; 2026-09-26 for local research execution (ADR-0024); 2026-09-24 for the Searcher2/3 and self-play removals; 2026-09-10 against the current working tree.

## Purpose

Document the actual CMake graph, checkout-specific dependency limitations,
manual checks, model-load diagnostics, and tracing boundaries.

## Current implementation

`CMakeLists.txt` requires CMake 3.19 and C++20. All configurations retain
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

OpenSSL Crypto is optional at configure time. CMake links it to targets that
compile the CTM runtime when it is available; without it, unrelated targets
such as `main` still configure and build, while CTM runtime targets require the
OpenSSL headers and Crypto library.

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
known subcommand runs the targeted search/terminal checks; unknown
subcommands fail nonzero (see
[`architecture/combat-search.md`](../architecture/combat-search.md)).
`apps/parity_test.cpp` has a CMake target `parity_test`; `parity_test.py`
locates the binary via `STS_PARITY_BIN` or `build/parity_test`.

CTest labels provide focused local verification tiers. The current CI gate
selects `core|smoke`; the other labels remain available for affected interfaces:

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
CTest suite. Tests that import torch, xgboost, scipy or sklearn also carry
`needs-ml-python` (list at the end of `CMakeLists.txt`). Cloud containers lack
those packages, so run `ctest -LE needs-ml-python` there; a remaining failure
is then real. In a Release build `cardqueue_overflow` still fails by design
(it needs assertions).

The following complete `tests/agent` discovery is available for changes to
agent tooling. It was a historical CI step; the current workflow does not run it:

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
build in `build/linux-gcc-debug`. Its `jobs: 0` setting requests parallel
building without a job count; with GNU Make this permits unlimited jobs.
CI overrides that preset with `--parallel 2` to bound build concurrency on
the hosted runner. Local builds should pass an explicit `--parallel N`
appropriate to the host's available CPU and memory.
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

`linux-gcc-release-x86-64-v3` (build preset `linux-gcc-x86-64-v3-build`,
binary dir `build/linux-gcc-release-x86-64-v3`) is the Release build with
`-march=x86-64-v3 -mno-fma`. `-mno-fma` keeps every multiply and add separately
rounded, so results match the ordinary Release build. On 2026-10-21 Silver
decisions were identical on fixed A20 seeds, and real combats ran about 10%
faster. The binary needs an AVX2 CPU (the cloud containers have one). It is the
default for cloud campaigns whose `code_commit` contains
`tools/cloud/default_configure_preset`; older frozen campaigns keep
`linux-gcc-release`, and the manifest key `configure_preset` overrides both
(`tools/cloud/README.md`). Local and live builds still default to
`linux-gcc-release`.

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
check passes. It runs one Linux GCC lane on non-draft pull requests to `main`
for opened, synchronize, reopened and ready-for-review events, excluding
docs-only changes. Draft pull requests skip the job; a draft handoff therefore
does not establish a CI pass. The lane performs:
recursive submodule checkout,
`build-essential`/CMake/CPython development prerequisites plus ccache, Python 3.12 and uv,
`uv lock --check`, `uv sync --locked --extra analysis`, the read-only
`tools/agent/doctor.sh`, repository-health comparison and its unit tests,
and the checked-in Debug configure/build with
`ctest --preset linux-gcc-test -L 'core|smoke'`. The workflow adds
the synced `.venv/bin` to `PATH` before CTest so its existing `python3` commands
use the locked environment; all test failures remain fatal and CTest
prints failure output through its preset.

This lane deliberately does not run statistical gameplay seed benchmarks, access
private cloud resources, use ignored training checkpoints, or deploy. Its
dependency environment includes the analysis extra; trained-model parity
remains outside CI because it requires a produced
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

### Decision-bearing research run preflight

Use the smallest justified experiment. Larger local runs require explicit
authorization; record frozen source/model/binary provenance, exact seed
ranges/counts, budgets, and decision rules before execution. There is no fixed
local numerical seed ceiling.

Before collecting a cohort:

1. Freeze the reviewed full source SHA, exact checkout and build paths, binary
   and model/configuration SHA-256 hashes, complete per-arm command/environment,
   exact seed ranges/counts, simulation budgets, worker/thread and wall/CPU
   budgets, outputs, and scientific decision rules in the experiment manifest.
2. Verify the checkout is clean at that SHA, pinned dependencies match, and the
   CMake cache belongs to that checkout. Hash the actual executable and every
   model/configuration artifact. A source SHA alone does not prove binary identity.
3. Use a clean explicit environment (for example `env -i` with `HOME`, `PATH`
   and all required settings) so inherited model-routing variables cannot leak
   between arms. Set `STS_EXECUTABLE_GIT_SHA` to the verified producer SHA.
4. Invoke `tools/seed_guard.sh` from the frozen checkout. Its `guard-only` mode
   validates recognized seed counts without executing gameplay. It imposes no
   general numeric ceiling; semantic capture/evaluation retain their native
   1..16 source/decision contract. Guard acceptance is not run authorization
   and does not verify provenance or the scientific design.
5. Reserve fresh per-arm result, metadata, trace and log paths; reject existing
   files (including dangling symlinks). Preserve failed attempts. Check active
   processes and capacity before starting an explicitly authorized larger run.
6. Run the smallest justified mechanism/provenance canary, then validate its
   CSV and sidecar with `tools/agent/check_benchmark_canary.py` against the
   expected source/binary hashes, backend, seed, simulations, threads, fair
   regime and reuse mode. Use the scientific analyzer for the final cohort.

The old host-specific launcher and its JSON launcher template are retired by
[ADR-0024](../../../decisions/0024-local-research-execution.md). Frozen historical
manifests remain evidence, not runnable current workflow templates. Keep
experiment-specific manifests and validators; do not infer completion from a
PID disappearing. Verify exit status, logs, output completeness and provenance.

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

### Opt-in GCC profile-guided Release experiment

`STS_PGO_MODE` defaults to `OFF`. `GENERATE` and `USE` require a single-config
GNU Release build and an absolute `STS_PGO_PROFILE_DIR`. Existing `-O3`/LTO
remain enabled; this option adds neither fast math nor CPU-specific flags.
Generation uses atomic counters for OpenMP workers. Use mode rejects an empty
profile directory at configure time and treats missing or mismatched object
profiles as compiler errors, rather than silently accepting unprofiled code.

Use a dedicated build directory and retain it across the two phases: GCC's
profile names encode object paths. Keep the source revision, compiler,
generator, build directory, and other flags fixed. Start with a fresh profile
directory for each experiment; do not mix profiles from different revisions.

```bash
cmake -S . -B build/pgo -DCMAKE_BUILD_TYPE=Release \
  -DSTS_PGO_MODE=GENERATE -DSTS_PGO_PROFILE_DIR="$PWD/build/pgo-profiles"
cmake --build build/pgo --target one_combat -j2
# Run the instrumented binary on representative, guarded Silver producer
# workloads here, preserving the frozen teacher settings and refreshing its
# executable hash. Wait for normal process exit so GCC writes the profiles.
cmake -S . -B build/pgo -DCMAKE_BUILD_TYPE=Release \
  -DSTS_PGO_MODE=USE -DSTS_PGO_PROFILE_DIR="$PWD/build/pgo-profiles"
cmake --build build/pgo --target one_combat -j2
```

Collect profiles for every translation unit rebuilt in USE mode, including
static-library members that `one_combat` does not pull into its final link.
Building additional targets in USE mode
without collecting their profiles intentionally fails. Profile existence alone
does not establish workload representativeness or a performance improvement.
Compare the final USE binary against ordinary Release on held-out workloads,
with separate trace/label parity checks and interleaved CPU-pinned timing;
never compare throughput against the instrumented collection binary. Refresh
teacher/producer executable hashes for each binary, and keep all seed-driving
commands under `tools/seed_guard.sh` (seed-count validation).

The Release preset produces `build/linux-gcc-release/one_combat`. The path does
not prove a running producer is optimized: inspect the actual job command,
`CMakeCache.txt`, generated compile flags, and binary hash on its host before
drawing a production conclusion. PGO remains an experimental build option;
no production speedup is established by enabling it.

### Focused OOC sampling parity and timing

The offline `combat_transition_runtime_probe MODEL FIXTURES smoke` compares
uncached and prepared draws over 32 seeds and four sequential draws per captured
fixture, including complete persistent state and planner RNG post-state. It also
reports preparation and repeated sampling timing and encoder counts. Supply the
frozen native model and matching captured JSONL explicitly; the loader CTest uses
malformed artifacts and does not replace real-model parity.

`one_combat oocmctsselftest` optionally accepts
`STS_OOC_MCTS_MICROBENCH_MODEL=/absolute/path/to/combat_transition_v1.native`.
With the normal native V4/win test setup, this runs a fixed 512-simulation,
map-checkpoint detached native-search fixture. It compares the uncached sampler with
edge preparation, checks all root statistics/tree counters/snapshots/history,
and prints `MICROBENCH` timing/counters plus `MICROBENCH_PARITY` exact outputs.
The native regain-control callback isolates searched combat from reward
projection; these timings are a microbenchmark, not gameplay qualification.
Use `tools/seed_guard.sh` for this executable self-test as for the registered
adapter CTest. No profile environment variable affects live search configuration.

### Offline historical compression audit

`one_combat ooccompressionaudit INPUT OUTPUT [--values]` is a research-only
reward-screen audit, separate from gameplay. The input envelope retains the
#844 public record and trace; the tool restores public act and zero misc only
for decks without misc-bearing cards, reconstructs reward candidates and
requires complete native public-record equality. It reports normalized
semantic prior probabilities (raw model weights separately), action identity,
and permanent-deck/cycle-burden before and after each candidate.

The current deployed `heart1full` prior and rollout3 native/M0 configuration
must be loaded; prior fallback is rejected. Without `--values` it performs no
leaf evaluations. With it, only a matching initial Neow reward may run the
existing 64-particle CRN root evaluator. Later historical public projections
lack exact snapshots and are never used for transitions or values. Invoke
through `tools/seed_guard.sh`; the experiment's explicit-environment launcher,
input custody and fixed gates are in
[`prior_anchor_compression_20261025`](../../experiments/evidence/prior_anchor_compression_20261025/PREREG.md).
This audit does not change root routing, search defaults or gameplay.

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
./build/small-test isbattleover
bash tools/seed_guard.sh ./build/one_combat bestbench 1000 8 0
ctest --test-dir build --output-on-failure
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

## Research execution

The former GCP server is unavailable and its workflow is retired. Do not wait
for or restore it. Use the local research preflight above and explicit
larger-run authorization; historical cloud commands are provenance only.

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
- `src/sim/search/CombatDistValueNet.cpp` BLAS initialization
