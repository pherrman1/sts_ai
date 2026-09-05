# Policy prior

Last verified: 2026-08-11.

## Purpose / research question

Can a learned policy prior (action probabilities from a GBM) improve PUCT
action allocation over uniform priors?

## Current conclusion

**The compact GBM policy prior is deployed and auto-loads.** It provides
+4.3pp win over plain UCB (§26). The prior uses 14 combat action features
(card type, cost, damage, block, etc.) trained on fair combat data.

**The v2 prior (22 features) was rejected.** It had better offline CE/KL
metrics but did not transfer to online gameplay: −2.0pp vs the tracked
prior on 256 paired seeds (§127). This is the second documented case of
offline≠online transfer (after §124c prior-guided rollouts, before §133
utility-R vnet).

**Prior-guided S3 rollouts were falsified** at −7.0pp (§124c). The GBM prior
as a rollout policy sampler is worse than the static heuristic rollout weights
at 2.7× cpu.

## Evidence map

| When | Evidence | Result |
| --- | --- | --- |
| 2026-07-15 | [§26 Known-RNG comparator](../../../../docs/experiments/ledger-01.md) | Compact policy prior +4.3pp over plain UCB |
| 2026-07-23 | [§58 Shared-state entity policy prior](../../../../docs/experiments/ledger-02.md) | Promising offline, not promoted at 500 paired seeds |
| 2026-08-05 | [§103 S2+PVNet policy head as PUCT prior](../../../../docs/experiments/ledger-04.md) | Exact tie with GBM prior at 8× cost |
| 2026-08-07 | [§124c Prior-guided rollouts](../../../../docs/experiments/ledger-05.md) | FALSIFIED: −7.0pp at 2.7× cpu |
| 2026-08-07 | [§127 Policy prior v2 pipeline](../../../../docs/experiments/ledger-05.md) | NULL: better offline CE/KL does not transfer (−2.0pp n.s.) |
| 2026-08-07 | Decision: prior v2 pipeline | Line closed; tracked prior stays deployed |

## Rejected / falsified approaches

- **Prior v2 (22 features)** — better offline, null online (§127)
- **Prior-guided S3 rollouts** — significantly negative (§124c)
- **PVNet neural policy prior** — tie with GBM at 8× cost (§103)
- **Policy-head search distillation** — falsified at gates (§104)

## Relationships

- [searcher3.md](../combat-search/searcher3.md) — prior is used inside PUCT selection
- [pvnet-and-alternatives.md](pvnet-and-alternatives.md) — PVNet provides both policy+value heads
- [leaf-evaluation.md](../combat-search/leaf-evaluation.md) — rollout policy interacts with prior

## Current implementation

The tracked prior is `models/policy_trees_c.txt` (sha256
`24793bd39dd1a35c8865035e458c3aa40616ef021cb26b05f914f72fb5e5a321`).
It auto-loads in both Searcher2 and Searcher3. The prior is a compact
GBM tree ensemble; it does not require PVNet or any neural runtime.

## Open questions

- Can offline CE/KL improvements be made to transfer online? (pattern: §124c, §127, §133 all show offline≠online)
- Would a neural prior with better online calibration close the gap with VNet?
