# Act-by-act clean value labels: stages 0-2 (offline + capture option, 2026-10-29)

Plan (Philipp's ask 2026-10-29, thread "Build clean value labels act by act"): learn V_k(s) = P(Heart kill | public
state in act k, student_sel + CTM rollouts) backwards, act by act, without X2-B or MCTS in the target. V_A4 at the
Act-4 entry anchors it; act-k labels are rollouts to the end of act k, scored by V_{k+1} at the next act's first map
state; one capture stores those act-end records so every backward refit is offline. Philipp chose this over an M0
refit (09:44Z) and said go for stages 1-2 with the CTM "only as a comparison" (12:50Z).

## Stage 0: label variance (offline, no seeds)
[`tools/stage0_variance.py`](tools/stage0_variance.py) on §707's roots (data branch `claude/sibling-noise-881-data`,
`sibling-noise-881/roots.jsonl.gz`: 1,872 roots, top-3 actions, 32 act-end rollouts each, CTM combats, deaths 0,
survivors M0-calibrated X2-B). Output [`results/stage0_variance.txt`](results/stage0_variance.txt).
- Per-state variance of the act-end label / Bernoulli variance p(1 − p) of a full-game outcome at the same mean:
  all 0.141, act 1 0.067, act 2 0.122, act 3 0.257 (map 0.160, card rewards 0.133).
- Sibling differences on shared streams / independent Bernoulli: all 0.058, act 1 0.026, act 3 0.100, map 0.140.
- Caveat: M0 stands in for V_{k+1}; a more informative V spreads more at act ends, so the true ratio is higher (≤ 1)
  and the ≈ 7× saving is an upper bound.

## Stage 2: V_A4 from real Act-4 outcomes (offline, no seeds)
Plan frozen before TEST was read: [STAGE2-PLAN.md](STAGE2-PLAN.md). Data: [`tools/extract_a4.py`](tools/extract_a4.py)
over the share unit tars of key-rules-ab, gumbel-qcap-ab, expert-anchored-ab and card-rule-ab, games whose log says
"Act 4 strong": 2,337 Act-4 entries, 62.2% Heart kills (extract sha256 `253e3178…`, share
`value-clean-labels/stage2/a4.pkl`). Fit and gate: [`tools/fit_a4.py`](tools/fit_a4.py) (Python 3.13.17, numpy 2.5.3,
xgboost 3.0.5, scikit-learn 1.9.1, scipy 1.18.1; a rerun with these versions equals
[`results/stage2_result.json`](results/stage2_result.json); with xgboost 3.4.1 the reviewer's two reruns gave GC − CTM
−0.007 and −0.010, CIs including 0, and failed the decile check, so the decile calibration is fragile and the FAIL holds). The CTM parser matches the CTest parity fixture to 2.7e-7.

| TEST (569 entries) | BCE | AUC |
|---|---|---|
| constant | 0.674 | — |
| HP logistic | 0.633 | 0.667 |
| G (GBM, public record) | 0.545 | 0.779 |
| Act-4 CTM, raw | 0.540 | 0.794 |
| Act-4 CTM, recalibrated on TRAIN | 0.533 | 0.794 |
| GC (G + logit CTM; picked on VALIDATION) | 0.529 | 0.798 |

Gate: GC − CTM_recal BCE −0.004 [−0.028, +0.018] → **FAIL** (calibration by decile passes here, fragile across
library versions, see above). The CTM sees the state
after the Act-4 campfire (its S&S input), the heads the Act-4 entry, so the comparison favours the CTM.
Caveat for later stages: s0's features include the screen one-hot; capture end records are map screens.

## Stage 1: capture option (code, default off)
`STS_OOC_CAMPFIRE_PRICE_RECORDS=1` adds to every `actEnd` entry of `STS_OOC_CAMPFIRE_PRICE` the start state
(`start`, index into the action's `starts`) and the public record at the act end (`endRecord`; none after a death);
`STS_OOC_CAMPFIRE_PRICE_ACT_END_ONLY=1` skips the leaf rollouts. Values and streams unchanged.
- Selftest (`ctest -R '^ooc_mcts_adapter$'`): PASS, with new checks (same act-end values as without records, start and
  end records, no record after a death, act-end-only rows).
- Smoke ([`tools/smoke_unit.sh`](tools/smoke_unit.sh) = §707's replay env, N = 4, killed at the first act-2 state;
  [`tools/smoke_check.py`](tools/smoke_check.py)): used seed 111374100 with and without records, game trace
  byte-identical, 59 rows, 588 act-end entries equal, 581 end records (all one act later), 7 deaths. 12 ms CPU per
  act-1 rollout; 1.7 MB raw / 99 kB gzip per 58 roots at N = 4 (≈ 25 kB gzip per root at N = 64, top 3).
