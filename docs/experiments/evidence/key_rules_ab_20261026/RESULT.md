# Key rules A/B at A20: result (KEYS_EXPLAIN)

Run 2026-10-26 23:4xZ – 2026-10-27 03:2xZ, RUN_COMMIT `89e6ba90` (code `db216ff0`, binary `d74cfded…`), 16 cloud
workers, 1,024 paired seeds 111382000–111383023. Pre-launch review PASS (reviewer G,
`/mnt/project-files/reviews/key-rules-ab-prelaunch.md`). `verify.txt`: all 1,024 units OK, no duplicate, one run
commit, 16/16 worker DONE files; `tars.sha256` lists the unit tars on `/mnt/project-files/key-rules-ab/units`.
Analysis: `python3 -I analyze.py <extract dir> result.json`. All 2,048 games valid; no pair dropped (the analyzer drops
a pair when either arm is invalid; none was).

## Primary (frozen rule: KEYS_EXPLAIN if Δ ≥ +4.0 pp and CI above 0)

| | R (rigid, main's default) | F (flexible) | F − R, paired [95% bootstrap CI] | discordant F only / R only | exact McNemar p |
|---|---|---|---|---|---|
| Heart kills | 212 (20.7%) | 274 (26.8%) | **+6.05 pp [+3.42, +8.59]** | 126 / 64 | 8.1e−6 |
| reached Act 4 | 340 (33.2%) | 418 (40.8%) | +7.62 pp [+4.88, +10.35] | 147 / 69 | 1.2e−7 |
| kills per Act-4 arrival | 0.624 | 0.656 | | | |
| mean final floor | 38.58 | 41.45 | +2.86 [+2.04, +3.68] | | |
| deaths act 1 / 2 / 3 / 4 | 181 / 292 / 211 / 128 | 148 / 241 / 217 / 144 | | | |
| wall per game, mean (max) | 234 s (1,894) | 285 s (2,134) | | | |

**Verdict: KEYS_EXPLAIN.**

## Where the gain comes from

First divergence (F − R pairs; Heart and Act-4 deltas summed over the class):

| first differing decision | seeds | Δ Act 4 | Δ Heart kills |
|---|---|---|---|
| Act-1 REWARDS with a Sapphire offer (R: key rule; F: tree rule or student_sel) | 901 | +78 | +63 |
| identical games (F's student_sel also took the Sapphire in Act 1) | 91 | 0 | 0 |
| Act-3 campfire (R: Recall rule; F: student_sel) | 26 | +2 | −2 |
| other | 6 | −2 | +1 |

Key timing (per arm, runs that hold the key):

| | R | F |
|---|---|---|
| Sapphire held: act 1 / 2 / 3 | 1,000 / 0 / 0 (floor 8.8) | 208 / 375 / 194 (floor 25.4) |
| relics at the start of Act 2 | 5.47 | 6.32 |
| Ruby held: runs, mean floor, HP fraction | 520, floor 41.2, 0.79 | 572, floor 46.2, 0.85 |
| Emerald held: runs (act 1 / 2 / 3) | 770 (506 / 180 / 84) | 818 (508 / 204 / 106) |

**Inference:** nearly all of the gain enters at the first Act-1 chest. Under F, student_sel defers the Sapphire in about
80% of runs and keeps the chest relic (+0.85 relics entering Act 2), which shows as fewer Act-1/Act-2 deaths. The pairs
that first diverge at an Act-3 campfire (flexible Ruby) are too few to show an effect; the flexible Ruby and Emerald
rules also act later in pairs that already diverged, so their own share is not separated here.

## What this says about §566 → §569

On today's stack, flexible keys alone add +6.1 pp to student_sel alone (20.7% → 26.8%). §566 (rigid, OOC MCTS, older
combat stack) scored 17.6% and §569 (flexible) 25.8% / 23.4%. **Inference:** the key rules are the largest single cause
of the jump (about 6 of its 8 pp); the rest fits the combat-side changes (§564 rigid at 20.1–21.5%). The cross-campaign
remainder is unpaired.

## Notes
- Act 4 strong (ADR-0060) is on by default at this code; `run_unit.sh` has no banner check for it (review note 1).
  Both arms ran the same binary and environment apart from `STS_KEY_*`.
- R is main's default (`RunGoal.cpp`); every campaign since §569 runs F. No default changed in this run.
- Follow-up (Philipp's call): make flexible keys the A20 default ("=first restores"), and check the live advisor's key
  flags, which read the same defaults.

Seeds used: 111382000–111383023 (campaign), 111383024–111383027 (smokes).
