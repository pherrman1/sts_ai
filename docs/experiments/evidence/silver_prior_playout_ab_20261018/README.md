# Prior-argmax playouts vs production greedy Silver: 8-worker A/B (2026-10-18)

Pre-registration: [PREREG.md](PREREG.md). Ledger: §TBD-b ("prior-argmax playouts vs production greedy Silver").

- 8 workers, run commit 7843e73c, code fecde345, binary sha256 cd50de5a…; launched 15:32Z after a pre-launch review
  PASS (`/mnt/project-files/reviews/pr666-prelaunch-review.md`). `verify_campaign.py`: OK 1-8, MISSING -, BAD -;
  64/64 units rc = 0. Raw tars: `/mnt/project-files/silver-prior-playout-ab/w01..w08.tar` (hashes in SHA256SUMS).
- Analysis: `python3 analyze.py result.json DIR...` (DIRs hold the extracted tars) -> [result.json](result.json).
- Canary: spare seed 111197784 in the lead's container (not part of the result).
