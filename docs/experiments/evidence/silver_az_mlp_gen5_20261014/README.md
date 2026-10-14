# Silver AZ MLP prior, generation 5 (20k teacher; self-play data and offline training)

Ledger §477. Generation 5 with a 20k teacher and the same 128/64 net (Philipp, 2026-10-14
07:40Z), with offline gating instead of an online milestone per generation. Full numbers:
`RESULT.md` (copied from the share).

- Frozen: `FROZEN.md`, `BRIEF-worker.md` (sha d42b67ec), `worker.sh` (per-unit timeout 9000 s),
  `env.sh`; main `f73e6ad7`, binary `b4586cfc…`, prior gen 4 (`3ebeab9d…`).
- Seeds: natural 94000000-94000511, perturbed 94001000-94001511, 8 workers (Philipp's choice).
  256/256 units rc 0.
- Training (`PLAN-train.md`): arms A/B/C, warm start from gen 4; C (dropout 0.15) selected.
  Packed with the lower-memory packer that became #535 (identical output).
- Parity: `g5parity_*.json` (pass). Model hashes: `MODEL_SHA256SUMS`; files in
  `/mnt/project-files/silver-az-mlp/gen5/model/`.
