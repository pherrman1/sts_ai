# OOC MCTS prior guidance: diagnostic and Act-1 A20 screen (2026-10-18)

Pre-registration: [PREREG.md](PREREG.md). Ledger: the §532 entry titled "OOC MCTS prior guidance".

- Diagnostic: `python3 diagnostic_rootstats.py DIR` over the extracted decision logs of the A20 winrate check
  (`/mnt/project-files/a20-winrate-check/w*.tar`, 14 tars uploaded at 12:4xZ, 224 seeds).
- Screen: 16 workers, run commit 3d0d5120, code 658d43ee, binary sha256 3315a7c1…; `verify_campaign.py`: OK 1-16,
  MISSING -, BAD -. Raw tars: `/mnt/project-files/ooc-prior-guidance/w01..w16.tar` (hashes in SHA256SUMS).
- Analysis: `python3 analyze.py DIR` (DIR holds the extracted tars) -> [result.txt](result.txt).
