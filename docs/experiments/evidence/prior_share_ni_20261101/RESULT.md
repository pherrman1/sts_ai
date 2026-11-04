# Prior-share stop at A20 map roots vs the 1,024 default: result, 2026-11-03

Pre-registration: [README.md](README.md) (review J PASS after deltas; RUN_COMMIT aefeffc7). Analysis: `analyze.py` as
frozen, `result.json`.

**Verdict: NOT_WORSE.** With `STS_OOC_MCTS_PRIOR_SHARE_STOP=0.9`, A20 map-root search uses 0.38x the simulations of
the 1,024 default, and Heart kills over the 1,536 paired seeds are 25.65% vs 25.72% (d = C − R −0.07 pp, 95% CI
[−0.59, +0.46]). The SPRT (nonregression, d0 = −1.5 pp, d1 = 0) accepted H1 at the second look (128 pairs,
LLR 3.76). As the pre-registration's power note says, this gate passes almost by construction (only 49 of 1,536
games diverge). The informative number is the kill count on the 49 diverging seeds: 19 with the stop vs 20 without
(−2.0 pp, CI [−18.4, +12.2]), i.e. no visible loss, but a small sample.

## Data
- 81 units (49 diverging seeds, 32 sentinels) on 4 cloud workers, finished 23:18 CET. `verify_campaign.py`: 81 OK,
  0 missing, 0 bad, 0 duplicates, one run commit (aefeffc7). Per worker 26/23/17/15. No failed units (every claim
  a1, no `failed` marker), so the failed-as-loss rule did not apply.
- Binary d3289b52 (v3, code 85bf1ba0 = 53d591b + #942), H = 0.9, everything else §741 arm B's environment.
- Control reuse (ADR-0064): 32/32 sentinels reproduce their control record exactly; 49/49 diverging units match the
  control before the predicted root and pick the predicted key there (`divergence_ps90.json`). Reuse valid.

## Primary
| | R (1,024 default) | C (prior-share 0.9) | d = C − R | 95% CI |
|---|---|---|---|---|
| Heart kill (1,536 seeds) | 25.72% | 25.65% | −0.07 pp | [−0.59, +0.46] |
| Heart kill (49 diverging seeds) | 20 | 19 | −2.0 pp | [−18.4, +12.2] |

SPRT looks: 64 pairs LLR 1.42, 128 pairs LLR 3.76 → NOT_WORSE.

## Secondary (paired, 95% seed bootstrap, d = C − R)
- Act 4 reached 40.43% vs 40.17%, −0.26 pp [−0.85, +0.33]; Heart reached 38.54% vs 38.35%, −0.20 pp [−0.78, +0.39].
- Mean final floor −0.08 [−0.21, +0.04].
- Deaths by act: Act 1 +0.07 pp, Act 2 +0.13 pp, Act 3 +0.07 pp, Act 4 −0.20 pp; every CI includes 0.

## Cost
- Map-root simulations: 0.38x of the 1,024 default over all 1,536 control games (offline from the control records,
  `divlist.py`; non-diverging games play identically, so this is the arm's real count). On the 49 diverging games
  6,512 vs 18,662 map sims per game (0.35x).
- Wall time per diverging game 448 s vs 770 s; the control ran on other machines at another time, so this ratio is
  indicative only.
- ≈ 81 games ≈ 14 core-h. Seeds: none new (§741/§727 seeds 111312000-111313535 replayed).

## Interpretation (Inference)
The stop at H = 0.9 fires mostly at 128 sims and almost never changes the move: 49 of 1,536 games ever see a
different map pick, and on those the kill count is level. Within the gate's 1.5 pp margin it is not worse, at ~0.38x
the map-search work. Map search is only part of a game's CPU (combat dominates), so the end-to-end speedup is
smaller than 2.6x; the diverging-game wall times suggest roughly 0.6x per game, to be measured on one machine before
quoting it.

The run used 85bf1ba0, before the default-on fidelity fixes #957/#970/#976. The stop rule does not depend on them,
but a default change would land on current main with its own smoke there.

**Decision:** no default change in this PR. Making H = 0.9 the A20 default is Philipp's decision (own PR + ADR on
current main).
