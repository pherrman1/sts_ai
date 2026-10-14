# §443 Stage 4 re-gate tools (Stage 3a gate, frozen)

Copied unchanged on 2026-10-14 from the local machine that ran the §443 Stage 3a gate on 2026-10-13.
Nothing was re-run when making this folder. Source directory for every file:
`/home/philippherrmann/Documents/sts/wt-ctm-a20/build/ctm-a20/gate3a/` (same contents as the
`gate3a-20261013.tgz` evidence bundle next to it, sha256 db1de2a0cb18e1da95b1d36ac1e1d5f1f601f83ca9a36a34a43589b96fcb5667).

| File | What it is |
|---|---|
| `gate3a.py` | Frozen Stage 3a gate script (`clamp` and `compare`), sha256 25f7dc00…838bd7. stdlib + numpy. |
| `offline_ab_compare_418.py` | Row extractor used by the gate (`extract` subcommand: hash-split TEST rows per scope). Byte-identical to `docs/experiments/evidence/ctm_offline_ab_418_20261009/offline_ab_compare.py` on origin/main (sha256 ff71cf53…). gate3a.py does not import it; run_gate3a.sh calls it. |
| `run_gate3a.sh` | The exact Stage 3a command sequence (absolute local paths; checkout 40db7d62, script sha check). |
| `PREREG-FROZEN.txt` | Frozen-inputs receipt written before any scoring (checkout, data branch, model/manifest/binary sha256s). |
| `PREREG-GATES.md`, `GATE3A-NOTES.md` | Frozen pre-registration and run notes. |
| `extract.json` | Receipt of the extract step (per-scope TEST row counts, corpus sha256s). |
| `results/*.json` | Stage 3a compare outputs; `main_test.json` is the gate (verdict NOT_QUALIFIED: criteria 2 and 5 failed). |
| `logs/` | All Stage 3a logs, incl. `main_test.summary.json`. |

Not included (large, local only): `rows/`, `rows-clamped/`, `scores/`, `tags/`.

Where TEST-only filtering happens: `gate3a.py` itself does not filter by split; it compares whatever rows
are in the two ctmscorerows CSVs. The TEST restriction (source-seed hash bucket >= 90) is done upstream by
`offline_ab_compare_418.py extract` (`split_for_seed`, `cmd_extract`).
