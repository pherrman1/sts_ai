# OOC MCTS prior temperature 3: A20 full-run confirmation (2026-10-19)

Pre-registered in [PREREG.md](PREREG.md). The identity gate passed: [IDENTITY.md](IDENTITY.md).
Ledger: §TBD in `docs/experiments/ledger-06.md`.

- RUN_COMMIT `c84d65f4` (frozen `4f5a181d` plus the pre-data failed-unit rule), code `b5dd5557`, binary `01d0f59e…`.
- 256 units (`units.txt`), arm T3, 16 cloud workers, share `/mnt/project-files/ooc-prior-temp3`.
- Control: the A20 winrate-check units for the same seeds (reused, not rerun).
- All 16 worker tars were verified with `tools/cloud/verify_campaign.py` (OK 1–16, MISSING -, BAD -). Their hashes
  are in [worker_tars.sha256](worker_tars.sha256).
- Analysis command: `python3 analyze.py T3_DIR CONTROL_DIR`. Output: [result.txt](result.txt).

## Result

| | Control | T3 |
|---|---|---|
| Wins (Heart kills) | 42/256 | 37/256 |
| Act 4 reached | 86 | 81 |
| Mean floor | 40.98 | 41.64 |

- **T3 − control, wins:** −2.0 pp [−6.6, +2.7]. Discordant pairs 17 vs 22, McNemar exact p = 0.522.
  **Verdict: NOT_SHOWN.**
- **Floor:** +0.66. This is descriptive only.
- **Failed units:** none, so the failed-unit sensitivity rule is moot.
- **OOC CPU per run:** 4,137 s vs 5,362 s. The two arms ran different binaries and stacks, so this is not a
  speed comparison.
- **Search behaviour under T3 (descriptive):** on 15,365 multi-action roots, the executed move equals the prior
  argmax 84.3% of the time. The §532 diagnostic on the temperature-1 stack measured 90.5%.
