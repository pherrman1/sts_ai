# Silver forced-action target audit (2026-09-19)

## Decision

The preregistered primary audit is
**`FORCED_ACTION_TARGET_PASS`**.  On 32 roots selected as two deterministic
hash-ranked roots from each of 16 fresh gameplay source seeds, the independent
forced-action label ensemble L (8 replicates at 5,000 continuation simulations)
improves on the frozen same-root Teacher-A label under a disjoint judge J
(8 replicates at 10,000 simulations).

This confirms a fresh-population target signal, but model training remains
blocked.  The separate historical harmful-root regression could not be run
because its exact frozen root snapshots were not available locally or on the
designated GCP worker.  No substitute roots were recollected.  The result does
not qualify a learned model, replay integration, gameplay, or a
production/default change.

## Frozen result

- Mean source-seed-clustered J-regret delta, L minus A: `-0.3284866992`;
  bootstrap 95% CI `[-0.7272965479, -0.0381220176]`.
- Mean pairwise-concordance delta: `+0.1193982233`; clustered 95% CI
  `[+0.0622749256, +0.1949791723]`.
- Maximum J-regret: L `1.0854700000`, A `5.5437900000`.
- Upper-decile J-regret: L `0.0`, A `0.4388132500`.
- New harmful roots at regret `>=3.0`: none.  One root was materially worse for
  L: `12006012/1/11/13/5`.
- All 32 roots contained a stochastic action.  Stochastic-involving pairwise
  delta was `+0.1293132604` over 32 root comparisons; deterministic-only delta
  was `+0.0780877242` over 26 comparisons.
- All seven preregistered gates passed.

## Provenance

- Gameplay source seeds: `12006000..12006015`; Ironclad A0, project-fair RNG,
  native OOC, exact 10k Silver, adaptive search disabled, Act-1 stop.
- Snapshot producer Git SHA: `8de023e3be82d2ac06a970d56f2f8988638babf9`.
- Corrected evaluator Git SHA: `1e1033d4da68aeaa2ceb8b30a6c58ca7b5bff407`.
- Silver submodule SHA: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.
- Capture SHA256: `2aad98625221dca6b22ef0fe58ac5e095b6a65588fba876bf52b2d6f3e3b6a5c`.
- Selected roots SHA256: `fb92b1d1870d8aeda07fe10204523f42ac2e43b17ccb510d24c549865384aab0`.
- Selection manifest SHA256: `d1708cbdca311fc1f9111e6e4911b4606e89f34b51862dc05a5fc1f503340068`.
- Audit JSONL SHA256: `028e9cdada11225e9311e89ddc63b97a2431a8d26c206277bf38647fddcb962c`.
- Compressed tracked audit SHA256: `1763a30a74af53404b1ca74b46c0f4cdcb17e974e55f531160882ec6aea8220d`.
- Audit executable SHA256: `afbd3cafb1e586b237f155cde8471ec1a2ba1ab09283d3744d85fdfcb883405d`.
- Analysis SHA256: `17cd23a1faf80c2212a35f1fe950e3ae8fb584fe28ded7f326c99b7c72116091`.
- Immediate-correction probe SHA256: `4547a301028ad5a2a087d209c65ab6114bf2269af547ac750dbfc1120932e9c9`.

The tracked [`analysis.json`](analysis.json) contains the complete aggregate
and per-root result, [`roots.jsonl`](roots.jsonl) freezes the selected
snapshots, [`audit.jsonl.gz`](audit.jsonl.gz) retains all 2,768 raw rows, and
[`baseline-corrections.jsonl`](baseline-corrections.jsonl) retains the cheap
173-action immediate-correction scan.  The larger raw capture remains in the
local build evidence directory under the hash above.  A pre-fix partial run and an
immediately stopped run with an incorrect evaluator-SHA argument were
quarantined and excluded from every result.

The first generated metadata used the non-object string
`8de023e3aeecf6fd5c2fc111dc1a15cd53f7a159` for the producer.  Branch history
and the evaluator's parent identify the actual producer commit as
`8de023e3be82d2ac06a970d56f2f8988638babf9`.  The retained capture, selected
roots, manifest, and audit stream were reissued with only that metadata field
corrected; that earlier analysis reproduced byte-for-byte.

## Verification boundary

Immediate-terminal forced actions exposed that they consume zero continuation
simulations.  The evaluator was repaired to record exact terminal utility and
`terminalAfterAction=true`, while every nonterminal replicate must consume its
full continuation budget.  Review then found that a fresh post-action search
root absorbed immediate effective-gold/max-HP changes.  Evaluator v2 now applies
the established victory-only original-root baseline correction, retaining the
leaf-root value, victory count, full correction and applied correction in every
row.  The frozen scan found one nonzero action (`-3.75`, end turn on
`12006015/1/13/7/3`), so L/J were rerun on the same roots.  Regret, selections,
tails and all gates were unchanged; only pairwise margins moved slightly.  The
completed corrected audit contains 2,768 rows, 173 root-action pairs, 48
terminal rows, and 864 stochastic rows.

**Knowledge impact:** this confirms an independent fresh-population target
signal, but does not reopen model training while the exact known-harmful-root
regression remains unavailable.
