# Silver forced-action target audit (2026-09-19)

## Decision

The preregistered primary audit is
**`FORCED_ACTION_TARGET_PASS`**.  On 32 roots selected as two deterministic
hash-ranked roots from each of 16 fresh gameplay source seeds, the independent
forced-action label ensemble L (8 replicates at 5,000 continuation simulations)
improves on the frozen same-root Teacher-A label under a disjoint judge J
(8 replicates at 10,000 simulations).

This qualifies the forced-action ensemble as a target for a later bounded model
experiment.  It does not qualify a learned model, replay integration, gameplay,
or a production/default change.  The separate historical harmful-root
regression could not be run because its exact frozen root snapshots were not
available locally or on the designated GCP worker.  No substitute roots were
recollected.

## Frozen result

- Mean source-seed-clustered J-regret delta, L minus A: `-0.3284866992`;
  bootstrap 95% CI `[-0.7272965479, -0.0381220176]`.
- Mean pairwise-concordance delta: `+0.1208863185`; clustered 95% CI
  `[+0.0637300460, +0.1960730632]`.
- Maximum J-regret: L `1.0854700000`, A `5.5437900000`.
- Upper-decile J-regret: L `0.0`, A `0.4388132500`.
- New harmful roots at regret `>=3.0`: none.  One root was materially worse for
  L: `12006012/1/11/13/5`.
- All 32 roots contained a stochastic action.  Stochastic-involving pairwise
  delta was `+0.1321541695` over 32 root comparisons; deterministic-only delta
  was `+0.0780877242` over 26 comparisons.
- All seven preregistered gates passed.

## Provenance

- Gameplay source seeds: `12006000..12006015`; Ironclad A0, project-fair RNG,
  native OOC, exact 10k Silver, adaptive search disabled, Act-1 stop.
- Snapshot producer Git SHA: `8de023e3be82d2ac06a970d56f2f8988638babf9`.
- Evaluator Git SHA: `cd24d9fbaff162bee0892fe2f5b06528a17d9260`.
- Silver submodule SHA: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.
- Capture SHA256: `2aad98625221dca6b22ef0fe58ac5e095b6a65588fba876bf52b2d6f3e3b6a5c`.
- Selected roots SHA256: `fb92b1d1870d8aeda07fe10204523f42ac2e43b17ccb510d24c549865384aab0`.
- Selection manifest SHA256: `d1708cbdca311fc1f9111e6e4911b4606e89f34b51862dc05a5fc1f503340068`.
- Audit JSONL SHA256: `5c7d04adf100cf564731b1f426b525771ed60eb3bd5e0bb692d5a47943797e54`.
- Audit executable SHA256: `93f5cff0fe6867789bce471909c242ec04bd4c5067b1aa38ac3c51b8db2d7a52`.
- Analysis SHA256: `eee5ce07108712096be9b0dd4fc9c19993118b9853442426b10c4ed2d72cc0f2`.

The tracked [`analysis.json`](analysis.json) contains the complete aggregate
and per-root result, and [`roots.jsonl`](roots.jsonl) freezes the selected
snapshots.  The larger raw capture and audit streams remain in the local build
evidence directory under the hashes above.  A pre-fix partial run and an
immediately stopped run with an incorrect evaluator-SHA argument were
quarantined and excluded from every result.

The first generated metadata used the non-object string
`8de023e3aeecf6fd5c2fc111dc1a15cd53f7a159` for the producer.  Branch history
and the evaluator's parent identify the actual producer commit as
`8de023e3be82d2ac06a970d56f2f8988638babf9`.  The retained capture, selected
roots, manifest, and audit stream were reissued with only that metadata field
corrected; the analysis reproduced byte-for-byte, retaining SHA256
`eee5ce07108712096be9b0dd4fc9c19993118b9853442426b10c4ed2d72cc0f2`.

## Verification boundary

Immediate-terminal forced actions exposed that they consume zero continuation
simulations.  The evaluator was repaired to record exact terminal utility and
`terminalAfterAction=true`, while every nonterminal replicate must consume its
full continuation budget.  The completed audit contains 2,768 rows, 173
root-action pairs, 48 terminal rows, and 864 stochastic rows.

**Knowledge impact:** this replaces the failed learned-teacher target premise
with a qualified independent forced-action target for a later model experiment.
It does not reopen learned root guidance beyond that next bounded step.
