# AZ gen-2 A/B result: NOT_SHOWN (2026-10-22)

1,024 paired A20 seeds (111142888–111143911), RUN_COMMIT `712d4def` (main `844bd923` + campaign dir), v3 binary
`23a09099…`, 32 workers × 4 lanes, `schedule queue`. `verify_campaign.py` (`verify.txt`): 1,024 of 1,024 units OK,
0 duplicates, one run commit. Unit tar hashes: `tars.sha256`. Analysis: `analyze.py` on the `--extract` dir → `result.json`.

| arm | Heart kills | reached Act 4 | mean floor | wall s/run (mean, max) |
|---|---|---|---|---|
| A student_sel | 214 (20.9%) | 399 (39.0%) | 43.15 | 773, 2,554 |
| B gen 2 (fc32d8f4) | 220 (21.5%) | 408 (39.8%) | 43.08 | 777, 2,739 |

- Heart kills B − A **+0.6 pp [−2.2, +3.3]**, discordant 107 B-only / 101 A-only, exact McNemar p 0.73.
- Act 4 +0.9 pp [−2.1, +3.9], p 0.61. Wall B/A 1.006 (≤ 1.10).
- **Verdict: NOT_SHOWN** (pre-registered rule). The difference is below the +1.0 pp extension trigger, so the
  pre-registered extension (111152128–111153151) does not run. student_sel stays the OOC prior.
- Search effort: 66,498 / 66,275 searched roots, 16,723 / 16,740 full-budget (policy targets). The search's pick differed
  from the prior's argmax at 6.6% (A) vs 7.9% (B) of searched roots.
- Speed: mean wall per run 773-777 s vs ~1,480 s in gen 1b's A/B (flat 10k), from the learned Silver stop in real
  combats, the 1024 fast-root cap, boss-only prior playouts and the v3 build.
- Data: both arms' policy rows (≈16.7k full-budget roots each) and value rows join the gen-3 training window.
- Run notes: repeated container restarts; unit 111143798 needed 3 claim attempts (attempt 1's worker died, attempt 2's
  claimers were lost) and finished on w07; no unit ran twice.

Inference: offline the gen-2 prior matched the search's improved policy much better than student_sel (selection KL 0.055
vs 0.103), but that did not show up as Heart kills at this resolution (±2.8 pp). With most searched roots following the
prior anyway (92-93%), a sharper prior moves few decisions.
