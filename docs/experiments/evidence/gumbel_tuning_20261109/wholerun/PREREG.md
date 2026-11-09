# Gumbel tuning, confirmation in whole runs: c2 against §775's G16 + mb4, then the node reuse cap (pre-registration)

Replaces stage 3 of [../PREREG.md](../PREREG.md) (paired fights at 16k and 64k). Stage 2's pick is c2
([../RESULT.md](../RESULT.md), −1.12 HP per fight against ctl = `gsh16+flat16000+mb4`, a pick with the winner's curse,
not a test).

**Authorization.** Philipp, 2026-11-09 20:53 CET (project chat): "okay ja lass und c2 in ganzen läufen prüfen. node cap
danach ebenfalls." The plan below was posted in the tuning thread at 20:58 CET. No new seeds (§775's block), 40 workers
(his cap; the coordinator starts them).

## Question

Does c2's tree setting raise the A20 Heart kill rate of whole runs over §775's teacher G16 + mb4 (41.21%)?
Test 2 (after Test 1): does a node reuse cap of 262,144 instead of 32,768 raise it further?

## Arms (run_unit.sh)

All arms are §775's G16 + mb4 (`gumbel_wholerun_20261108/run_unit.sh`): net-0420 (sha 8c0bd16c) as the whole
out-of-combat policy (temperature 0, no OOC MCTS), every fight with the Gumbel root (k 16) at a flat 16,000 simulations
plus max backup (min 4 visits), Act 4 at the larger of that and Act 4 strong's budget (Shield and Spear 10k, Heart 40k)
with its prior playouts; `one_combat bestbench 16000 1 20 SEED`.

| arm | differs from §775's G16 | where its games come from |
|---|---|---|
| G16 | nothing | §775 (code 5665d5ae, binary 0eabb014); 32 sentinel seeds rerun here |
| C2 | c2's five tree settings in every fight: UCB exploration 12.5 at decision and chance children (`STS_SILVER_GUMBEL_ROOT_UCB`, default 25), root prior weight 100 (`STS_SILVER_ROOT_PRIOR_WEIGHT`, §775 400), tree prior from 32 visits (`STS_SILVER_TREE_PRIOR_MIN_VISITS`, §775 8), widening C 14.8 at end-turn and 1.85 at other chance nodes (`STS_SILVER_GUMBEL_ROOT_WIDEN_END_TURN` / `_WIDEN_CHANCE`, default 3.7028) | this campaign |
| C2CAP / G16CAP | C2 / G16 with `STS_SILVER_NODE_REUSE_CAP=262144` in every fight (the Heart's cap already) | Test 2 |

The tuning arm tokens set the same searcher fields (`ucb`/`wet`/`wch` through `NativeSilverSearchParams` at searcher
creation, `pw`/`tp` through the root prior weight and tree prior); in a whole run with net-0420's policy every Silver
search is a whole-run Gumbel search (§775: Gumbel roots = all decisions), so the process-wide `pw`/`tp` options reach
exactly those fights. Stage 2 tuned on acts 1-3 elite and boss fights; here c2 also plays hallway fights and Act 4.

## Seeds and units

§775's seeds 111378256-111379279 (1,024) in ascending order; smokes on 111379280-111379289 and §775 seeds (not
analysed). `units.txt`: first the 32 sentinel units `SEED G16` for 111378256-111378287 (lines 1-32, so the static
schedule runs them first), then 1,024 units `SEED C2`. One game per unit.

## Sentinel and control reuse (ADR-0064 §742)

The 32 sentinel games replay §775's G16 games with this binary. A game's fingerprint: rc, abort flag, the whole .log
except the BEST line's timing fields, and the .err lines `[heart1_ppo] seed=` (decision counts) and
`[silver] whole-run Gumbel roots= sims=` (every root's simulations summed). **32 of 32 identical = REUSE_VALID**: §775's
1,024 G16 games are the control. Anything else = REUSE_INVALID: no verdict against §775's games (CONTROL_INVALID); the
C2 games stand, and a G16 rerun on all seeds (about 146 lane-hours) needs Philipp's go.

## Primary (analyze.py, frozen with this file)

d = Heart kill C2 − G16 per seed. A seed counts if both games finished rc 0 with all log checks and an env matching
the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more than 20 = INCOMPLETE.
Universe: seeds whose C2 unit was claimed (unit directory or claims snapshot). Gate `tools/sprt_gate.py` gainer
(H0 0, H1 +2 pp), alpha 0.05 (one contrast), beta 0.05, look 64, cap = analysed seeds (≤ 1,024), seeds gap-free in
ascending order. PASS = GO; NOT_SHOWN = NOT_SHOWN; at CAP the (1 − alpha) seed bootstrap of mean d decides (10,000
resamples, seed 20261109): GO if lo > 0, STOP if mean ≤ 0, else INCONCLUSIVE. 95% CI always reported.

**Stopping.** Every seed runs (as §775 at Philipp's word); "crossed at" is reported.

**Power (inference).** §775's G16 − D had 244 discordant seeds of 1,024 (95% CI ±2.9 pp). With a similar discordance
the CI here is about ±3 pp: a gain of about +3 pp or more is likely to pass, +1-2 pp likely ends INCONCLUSIVE.

## Secondary (not gates)

C2 − D and C2 − G32 (§775's games) with 95% CIs; the primary's sprt_gate nonregression; per arm Heart kill, act-4
reach (final floor ≥ 52), mean floor, CPU sec per run and its ratio to §775's G16 (other machines: descriptive), games
over 1 h; the tree reuse counters of this binary's games (exit line `[silver] whole-run tree reuse:`): cap resets as a
share of kept-or-reset reroots, visits lost to cap resets and visits carried as shares of all simulations.

## Test 2: node reuse cap (after Test 1)

Same seeds, same binary, same analysis (`test2` in analyze.py): **C2CAP − C2** if Test 1 says GO, else
**G16CAP − G16** (§775's G16, valid only with REUSE_VALID). Its units file and launch come after Test 1's result, with
Test 1's cap counters reported first. Expectation (inference): at 16k the cap drops about 5-6% of the simulations in
acts 2-3 elite and boss fights (11-09 counters), and §682 saw +1.4 to +2.0 pp (n.s.) for a larger cap at 40k, so the
effect is probably below what 1,024 seeds resolve (±3 pp). If Test 1's counters show cap resets on under 1% of reroots,
the thread recommends skipping Test 2 and asks Philipp.

## Decision

No default change on either test. Test 1 GO: c2 replaces G16 + mb4 as the teacher candidate (AZ teacher, production
proposal). Otherwise G16 + mb4 stays. Test 2 GO: the candidate takes the larger cap.

## Cost and schedule

C2 is about 1.05× ctl's CPU in stage 2, so about 155 lane-hours for 1,024 games plus 5 for the sentinel; 40 workers
× 4 lanes, queue schedule, about 1.5-2 h (§775's longest G16 game: 51 min). Share: about 3,200 new files (tars, claims);
the share held about 40,000 files at 21:15 CET. Test 2 about 165 lane-hours.

## Smoke (2026-11-09, local, this binary)

G16 on 111378256 and 111378257 against §775's records, C2 and C2CAP on 111379280: results in the result file.
