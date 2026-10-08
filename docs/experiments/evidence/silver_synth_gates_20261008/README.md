# Synthetic Silver prior pilot: Gate A / Gate B evidence (ledger §397)

- Corpus: `silversynthgen` at 450376c8 (one_combat sha256 8906180f…), seeds
  56000000-56000215 natural and 56002000-56002215 perturbed, flat exact-10k
  native Silver, A0, project-fair. 432 runs, 9,305 fights, 174,746 roots,
  554,337 leaves, 20,384 continuation roots; 0 errors.
- Rules: [PREREG.md](PREREG.md), copied verbatim from
  `/mnt/project-files/silver-synthetic-prior/GATES-PREREG.md`, which was written
  before any model was trained.
- Pipeline: `one_combat silversynthfeatures` and `silversynthreplay` (this PR),
  `tools/silver_synth_gates.py train|gatea|tasks|gateb`.
- Files: `train.json` (row counts, early-stopping iterations), `gateA.json`,
  `weight-*.json` (validation weight grid), `gateB.json`. Models, replay
  tasks and replay outputs are in
  `/mnt/project-files/silver-synthetic-prior/gates-20261008/` (not archived in
  the repository).
- CIs are 95% seed-clustered percentile bootstraps (2,000 resamples, 43 test
  seeds). Gate B means are over 8,188 root-seed runs (4,094 test roots x 2
  replay seeds); no root was dropped for an action mismatch.
