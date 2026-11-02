# Map-simulations SPRT, 1,024 vs 4,096: result (stage 1)

Pre-registration: [README.md](README.md) (frozen in `c78b0f4c` before any campaign tar was read; RUN_COMMIT
`b01a0e81`, code `1cd21a15`, binary `b8f0628b…`, 24 cloud workers, 716 units). Raw: `result.json` (written by
`analyze.py /mnt/project-files/map-sims-sprt /mnt/project-files/value-chooser-ab/units result.json`). Tars:
`/mnt/project-files/map-sims-sprt/units/*.tar` (716; sha256 of the sorted per-tar sha256 list `ec49a4626fe91a53`).

## Verdict: NOT_WORSE (SPRT H1 crossing at n = 1,024 pairs, LLR 3.36 > ln 19 = 2.94)

| | A (4,096 map sims, §727 arm A) | B (`STS_OOC_MCTS_FULL_ROOT_SIMS=1024`) | B − A, 95% seed bootstrap |
|---|---|---|---|
| **Heart kill (primary)**, 1,536 seeds | 25.07% | 25.72% | **+0.65 pp [−0.98, +2.34]** |
| Act 4 reached | 41.15% | 40.43% | −0.72 pp [−2.54, +1.11] |
| Heart reached (floor ≥ 56) | 39.52% | 38.54% | −0.98 pp [−2.73, +0.78] |
| final floor | 42.08 | 41.44 | −0.64 [−1.10, −0.17] |
| death in act 1 / 2 / 3 / 4 | | | +1.17 [+0.20, +2.15] / +0.46 [−0.98, +1.95] / −0.91 [−2.67, +0.78] / −1.37 [−3.06, +0.33] pp |

- **Reuse validity: VALID.** 64/64 sentinels reproduce A record for record, 652/652 diverging units match A row for
  row before the predicted root and pick the predicted key there, no missing unit, no duplicate (verify_campaign.py:
  716 OK, 0 missing, 0 bad, 0 duplicates, one run `b01a0e81`).
- **SPRT path** (look, LLR, running mean d): 64 +0.24 +3.1 pp; 320 −0.82 −2.8 pp (lowest); 576 +0.56 0.0; 768 +1.28
  +0.5 pp; 1,024 **+3.36** +1.66 pp. The stopping-time mean (+1.66 pp) is biased upward by optional stopping; the
  full 1,536-pair mean (+0.65 pp) is the descriptive estimate (all pairs were played anyway).
- On the 652 diverging seeds alone the kill difference is +1.53 pp (= +0.65 × 1,536 / 652, Inference).
- **Cost:** map simulations per diverging game 69,959 (A) vs 17,125 (B), −75.5%; wall per diverging game 956 s vs
  558 s, −42% (different containers, indicative only, as pre-registered).

## Reading

- The primary passes the pre-registered non-inferiority gate: 1,024 map simulations are not worse than 4,096 by
  1.5 pp in Heart kills; the point estimate favours 1,024.
- The secondaries (descriptive, not multiplicity-corrected) lean the other way: B dies slightly earlier
  (final floor −0.64, act-1 deaths +1.2 pp, both CIs excluding 0), and reaches Act 4 / the Heart ≈ 1 pp less often
  (n.s.), while killing the Heart as often or more. Inference: fewer simulations make some early map choices worse
  but the runs that survive are not weaker; the act-1 effect is the one to watch if a default PR follows.
- Stage 2 (§683 MAP replay) is not run: it was pre-registered only for a CAP.

## Decision (pre-registered)

`STS_OOC_MCTS_FULL_ROOT_SIMS=1024` (or an A20 default of 1,024 map simulations) is now a **default candidate**.
Philipp decides, in its own PR and ADR. Note for that PR: the learned OOC stop (`ooc_learned_stop_trees`, needs
> 2,048 simulations) and the gap stop were trained/tuned at the 4,096 scale; under a 1,024 cap the learned stop
cannot fire, so the cap replaces it rather than combining with it.

## Disclosed deviation

`analyze.py` (pre-registered version) read only `SHARE/wNN.tar` (static-schedule worker tars); the campaign ran with
`schedule queue`, which uploads one tar per unit to `SHARE/units/<id>.wNN.tar`. The first run therefore saw no B unit
and returned INVALID (716 missing). The loader now also reads `SHARE/units/*.tar`; no other line changed (diff in
the PR). Verdict logic, checks and thresholds are untouched.

Seeds: none new (replays of the USED §727 block 111312000-111313535).
