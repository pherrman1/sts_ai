# AZ gen-3 exploration block: result (2026-10-22, descriptive)

1,024 seeds (111300000–111301023), RUN_COMMIT `0a56caae` (main `165b5060` + campaign dir), v3 binary `eb314334…`,
32 workers × 4 lanes, `schedule queue`. `verify_campaign.py` (`verify.txt`): 1,024 of 1,024 units OK, 0 duplicates,
one run commit. Unit tar hashes: `tars.sha256`. `analyze.py` on the `--extract` dir → `result.json`. All 1,024 runs valid.

| | exploration (E) | gen-2 A/B arm A (same net, greedy; other seeds) |
|---|---|---|
| Heart kills | 161 (15.7%) | 214 (20.9%) |
| reached Act 4 | 324 (31.6%) | 399 (39.0%) |
| mean final floor | 41.4 | 43.2 |
| wall s/run (mean) | 778 | 773 |
| prior overrides (searched roots) | 13.0% | 6.6% |
| fast roots stopped below the 1024 cap | 99.89% | 99.90% |
| fast roots: mean completed sims (D's sample) | 534 | ~415 |

- Exploration costs strength: −5.2 pp Heart kills, −7.4 pp Act 4 (unpaired, different seeds; ±3.3 pp at 95%).
- Floors 0-6: 11,457 searched roots, all sample-eligible. The played action differed from the most-visited one at 2,601
  (22.7%); its root Q was higher at 1,011 and lower at 1,590 (mean ΔQ −0.017).
- Root noise acts on every searched root, not only floors 0-6: the search's pick differs from the prior's argmax twice as
  often as in the greedy arm (13.0% vs 6.6%). Recorded priors are clean, so π' targets use the clean prior.
- The learned OOC stop still fires before the 1024 cap (99.89% vs 99.90%), but later under noise: fast roots average
  534 vs ~415 completed sims, and 24% vs 42% stop at the first check (≤ 128); also 22% vs 40% on floors ≥ 7, where play
  is greedy, so it is the noise (reviewer D, 150-unit sample, 7.3k roots). Mean wall unchanged (778 vs 773 s).
- Rows: 63,472 searched roots, 16,087 full-budget (policy targets), 140,821 decisions.

Inference: the block gives the gen-3 window ≈16k policy targets from states the greedy runs do not reach, at the price of
weaker z labels (lower kill rate). For value training, the run outcome of an exploration run is a pessimistic label for its
early states; gen-3 training should keep these runs' policy rows and down-weight or drop their value rows.

Notes: the analyzer's fast-root metric was changed after the smoke from `savedSimulations` (true for every capped root) to
`completedSimulations < 1024` (review D). Brief nit for future campaigns: add `test "$(git rev-parse HEAD)" = $RUN_COMMIT`.
