# Act-4 CTM survival model A/B in the A20 stack (2026-10-18): NOT_SHOWN

Ledger §534. [PREREG.md](PREREG.md) was frozen before launch. The run started at RUN_COMMIT `ef809026` (code main
`95c1ef1f`, binary `2b2817bc…`). The first freeze, `c6916b99`, had a malformed `binary_sha256` manifest line, and every
worker refused at setup, so no unit ran at it.

- Workers: 8 × 128 units, seeds 111140200–111140711 × arms A/B, A20 full runs. `verify.txt` shows all eight tars OK
  (`tools/cloud/verify_campaign.py`). Tar hashes are in `tars.sha256`; the raw tars are on the share at
  `/mnt/project-files/ctm-act4-ab/`.
- Analysis: `python3 tools/analyze_act4_ctm_ab.py analyze <extracted tars>`. Output is `result.json`, with the
  per-arm decision-source counts dropped.
- Smoke: seeds 111194390–111194392 at `c6916b99`. Its code and binary are identical to the run's; only the manifest
  line differs.

## Result

| | A (control) | B (+ Act-4 model) |
|---|---|---|
| Heart kills / 512 | **82** | **75** |
| Reached Act 4 (act-3 clears) | 178 | 173 |
| Act-4 conversion | 0.461 | 0.434 |
| Deaths in act 1 / 2 / 3 / 4 | 78 / 158 / 98 / 96 | 78 / 158 / 103 / 98 |
| Seconds per run | 299.3 | 300.2 |
| MCTS CPU seconds per OOC decision | 2.715 | 2.752 |
| Runs that logged `[ctm-act4-survival]` | 0 | 229 |

Primary: Δ Heart kills −0.0137 [−0.0273, 0.0000] (seed bootstrap). Discordant pairs: 3 favour B, 10 favour A.
McNemar p = 0.092. Label: **NOT_SHOWN**.

Descriptive:
- No seed was excluded and no unit had a nonzero rc.
- 451 of 512 seeds had identical outcomes. Through Act 2 the arms played identically, as expected: B changes only how
  Act-4 fights are priced, which matters once the search horizon reaches Act 4.
- Every seed on which B reached Act 4 also reached Act 4 in A. On those 173 seeds, A killed the Heart 82 times and
  B 75 times.
- Mean floor difference (B − A): −0.057.
