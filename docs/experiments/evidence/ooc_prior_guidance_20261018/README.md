# OOC MCTS prior guidance: diagnostic and Act-1 A20 screen (2026-10-18)

Pre-registration: [PREREG.md](PREREG.md). Ledger: the §532 entry titled "OOC MCTS prior guidance".

- Diagnostic: `python3 diagnostic_rootstats.py DIR` over the extracted decision logs of the A20 winrate check
  (`/mnt/project-files/a20-winrate-check/w*.tar`, the 14 tars w03, w05, w06, w12, w13, w15, w19, w21, w22, w24, w27, w29, w30, w32,
  224 seeds; later uploads were not included).
- Screen: 16 workers, run commit 3d0d5120, code 658d43ee, binary sha256 3315a7c1…; `verify_campaign.py`: OK 1-16,
  MISSING -, BAD -. Raw tars: `/mnt/project-files/ooc-prior-guidance/w01..w16.tar` (hashes in SHA256SUMS).
- Analysis: `python3 analyze.py DIR` (DIR holds the extracted tars) -> [result.txt](result.txt).
