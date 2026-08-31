# Test-suite tiering and duplicate removal

Date: 2026-08-31

## Decision

Keep the inexpensive native simulator regressions and the offline analyzers
that still implement maintained evidence contracts. Reduce routine test cost
by assigning each Python test family one CI owner, removing compile-only
processes when a behavioral test already imports or executes the module, and
labeling CTest entries as `smoke`, `core`, `integration`, `tooling`, or
`research-repro`.

The unfiltered `linux-gcc-test` preset remains the authoritative CTest gate.
The separate pre-build unittest discovery command owns `tests/agent`; CTest no
longer repeats selected modules from that directory. The native test
dispatcher rejects unknown commands so a misspelled CTest registration cannot
silently pass.

## Evidence and scope

- `CMakeLists.txt` reduces the registered suite from 81 to 58 entries without
  removing a maintained behavioral assertion: 19 redundant Python parse
  processes and four duplicate CTest wrappers are removed. The wrappers had
  repeated five unittest modules already covered by discovery.
- A cold WSL build on the Windows-mounted checkout took 2,222.75 seconds while
  the initial 60-entry CTest measurement took 17.82 seconds. In that test run,
  the core label accounted for 1.72 seconds. These timings characterize this
  local filesystem/environment only; Linux CI timings remain authoritative.
- Dependency tracing retained the closed-research analyzers: maintained
  knowledge pages still name them, other maintained tools import them, or
  they regenerate recorded evidence. Closing a hypothesis is not sufficient
  reason to remove its reproducibility contract.

## Non-goals

- No simulator, search, gameplay, model, or research behavior changes.
- No removal of historical evidence or ignored research data.
- No change to the authoritative full CI gate.

## Relevant code

- `CMakeLists.txt`
- `.github/workflows/ci.yml`
- `apps/test.cpp::main`
- `docs/knowledge-base/operations/build-and-debugging.md`
