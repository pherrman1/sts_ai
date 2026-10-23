# CTM-calibration A/B at A20 (pre-registration)

**Status: proposed, not authorized.** Written 2026-10-23 before any game of this campaign ran, apart from the smoke
below. Philipp's card (17:50Z, "Check the CTM first") asked for an A/B proposal; the run needs his typed go and the
worker count. At the go the campaign is frozen as usual (`campaign.manifest`, brief, run commit), after review.

## Question
In today's A20 search stack, does calibrating the CTM to today's Silver (`STS_CTM_CALIBRATION`, table
`ctm_calibration_pathb_a20_v1.json`) kill the Heart more often?

## Background
[`README.md`](README.md): over the stage-3 A/B's 97,561 real fights, the A20 CTM predicts too many deaths at most
bosses (the Heart 0.486 against 0.370 observed, Act-1 bosses 0.093 against 0.050) and too much HP loss in Acts 2–4
(Act-3 bosses: mean HP after a won fight 19 HP too low). The per-fight calibration predicts held-out fights better
(log loss 0.0733 → 0.0698, won-fight HP error 8.2 → 7.6 on the 256 stage 1–2 games). The OOC search's rollouts play
up to three combats through the CTM before the M0 leaf, and every Act-4 rollout ends in a CTM death or Heart kill
(§663), so the CTM sets how much the search fears a fight.

## Arms ([`run_unit.sh`](run_unit.sh) is the source of truth)
- **A:** today's A20 stack: the stage-3 A/B's config (§661, `../value_level_ab_20261023/run_unit.sh`) with the M0
  leaf, which is now the default (ADR-0057; banner `leaf_calibration_min_ascension=20` checked). student_sel OOC prior
  and rollout net (`cf6bf7fb…`), OOC MCTS 4096 sims, rollout3 native leaf, learned OOC stop 0.99, 25% full-budget
  roots, fast roots capped at 1024, learned Silver stop with exact root budgets, g7f_E root table and prior, boss-only
  prior playouts, keys on, CTM rows on.
- **C:** A + `STS_CTM_CALIBRATION=models/candidates/ctm_calibration_pathb_a20_v1.json` (sha256 `359619f7…`; banner
  checked). Nothing else differs.
- One unit is one seed with both arms in sequence, order rotated by seed % 2, on one lane: wall times compare within a
  lane. 7 h timeout per arm.
- Real combats are the same Silver in both arms; only the OOC search's imagined fights change.

## Seeds
111392000–111394047 (2,048, assigned by the coordinator on 2026-10-23 at 18:30Z;
[`units.txt`](units.txt)). The smoke used 111394990–111394993. **Recommended: all 2,048.** The cheaper option is
the first 1,024 (111392000–111393023).

## Endpoints
- **Primary:** Heart kills, C − A per seed: mean and 95% seed-bootstrap CI (10,000 resamples, RNG seed 20261023).
  **IMPROVED** if the lower bound is above 0, **WORSE** if the upper bound is below 0, else **NOT_SHOWN**. The exact
  McNemar test on discordant seeds is reported alongside.
- **Guard:** mean wall C / A ≤ 1.10.
- **Secondary (descriptive):** reached Act 4; deaths by act; mean final floor; real elite fights per run by act (from
  the CTM rows); searched roots, picks off the prior's argmax, learned-stop and root-lock shares at fast roots.
- **Validity:** a seed counts when both arms end with rc 0 and a complete, integrity-passed footer. Other seeds are
  listed and left out.
- Analysis: [`analyze.py`](analyze.py) on the verified extraction (`tools/cloud/verify_campaign.py`).

## Power
Stage 3's M − A at 1,024 paired seeds had a 95% half-width of 2.6 pp. At 2,048 seeds it is about 1.8 pp (SE
0.93 pp): a true +2 pp gain is called IMPROVED with probability about 0.6, a +3 pp gain about 0.9. At 1,024 seeds
those are about 0.3 and 0.6.

## Prediction (frozen here)
- Direction of the primary: no confident call. M0, which cut the search's over-priced deaths, gained +2.15 pp
  (§661). The last CTM calibration A/B, the Act-4 survival model, was NOT_SHOWN at −1.4 pp (75 vs 82 Heart kills of
  512, §534). Point guess +1 pp.
- Play (descriptive): with fewer imagined deaths and less imagined HP loss in Acts 2–3, C should fight more elites in
  Acts 2–3 than A.

## Decision
- **IMPROVED** with the guard passed: propose the calibration as the A20 default (Philipp's call). Making it default
  needs its own PR with an ADR and the live advisor's packaging (the advisor refuses the flag today).
- **NOT_SHOWN or WORSE:** record it in the ledger; the flag stays off. Retraining the CTM on current-Silver rows
  (GPU on Philipp's PC) stays an option.

## Cost and run plan
- 2,048 seeds × 2 arms = 4,096 games, the same as the stage-3 A/B: about 7 h on 32 workers (4 lanes each, queue
  schedule, lease 30 min). 1,024 seeds: about 3.5 h. Expect a straggler tail: container speeds vary about 3× (§663).
- Share `/mnt/project-files/ctm-calibration-ab`. [`BRIEF-worker.md`](BRIEF-worker.md) and
  [`campaign.manifest`](campaign.manifest) are templates until the freeze (code commit, binary sha256, worker count,
  authorization).

## Smoke (this container, before the freeze)
See [`SMOKE.md`](SMOKE.md).
