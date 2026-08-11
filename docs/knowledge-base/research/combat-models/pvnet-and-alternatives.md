# PVNet and alternative combat models

Last verified: 2026-08-11.

## Purpose / research question

Can a neural network providing both policy priors and a value leaf replace
or complement separate GBM models?

## Current conclusion

**PVNet does not have a deployed role.** The Phase 1 payoff gate at 3k sims
was negative — no S3+PVNet arm beats same-compute S2/S3, and the A–H
architecture sweep was stopped (§102).

The PVNet policy head as a PUCT prior ties the GBM prior at 8× cost (§103).
The PVNet value leaf is shadowed by the VNet default (VNet-first at the
blend site, PVNet in the else-if clause) since the §126 vnet promotion.

The 2026-07-30 "66.4% at 100 sims" headline from the Phase 4b sweep does
not reproduce on the current checkout (§72: 8.6% at 100 sims, α=0). The
historical sweep numbers should be treated as unreliable.

Other alternative combat architectures (DeepSets, mixture models, distributional
value nets, entity-aware models) were all rejected at gates or closed by evidence.

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-07-30 | [Phase 4b PVNet alpha sweep](../../../../docs/experiments/ledger-03.md) | 66.4% headline — doesn't reproduce (§72) |
| 2026-08-02 | [§72 PVNet re-check](../../../../docs/experiments/ledger-03.md) | 8.6% at 100 sims on current checkout |
| 2026-08-04 | [PVNet parity fixes](../../../decision-log/2026-08-04-combat-pvnet-parity-fixes.md) | 3 C++ inference bugs fixed |
| 2026-08-04 | [§101 PVNet parity fix + replication](../../../../docs/experiments/ledger-04.md) | 12.5% at 100 sims on fixed binary |
| 2026-08-04 | [§102 Phase 1 payoff gate](../../../../docs/experiments/ledger-04.md) | NEGATIVE: A–H sweep stopped; PVNet channel closed |
| 2026-08-05 | [§103 S2+PVNet PUCT priors](../../../../docs/experiments/ledger-04.md) | Exact tie with GBM prior at 8× cost |
| 2026-08-09 | [§157 DeepSets combat VNet parity](../../../../docs/experiments/ledger-06.md) | RMSE 8.66, online 0% win |
| 2026-08-09 | [§158 DeepSets collapse diagnosis](../../../../docs/experiments/ledger-06.md) | Numerically collapses on OOD search states |
| 2026-08-07 | [§128 Value-only utility-distribution model](../../../../docs/experiments/ledger-05.md) | Better win calibration but vnet owns the leaf |
| 2026-08-04 | [§97 Combat value under gate stack](../../../../docs/experiments/ledger-03.md) | Old-era vnet rejected |
| 2026-07-22 | [§56 Distilled native combat MLP](../../../../docs/experiments/ledger-02.md) | Rejected at 500 paired seeds |
| 2026-07-22 | [§57 Entity-aware multi-head combat model](../../../../docs/experiments/ledger-02.md) | Rejected at 500 paired seeds |
| 2026-08-07 | [PVNet deployment-speed knobs](../../../decision-log/2026-08-07-pvnet-deployment-speed.md) | `STS_PVNET_CACHE` default ON (behavior-preserving); conditional gating experimental |

## Rejected / falsified approaches

- **PVNet as primary combat architecture** — Phase 1 gate negative (§102), A–H stopped
- **PVNet policy head as PUCT prior** — ties GBM at 8× cost (§103)
- **DeepSets combat VNet** — collapses on OOD search states (§157/§158)
- **Distilled native combat MLP** — rejected at 500 paired seeds (§56)
- **Entity-aware multi-head combat model** — rejected at 500 paired seeds (§57)
- **Entity-aware joint meta value model** — floor head rejected; win head inconclusive (§59)

## Relationships

- [vnet.md](vnet.md) — VNet is the deployed combat value model; PVNet is in the else-if
- [policy-prior.md](policy-prior.md) — PVNet policy head vs GBM prior
- [leaf-evaluation.md](../combat-search/leaf-evaluation.md) — PVNet value leaf at the blend site
- [searcher3.md](../combat-search/searcher3.md) — PVNet consumed only by Searcher3 (value leaf) and Searcher2 (policy priors since 2026-08-05)

## Current implementation

- `STS_PVNET=<path>` loads jointly for policy priors (S2+S3) and value leaf (S3 only)
- `STS_PVNET_ALPHA` controls blend weight
- `STS_PVNET_VALUE_ONLY` makes PVNet fully inert under Searcher2
- `STS_DIST_VNET` is consumed only by Searcher3
- `STS_PVNET_CACHE` is default ON (behavior-preserving visibleHash leaf cache)

See [`docs/knowledge-base/architecture/combat-search.md`](../../architecture/combat-search.md).

## Open questions

- Could PVNet be retrained with the current honest-data distribution and current searcher defaults?
- The Phase 4b producer provenance is unverified (no `STS_FAIR=1` in archived invocation).
