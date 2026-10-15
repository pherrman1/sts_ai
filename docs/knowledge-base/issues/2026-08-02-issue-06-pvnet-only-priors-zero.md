# Issue 06: PVNet-only multi-edge priors are zero

- **Status:** closed
- **Tier:** Critical
- **Last verified:** 2026-08-02
- **Source:** [`architecture/combat-search.md`](../architecture/combat-search.md), "Known limitations"; [`evaluation/current-baselines.md`](../evaluation/current-baselines.md)

## Symptom

Node expansion invokes `computeEdgePriors` only when the separate policy net is
loaded, while PUCT activation also recognizes a loaded PVNet. With
`STS_POLICY=0` and only `STS_PVNET` set, multi-edge PVNet priors remain zero and
PVNet policy evidence is silently unavailable.

## Evidence

- `src/sim/search/BattleScumSearcher3.cpp::step` (line 227): `computeEdgePriors`
  is gated on the policy-net flag.
- `src/sim/search/BattleScumSearcher3.cpp::selectBestEdgePUCT`: recognizes a
  loaded PVNet for selection.
- `current-baselines.md`: "Current Searcher3 expansion calls `computeEdgePriors`
  only when the separate policy net is loaded."

## Why it matters

The recorded PVNet sweep's policy head results (§ "Phase 4b PVNet alpha sweep")
depend on this enabling condition. Anyone running PVNet-only configuration
believes the PV policy head guides search when it contributes nothing at
multi-edge nodes.

## Candidate fix direction

Let PVNet priors be computed when either the policy net or the PVNet policy head
is active; document precedence when both exist.

## Relevant code

- `src/sim/search/BattleScumSearcher3.cpp::step`, `computeEdgePriors`,
  `selectBestEdgePUCT`
- `apps/one_combat.cpp::main` (`STS_POLICY`, `STS_PVNET` parsing)

## Resolution (2026-08-02)

Fixed: `computeEdgePriors` runs when the separate policy net OR a PVNet with its policy head enabled is loaded; PVNet policy head takes precedence. Residual quirk: `STS_PVNET_VALUE_ONLY=1` still leaves zero priors while PUCT recognizes the PVNet (documented in `combat-search.md`).

## Closed by

*Fixed in the 2026-08-02 working tree (uncommitted); re-run the referenced focused checks before committing.*
