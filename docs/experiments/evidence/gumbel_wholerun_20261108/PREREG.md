# Gumbel teacher in whole runs: A20 default combat vs the Gumbel root with max backup at 16k / 32k / 64k, net-0420 policy alone (pre-registration, 2026-11-08)

**Authorization.** Philipp 2026-11-08 23:23 CET (planning thread of this project): "gepaarte bestätigung bitte mit
dem ppo 420 net. und versuch mal default vs 16k gumbal, 32k gumbel und 64k gumbel mit max backup 4. erst nachdem der
momenate test gumbel run fertig ist, auf 40 worker dann." Seeds from the coordinator (23:27 CET). The run starts only
after the max-backup budget check (#1017, `gumbel_mb_budget_20261108`) has finished, on 40 workers, after an
independent prelaunch review.

**Question.** Does the Gumbel teacher of §770/§772 (Gumbel root k 16, max backup with min 4 visits) raise the A20
Heart kill rate of whole runs when it plays every fight, against today's A20 default combat? At which of
16k, 32k and 64k simulations per root?

**Motivation.**
- §770: the Gumbel root at 16k loses 0.88 HP per elite or boss fight less than production [−1.20, −0.57] on
  Baalorlord's states. §772: 32k −0.24, 64k −0.37 and max backup at 16k −0.29 HP more. #1017 (running) measures max
  backup at 32k/64k on the same states.
- HP per fight is a proxy. A descriptive, unpaired, not pre-registered comparison of existing data (planning thread,
  2026-11-08): stage 0's D0 (3,072 natural A20 runs, student_sel argmax without OOC MCTS, flat 10k production Silver,
  seeds 111860000-111863071) against D1 (1,024 runs, same environment plus the Gumbel root at flat 16k, seeds
  111900000-111901023) gives Heart kill 24.64% (SE 0.78) vs 29.00% (SE 1.42), +4.4 pp, about [+1.2, +7.5]; act-4
  reach 40.3% vs 44.3%. That is larger than the HP extrapolation (about 0.9 HP × 8 elite/boss fights × 0.19 pp/HP ≈
  +1.5 pp, §763) and needs a paired test.
- Philipp chose net-0420 (§760, the PPO baseline) as the out-of-combat policy instead of student_sel.

**Setup.** §767's whole-run setting with today's A20 default combat in place of combat B: LONG_C's net-0420 (sha
8c0bd16c…) as the whole out-of-combat policy, temperature 0, no OOC MCTS; `one_combat bestbench SIMS 1 20 SEED`.
Combat default (arm D, as the production arm of `../cheap_combat_proxy_20261031`): learned Silver stop
(gbt-0cac7cc64364), exact root budgets, g7f_E root table and prior (weight 400), tree prior K = 8, boss-only prior
playouts, Act 4 strong (Shield and Spear 10k with prior playouts, Heart 40k); SIMS = 10000.

**Code change** (this branch, default off): `STS_SILVER_GUMBEL_ROOT=K` makes every whole-run fight search each root
with `SilverSearcher::searchGumbelRoot` (§770's root: Gumbel-top-K over the g7f_E root prior, sequential halving,
c_visit 50, c_scale 1) at a flat budget of SIMS, in place of the learned stop. In Act 4 strong's fights (Shield and
Spear, Heart) the budget is the larger of SIMS and Act 4 strong's own (10k, 40k), and Act 4 strong's prior playouts
and reuse cap stay. `STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=M` adds max backup (min M visits, §759/§772) in exactly those
fights. Research overrides (arm threads, imagined OOC fights) and the stop trace keep their own settings. Philipp
2026-11-08 23:59 CET: Act 4 is part of the arms ("hä wieso sol akt 4 bei default bleiben?? mach das nicht"). Everything else in the search (prior, tree prior, prior
playouts, leaf, rollouts) is the default's. The binary reports the count of Gumbel roots at exit
(`[silver] whole-run Gumbel roots=N`). With neither variable set the code path is unchanged.

**Arms** (all four on every seed; D, G16, G32 in one unit in an order rotated by seed, G64 in its own unit):

| arm | added to the common environment | SIMS (Act 4: S&S / Heart) |
|---|---|---|
| D | (none) | 10000, learned stop (10k / 40k, plain root) |
| G16 | `STS_SILVER_GUMBEL_ROOT=16 STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4` | 16000 (16k / 40k) |
| G32 | same | 32000 (32k / 40k) |
| G64 | same | 64000 (64k / 64k) |

The combat setting changes every decision, so no control reuse.

**Seeds.** 111378256-111379279 (1,024 seeds) in ascending order; smokes 111379280-111379289. The coordinator
reserved both blocks on 2026-11-08. The main block was pre-registered as stage B of
`../boss_relic_forks_20261025` and never played (ledger: "111378256–111379023 … unused"; that campaign stopped after
stage A); 111379024-111379289 appear in no PREREG or units file on main. Every game goes through `tools/seed_guard.sh`.

