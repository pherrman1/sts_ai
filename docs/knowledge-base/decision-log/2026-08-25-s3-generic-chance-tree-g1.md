# Searcher3 generic chance-tree G1 evidence closure

Date: 2026-08-25

## Decision

Record the completed G1 generic action-observation-tree smokes and close the
experimental branch/PR without merging it into `main`. The implementation at
`d3e250d84672e264b8515f02b1b6bbbc40c4dc66` passed the hard topology and semantic
routing checks. The fresh-tree 16-seed smoke and the generic reuse comparison
are evidence, not gameplay promotion gates.

## Evidence

- Chronological ledger entry: `docs/experiments/ledger-06.md` (G1 section).
- Machine-readable provenance: `docs/experiments/evidence/s3_generic_chance_tree_g1_2026-08-25.json`.
- Raw ignored CSV/log artifacts: `build/g1_fresh_*`, `build/g1_reuse*`, and
  `build/g1_particle_audit*` in the experiment worktree.
- Frozen executable and model hashes are recorded in the evidence manifest.

## Findings

- Fresh generic tree: 16 paired seeds, hard counters all zero; 4/16 treatment
  wins versus 7/16 legacy control, with approximately +35.8% runtime.
- Generic reuse isolation: reuse 1 won 5/16 versus 4/16 for reuse 0, but cost
  approximately +9.0% runtime; this is mixed, underpowered evidence.
- Boundary particle audit: carried fallback was 8.33% for reuse 0 and 12.36%
  for reuse 1, while fresh-boundary fallback was approximately 95% in both
  arms. The audit does not count every internal particle install and does not
  explain the largest outcome tables by itself.

## Status and follow-up

No deterministic fast path, local chance resampling, progressive widening,
transposition, CRN gameplay, or other G2+ feature is authorized by these
smokes. If the line is resumed, first isolate `reuse=1` with a fresh 64-particle
belief rebuilt at the real decision boundary. The PR may be closed without
merge; the evidence manifest prevents the ignored raw-run mistake from losing
the provenance again.
