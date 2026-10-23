# CTM-calibration guard at A20 (pre-registration)

**Status: authorized, to be frozen after the default's review.** Revised on 2026-10-23 before any game of the guard ran.
This file first pre-registered an A/B that asked whether the calibration kills the Heart more often (two stages, 512
then 1,536 seeds; §670 and PR #838 hold that version). On 2026-10-23 at 20:32Z Philipp argued that the CTM should be
judged by its precision, not by winrate. At 20:44Z he chose "Default on + 512-seed guard" on the card "Adopt the CTM
calibration on precision, and with what play check?": the calibration became the A20 default (ADR-0058), and 512 seeds
check that it does not clearly lose. At 20:45Z he authorized the run ("The 512 seeds can use 8 workers later") and at
22:11Z raised it to 16 workers ("U can also use 16 workers"). The campaign is frozen as usual (`campaign.manifest`,
brief, run commit) after the default's PR is reviewed and merged.

## Question
In today's A20 search stack, does the CTM calibration, now the default, kill the Heart clearly less often than the raw
CTM (`STS_CTM_CALIBRATION=0`)?

## Background
[`README.md`](README.md): over the stage-3 A/B's 97,561 real fights, the A20 CTM predicts too many deaths at most
bosses (the Heart 0.486 against 0.370 observed, Act-1 bosses 0.093 against 0.050) and too much HP loss in Acts 2–4
(Act-3 bosses: mean HP after a won fight 19 HP too low). The per-fight calibration predicts held-out fights better
(log loss 0.0733 → 0.0698, won-fight HP error 8.2 → 7.6 on the 256 stage 1–2 games), but below 20 HP it makes Act-3
fights look safer than they are (README, "By pre-fight HP"). The OOC search's rollouts play up to three combats
through the CTM before the M0 leaf, and every Act-4 rollout ends in a CTM death or Heart kill (§663), so the CTM sets
how much the search fears a fight.

## Arms ([`run_unit.sh`](run_unit.sh) is the source of truth)
- **A:** today's A20 stack with the raw CTM, `STS_CTM_CALIBRATION=0` (no calibration banner, checked). Otherwise the
  stage-3 A/B's config (§661, `../value_level_ab_20261023/run_unit.sh`) with the M0 leaf, which is the default
  (ADR-0057; banner `leaf_calibration_min_ascension=20` checked): student_sel OOC prior and rollout net (`cf6bf7fb…`),
  OOC MCTS 4096 sims, rollout3 native leaf, learned OOC stop 0.99, 25% full-budget roots, fast roots capped at 1024,
  learned Silver stop with exact root budgets, g7f_E root table and prior, boss-only prior playouts, keys on, CTM rows
  on.
- **C:** the same with `STS_CTM_CALIBRATION` unset: the default applies the bundled table
  `models/candidates/ctm_calibration_pathb_a20_v1.json` (sha256 `359619f7…`; banner checked). Nothing else differs.
- The equivalence check ([`../ctm_calibration_default_20261023/`](../ctm_calibration_default_20261023/README.md))
  shows that C plays exactly as the §670 flag `STS_CTM_CALIBRATION=<table>` did before the default, and A exactly as
  the code before the default.
- One unit is one seed with both arms in sequence, order rotated by seed % 2, on one lane: wall times compare within a
  lane. 7 h timeout per arm.
- Real combats are the same Silver in both arms; only the OOC search's imagined fights change.

## Seeds
111392000–111392511 (512, [`units.txt`](units.txt); from the 2,048 seeds 111392000–111394047 that the coordinator
assigned on 2026-10-23 at 18:30Z). The first plan's second stage ([`units-stage2.txt`](units-stage2.txt),
111392512–111394047) is dropped; those seeds stay reserved and unused. The smoke used 111394990–111394999
([`SMOKE.md`](SMOKE.md)); the equivalence check reruns two of them.

## Endpoints
- **Primary:** Heart kills, C − A per seed: mean and 95% seed-bootstrap CI (10,000 resamples, RNG seed 20261023).
  **WORSE** if the upper bound is below 0, **IMPROVED** if the lower bound is above 0, else **NOT_SHOWN**. The exact
  McNemar test on discordant seeds is reported alongside.
- **Wall:** mean wall C / A, reported. The calibration adds almost no CPU per CTM call, so a ratio above 1.10 would
  come from longer games; it is flagged to Philipp but does not enter the decision.
- **Secondary (descriptive):** reached Act 4; deaths by act; mean final floor; from the CTM rows, by act: real elite
  fights per run, mean HP entering a fight, and fights entered below 20 HP per run with their death rate; searched
  roots, picks off the prior's argmax, learned-stop and root-lock shares at fast roots.
- **Validity:** a seed counts when both arms end with rc 0 and a complete, integrity-passed footer. Other seeds are
  listed and left out.
- Analysis: [`analyze.py`](analyze.py) on the verified extraction (`tools/cloud/verify_campaign.py`).

## Power
Stage 3's M − A at 1,024 paired seeds had a 95% half-width of 2.6 pp, so at 512 seeds the SE of C − A is about
1.9 pp. The guard calls WORSE with probability about 0.025 if the calibration is harmless, 0.18 at a true −2 pp, 0.35
at −3 pp and 0.75 at −5 pp. It catches large losses only; a loss of about 2 pp would mostly go unnoticed. IMPROVED
would need a gain of about +3.7 pp to be called half the time.

## Prediction (frozen here)
- Primary: point guess 0 pp, so NOT_SHOWN. M0, which cut the search's over-priced deaths, gained +2.15 pp (§661); the
  last CTM calibration A/B, the Act-4 survival model, was NOT_SHOWN at −1.4 pp (75 vs 82 Heart kills of 512, §534);
  the 10-seed smoke leaned against the calibration ([`SMOKE.md`](SMOKE.md)).
- Play (descriptive): with fewer imagined deaths and less imagined HP loss in Acts 2–3, C should fight more elites in
  Acts 2–3 than A and enter fights with less HP. In the smoke C entered Act-2 fights with less HP (64.6 against 67.9).

## Decision
- **WORSE:** a PR turns the default off (unset means the raw CTM again; the table stays a research option). Philipp
  merges it.
- **NOT_SHOWN or IMPROVED:** the default stays.
- Either way the result goes to the ledger.

## Cost and run plan
- 512 seeds × 2 arms = 1,024 games: about 3.5 h on 16 workers (4 lanes each, queue schedule, lease 30 min), plus a
  straggler tail (container speeds vary about 3×, §663).
- Share `/mnt/project-files/ctm-calibration-ab`. [`BRIEF-worker.md`](BRIEF-worker.md) and
  [`campaign.manifest`](campaign.manifest) are templates until the freeze (code commit, binary sha256, 16 workers,
  authorization).
- The freeze builds the binary from the merged default and reruns one equivalence-check seed on it; its records must
  match the check's.

## Smoke (this container, before the default)
See [`SMOKE.md`](SMOKE.md): the first plan's 10-seed smoke, with the calibration as a flag on the pre-merge binary.