**Primary endpoint and gate.** Per contrast X − D, X in (G16, G32, G64): d = Heart kill X − Heart kill D per seed.
`tools/sprt_gate.py` gainer (d0 0, d1 +2 pp), alpha 0.05/3 per contrast (Bonferroni), beta 0.05, look 64, pairs in
ascending seed order, cap = analysed seeds (at most 1,024). PASS = **GO**, H0 = **NOT_SHOWN**; at CAP the (1 − alpha)
seed bootstrap of mean d (10,000 resamples, seed 20261108) decides: GO if lo > 0, STOP if the mean ≤ 0, else
INCONCLUSIVE. The 95% CI is reported in every case. `analyze.py` implements this (`--self-test` passes).

**Validity.** A game counts if its rc is 0 and all log checks of `run_unit.sh` pass (net loaded, seed and SIMS line,
learned stop model, root prior, Gumbel banner and a non-zero Gumbel root count in G arms and neither in D, no other
research flag) and its `.env` holds the arm's Gumbel flags. A combat abort (stall) is a counted loss and listed.
Seeds without both games of a contrast are dropped and listed, never imputed; more than 20 dropped seeds in a
contrast = INCOMPLETE. A game killed by a signal (rc 137/143, issue #1001) makes `run_unit.sh` exit 3, so the queue
re-runs the whole unit as a new attempt (at most 4); a unit lost with its container is re-claimed after the 90-min
lease. A timeout (rc 124, 8 h per game) is final and a drop; the smoke bounds G64's wall time well below it. Units still
failing after 4 attempts are drops and are reported.

**Stopping.** `worker.sh` hands each worker its static share of `units.txt` (line i to worker (i − 1) mod 40 + 1) in
order and only then takes other workers' unclaimed units, so units are claimed roughly, not exactly, in seed order,
and a seed's two units (G64, and D/G16/G32) usually sit on different workers. Once all three gates have crossed
(PASS or H0) on the contiguous prefix of complete seeds, the author may stop the campaign with `worker.sh stop` on
every worker: no new claims, every claimed unit finishes. After all workers have finished, the author lists the
share's `claims/` directory into `claims.txt`; `analyze.py OUT_ROOT result.json claims.txt` then counts, per contrast,
the seeds whose units for that contrast were all claimed (a unit directory in the extracted tars or a claim in the
list). Whether a unit was claimed is fixed before any of its games ends, so a stop that leaves a seed's other unit
unclaimed removes the seed without selecting on outcomes; a claimed unit without valid games (failed 4 times, rc ≠ 0,
bad checks) is a drop. Without a stop every seed is claimed and the rule changes nothing. No other look at outcomes
changes the design.

**Secondary (not gates).** G32 − G16 and G64 − G32 (95% CIs); each contrast's sprt_gate nonregression. Descriptive per
arm: Heart kill, act-4 reach (final floor ≥ 52), mean floor, CPU per run and ratio to D, aborts, games over 1 h.

**Decision.** No default change on this result. A GO arm is a candidate for (a) the combat teacher of the AZ loop
and (b) a production default proposal, which needs Philipp's call on the CPU cost and its own gate with the
production out-of-combat stack. Interpretation: whole runs on net-0420's own decks and paths, so this is the
teacher's value in play, not on Baalorlord's states.

**Caveats fixed in advance.**
- Gumbel arms spend 1.6-6.4× D's nominal budget plus the root rule; the test measures the teacher as used, not equal
  CPU. CPU ratios are reported.
- One Gumbel setting (k 16, c_visit 50, c_scale 1) at all budgets, as in §770/§772.
- net-0420's out-of-combat play is fixed; a stronger combat changes which states it reaches.

**Cost and schedule.** From the smoke (one cloud core per game): D about 0.5-2 s per floor, G16 3-5 s, G32 4-9 s,
G64 roughly 2× G32; a G16 run that kills the Heart took 1,476 s. Singleton roots cost nothing under the Gumbel root (a
root with one edge searches nothing), although exact root budgets are on. Estimate for all 1,024 seeds: up to about
1,000 lane-hours, 6-7 h on 40 workers × 4 lanes, with G64 games on deep runs of 2-3 h (below the 8 h timeout, but
in reach of container resets; those units are re-run, see Validity). With an effect near the D0/D1 point estimate the
gates should cross after a few hundred seeds and the run can stop early (Stopping). Philipp 2026-11-09 sets the
scope on the new estimate (decision card in the planning thread).

**Smoke** (2026-11-08/09, cloud, binary 0eabb014 of code 5665d5ae, smoke seeds 111379280-111379288, not part of the
analysis): every game rc 0 with all log checks; in G arms the Gumbel root count equals the decision count (e.g. G16
on 111379288: 873 of 873 decisions, Heart kill, Act 4 included); D shows neither banner nor count. Per-game walls
and floors are in the PR description.
