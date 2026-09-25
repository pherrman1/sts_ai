# ADR-0021: Native Silver search on the main engine is the default

Date: 2026-09-24
Status: accepted

Amends: [ADR-0020](0020-silver-only-combat-remove-searcher2-and-selfplay.md),
which made the vendored Silver model the only combat searcher. Silver stays the
only search algorithm; this ADR changes which engine it runs on.

## Context

The vendored Silver backend searches in a private copy of a different
`sts_lightspeed` fork and converts every live decision into it. The project
chose to merge the two simulators so there is one rule set. The main engine
gained value-type actions, search equality/hashing, an information-set draw
pile and deferred Runic Dome rolls, and Silver's production search was ported
onto it (`SilverSearcher`, `NativeSilverBackend`). On the standard 128-seed
block the port won 86/128 against the vendored 83/128 (paired +2.3 pp, 95% CI
[−6.2, +10.9] pp; ledger §348).

## Decision

- `one_combat` installs the native backend by default.
- `STS_NATIVE_SILVER=0` selects the vendored backend.
- The vendored backend is also selected automatically when any `STS_SILVER_*`
  option that only it implements is set (captures, diagnostics, telemetry,
  leaf VNet, root prior, reuse-cap overrides, exact budgets). The run prints
  which option selected it. `STS_SILVER_SEARCH`, `STS_SILVER_ADAPTIVE`,
  `STS_SILVER_ADAPTIVE_TOP_GAP` and `STS_SILVER_ADAPTIVE_RETAINED_ONLY=1` work
  with both backends.
- `STS_NATIVE_SILVER=1` together with a vendored-only option is an error.
- Bestbench metadata records `effectiveCombatBackend="native_silver"` for the
  native backend.
- Generators that pin the vendored model for teacher provenance
  (`wholecombatgen` and related combat-dataset modes) keep installing it.

## Rationale

The native backend plays as well as the vendored one within the measured
uncertainty and runs Silver's search against the rules the agent actually plays
by. Research producers depend on vendored-only features and provenance
(Silver telemetry, captures, pinned upstream SHA); selecting the vendored
backend for them keeps their contracts valid until they are ported or retired.

## Alternatives considered

- Keep native opt-in until a larger gate. Rejected: the 128-seed gate shows no
  regression, and running both as equals delays removing the second rule set.
- Fail when a vendored-only option is set without `STS_NATIVE_SILVER=0`.
  Rejected: it would break every existing research manifest at once.

## Consequences

- New plain `run`/`bestbench` results are a native-Silver series; compare them
  with vendored rows only as paired, labelled comparisons.
- The vendored engine, bridge and research tools remain until a follow-up
  decides to port or retire each consumer (live advisor, Silver research tools).
- Remaining modelling differences from the vendored backend: Gambling Chip and
  Purity selections are atomic subsets, and reroot uses multiset equality plus
  action translation instead of the vendored repairs.

## Affected files

- `apps/one_combat.cpp` (backend selection)
- `src/sim/search/NativeSilverBackend.cpp`, `src/sim/search/SilverSearcher.cpp`

## Evidence

- Ledger §348: native 86/128 vs vendored 83/128 on seeds 126700–126827.
- Local checks for this change: the default bestbench records
  `native_silver`; `STS_NATIVE_SILVER=0` and `STS_SILVER_TELEMETRY=1` give
  vendored rows identical to the reference; the conflicting combination exits
  with status 2.
