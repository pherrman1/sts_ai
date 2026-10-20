# A20 winrate check (2026-10-18/19)

Descriptive whole-run A20 measurement of the stack in [PLAN.md](PLAN.md); ledger entry "A20 winrate check of the best
stack" in `docs/experiments/ledger-06.md`.

- Result: 90/512 Heart kills = 17.6% [14.5, 21.1]; reached Act 4 184/512 = 35.9%; all 512 units rc=0.
- `campaign.manifest`, `units.txt`, `run_unit.sh`: frozen campaign (RUN_COMMIT `9db53ea3`, binary `9daffbd4…`).
- `verify.txt`: `tools/cloud/verify_campaign.py` output, 32/32 OK. `tars.sha256`: worker tar hashes.
- `report.json`: `python3 analyze.py /mnt/project-files/a20-winrate-check/w*.tar > report.json`.
- Raw tars: `/mnt/project-files/a20-winrate-check/w01..w32.tar` (project share).
