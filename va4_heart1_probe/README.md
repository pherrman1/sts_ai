# V_A4 heart1.pt probe inputs (data branch, never merged)
Philipp 2026-10-30 14:26Z: sanity-check the heart1.pt encoder at the Act-4 entry before using it for V_A4.
- `va4_entries.jsonl.gz` (sha256 1450bc41e81ad40f9407d0076267643f887153a3960146f862c3dcaf44b41fea): 7,353 Act-4 entry
  records (all sources of the V_A4 study, same row order as `core.build(2)` in
  `docs/experiments/evidence/value_a4_improve_20261030/tools`), incl. TEST seeds (needed for alignment; the probe uses
  seed % 4 != 3 only).
- `heart1_embed.py`: run on the PC with heart1.pt and the silverbot checkout; writes `heart1_embed.npz`
  (pooled encoder output + value-head output) -> commit it here.
No gameplay, no seeds run.
