# Issue 12: Clean clone cannot configure (json/pybind11 absent)

- **Status:** closed
- **Tier:** High
- **Last verified:** 2026-08-02
- **Source:** [`operations/build-and-debugging.md`](../operations/build-and-debugging.md), "Known limitations"

## Symptom

`.gitmodules` declares `json/` and `pybind11/`, but the git index contains no
gitlinks for either and both root directories are absent. `CMakeLists.txt`
requires them via `add_subdirectory`, so a fresh configure from this checkout
lacks required sources. A tracked standalone JSON header exists at
`extern/nlohmann/json.hpp`, but CMake does not use it as a complete replacement.

## Evidence

- `.gitmodules` entries; `git ls-files` shows no `json/`/`pybind11/` gitlinks.
- `CMakeLists.txt`: `add_subdirectory(json)` / `add_subdirectory(pybind11)`.
- `build-and-debugging.md` "Known limitations".

## Why it matters

A fresh checkout cannot build without undocumented manual steps. This blocks
reproducible builds, CI, and any collaborator, and is a prerequisite for the
clean-configure baseline used to validate experiments.

## Candidate fix direction

Vendor the dependencies, restore real gitlinks, or switch to fetched CMake
dependencies; decide via the open question in `build-and-debugging.md`.

## Relevant code

- `.gitmodules`, `CMakeLists.txt`
- `extern/nlohmann/json.hpp`

## Resolution (2026-08-02)

Fixed: `json` and `pybind11` restored as real gitlinks (pinned `2222d386`, `63d627c5`); the pybind11 module is guarded on `find_package(Python)` so core targets build without Python dev headers. Clean configure + full build verified on 2026-08-02.

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
