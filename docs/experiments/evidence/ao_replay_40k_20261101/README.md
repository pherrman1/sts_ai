# Awakened One replay: production vs flat 40k (pre-registration, 2026-11-01)

Philipp (11-01, decision card "Smoke, dann ~125 core-h" on "Awakened-One-Replay (Produktion vs. flat 40k)
vorbereiten?"; the run itself still needs his typed go with a worker count). Follow-up of roadmap X5 (§740): Awakened
One is the only fight cluster that clears the X5 rule (8.3% of runs, sibling bound +3.11 pp, ≈ +1.0 pp relative to
the expert), and 69% of its deaths re-die in ≥ 3/4 redraws (§698 replays), so most look state-determined. This run
asks whether the rest is a play problem that more search fixes.

**Question.** Does flat 40k simulations per root (no learned stop) lose fewer recorded A20 Awakened One fights than
production combat, replayed from the same pre-combat states with the same battle seeds?

**Data.** The Awakened One fights of §727 arm A (A20 default at code 8f5b17d6, 1,536 seeds 111312000-111313535;
tars on /mnt/project-files/value-chooser-ab/units, hashes in `source_tars.sha256`). 544 seeds have an AO fight (one
each; 120 recorded deaths, 22.1%). Units = the first 304 of them in seed order (111312001-111312805, `units.txt`),
picked for the ~125 core-h budget; seed order is unrelated to outcome. No new seeds: battle redraws use
SEED_BASE 740000001 (`one_combat fightreplay`). Rows: `tools/fight_replay_rows.py --arm A --rooms BOSS`, filtered to
encounter 53.

**Arms** (`run_unit.sh`, both on every unit, 3 copies each):
- P: production, the §727 arm-A environment verbatim (learned stop gbt-0cac7cc64364, exact root budgets, g7f_E
  rollout table and prior, Act-4 strong, student_sel). Copy 0 replays the recorded seed and must reproduce the
  recorded fight exactly (identity gate; the log line is checked, rc 97/1 otherwise).
- F: P + `STS_FIGHT_REPLAY_FLAT=40000` (new, default off, `apps/one_combat/fight_replay.cpp`): flat 40,000
  simulations at every root, singletons searched, no learned stop; the same override as expertfights' `flat40000`
  (§716/§718). Copies 0-2 use the same battle seeds as P's copies 0-2, so the arms are paired copy by copy.

Code main 8eec7b9 = §727's combat code (only `silver_synth_gen.cpp` differs) plus the F switch.

**Primary metric.** Per-fight death rate F − P (mean of the 3 paired copies per entry, then mean over entries), 95%
entry bootstrap (4,000, rng 740). `analyze.py UNITS_DIR`.
- PLANNING_LIMITED: dDeath ≤ −4 pp and CI upper < 0.
- NOT_PLANNING_LIMITED: CI lower > −4 pp.
- otherwise INCONCLUSIVE.
A unit counts only with rc 0 and all 6 replays valid; others are listed, not imputed.

**Secondary (descriptive).** HP lost F − P (death = entry HP), CPU per copy, identity count, recorded-death share, and
the run-level translation −dDeath × 5,543/15,363 AO entries per run × 0.59 P(Heart kill | survived AO) (§740).

**Decision.** PLANNING_LIMITED → propose an AO-specific budget follow-up (budget schedule A/B at matched CPU, own
prereg). NOT_PLANNING_LIMITED → AO deaths are deck/state problems; the X5 lever moves to deck building (ledger, no
default change). INCONCLUSIVE → ledger, no follow-up without Philipp.

**Prior evidence against.** §718: flat 40k on expert boss states gave no gain (AO +2.0 HP worse, n.s.). A 40k tree
also loses most reuse (Silver reuse cap 32,768).

**Cost and power.** Smoke (author, 13 of 16 entries finished before the container's 2-h limit, seeds every 34th of
the 544, e.g. 111312001, 111312089, ..., 111313257; local build of this branch): identity 13/13, all rc 0; CPU per
copy P 56 s, F 449 s (max 1,206 s) → ≈ 1,515 CPU-s per unit, **≈ 128 core-h for 304 units**; unit wall up to 62 min
(single-threaded). Smoke dDeath −5.1 pp (13 entries, not a result), entry-level SD of the paired difference 0.125 →
CI half-width ≈ ±1.4 pp at 304 entries, enough to separate −4 pp from 0.

**Campaign.** `campaign.manifest` (tools/cloud/worker.sh, parallel 4, queue, lease 150 min). Workers: Philipp's
number (16 workers ≈ 2.5-3 h wall). Output `/mnt/project-files/ao-replay-40k/units/<seed>/`.
