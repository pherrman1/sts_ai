# #418 offline CTM A/B: production vs pathb-r2 (2026-10-09)

Ledger: §412 in [ledger-06.md](../../ledger-06.md).

- Pre-registration: [RUNBOOK.md](RUNBOOK.md) and the frozen script [offline_ab_compare.py](offline_ab_compare.py)
  (sha256 `ff71cf53…`, committed at `72ebd7d1`).
- Freeze record: [PREREG-FROZEN.txt](PREREG-FROZEN.txt) (2026-10-09T14:05:18Z; checkout `7d62ba42`; `one_combat`
  `dddb09f0…`; candidate FASTF `90806c25…`, STD1E `b9188de0…`, manifest `d9d8377e…`).
- Deviation: [logs/DEVIATIONS.txt](logs/DEVIATIONS.txt) (`python3 -P -E` instead of `-I`; judged harmless by the
  review).
- Inputs: [extract.json](extract.json) (per-scope corpora, TEST row/seed counts, tag hashes).
- Results: [results/](results/) — `main_test.json` is the gate; `ritual_writhing_test`, `high_maxhp_test`,
  `lizard_fairy_test`, `lizard_brew_test` and `stage0_learned` are secondary/replication sets.
- [SHA256SUMS.txt](SHA256SUMS.txt) covers the files above; all are byte-exact copies of the hand-back in
  `/mnt/project-files/ctm-pathb/offline-ab-20261009/` (`sha256sum -c SHA256SUMS.txt` passes in this directory).
- Independent review: [REVIEW.md](REVIEW.md) (PASSED, 2026-10-09).

## Not committed

The score CSVs (`scores/*.cand.csv`, `scores/*.prod.csv`), the tag CSVs (`tags/`) and the run logs (`logs/`, with
the `ctmscorerows research candidate pathb-r2` lines and `rows=R scored=S` counts) exist only on Philipp's machine,
in `$R2/offline-ab-20261009.tgz` (`$R2` = `$WT/build/ctm-retrain-a69f8862`, RUNBOOK.md line 62; sha256 `fcffc769620ef4253d3ac5196b7173ba63231baa34af55cc87789e4414a912ed`). The
results JSONs record the sha256 of each score and tag CSV they read (`inputs.*Sha256`). They are not in the project
share or the repository.
