# §474 evidence: end-of-run Silver leaf parts vs legacy leaf, paired whole runs (split of §468)

Ledger §474. Planned and run as "§471" (folder, analyzer, PREREG, brief and share path keep that number because the
workers' FROZEN provenance cites them); renumbered after main's §471 (Codex PR #529) landed first.

- Pre-registration: [PREREG.md](PREREG.md). Smoke: [SMOKE.md](SMOKE.md). Worker brief: [BRIEF-worker.md](BRIEF-worker.md)
  (sha256 `2cb82661…`, pre-launch review PASS).
- Code commit [CODE_COMMIT](CODE_COMMIT) `7a6c6bb9`; run commit `965000fa`; binary sha256 `6b2bca17…` on all 8 workers.
- Raw data: `/mnt/project-files/silver-leaf-471/w01..w08.tar` and `.DONE.txt` ([SHA256SUMS](SHA256SUMS)).
- Analysis: `python3 tools/analyze_silver_leaf_471.py report.json <8 extracted out dirs>` → [report.json](report.json).
- Validity: 2,000/2,000 units rc=0; no stalls, timeouts, restarts or `[bestbench-seed-failure]`; every `.env` holds its
  arm's options; 500/500 pairs per cohort.

Per-act deaths (descriptive, not pre-registered). Both arms play every seed identically until floor 50 (no paired
difference before the final bosses):

| | A0 base | A0 end | A20 base | A20 end |
|---|---|---|---|---|
| wins | 402 | 406 | 42 | 47 |
| died before floor 50 | 49 | 49 | 340 | 340 |
| died floor 50 (act-3 boss / A20 first boss) | 49 | 45 | 52 | 57 |
| died floor 51+ (A20 second boss) | – | – | 66 | 56 |
| seconds per run | 63.1 | 63.9 | 37.0 | 37.0 |
