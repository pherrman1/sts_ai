# Order dominance pilot (#1057): frequency, soundness and equal-CPU picks at G16 roots (pre-registration, 2026-11-15)

**Scope.** A small data run in the thread's own cloud container (4 cores), no workers, no new seeds: whole A20 runs of
§797's seed block, replayed bit-identically, with extra fresh searches after each played search. It is a pilot that
decides whether a 256-run data run (§797's full block on workers) is worth asking for. No gate, no default change.

Request: Philipp, 2026-11-15 17:08 CET, project chat: one thread per issue created today, worked through per thread
(coordinator: GitHub issue #1057; "whole runs only on gain and with Philipp's typed go").

## Background

- Silver merges equal states (transpositions), but not dominated orders: Strike then Bash and Bash then Strike reach
  different states, and the first is never better. tfriedel/spire-mentor prunes them (`dominance.rs`).
- §658 (2026-10-23): turn-level end-state dominance of Silver's *chosen* root edge, 0.65% material → DROP. That
  measured a search-quality target (does Silver choose a dominated line), not the budget an in-tree pruning frees.
- The order test cannot prune the real root: it compares two paths from a common ancestor, and the root has none in
  the graph. Pruning therefore acts at decision nodes below the root, which changes the Gumbel root's candidate values
  and how the 16k budget is spent beneath each candidate.

## Intervention

`SilverSearcher::orderDominance` (research option `STS_SILVER_ORDER_DOMINANCE=1`, default off; `SilverDominance.h`):
at a decision node X reached from decision node P by a deterministic card play b, each card play a at X is pruned
when a-then-b from P reaches a state equal for search to X + a except that no monster has more HP and at least one
has less (same monsters alive; player HP and block equal; both plays consume no search randomness). Guard: no test
while the Mystic, Centurion, the Champ or Time Eater is alive (their AI reads monster HP). Off, the search is
unchanged bit for bit.

## Data run

- **Generator.** `one_combat silverazgen` with §797's environment ([record_env.sh](record_env.sh)) without the budget
  ladder, plus `STS_AZGEN_DOMINANCE_LADDER=16000:5,8000:4,4000:3` (fresh Gumbel k 16 searches with pruning on at 16k /
  8k / 4k, seeded like §797's ladder slots 16k / 8k / 4k) and `STS_AZGEN_DOMINANCE_AUDIT=16` (dominated edges in the
  played, unpruned tree at nodes with ≥ 16 simulations).
- **Seeds.** 111980000-111980031 (32 of §797's 256 games; reused, data only). `run_unit.sh` refuses any other seed.
  If the container's time does not allow 32, the first 16 seeds; the count used is reported.
- **Sentinel.** Every run's played choices must equal §797's rows of that seed; a differing run is dropped and
  reported.

## Measurements (frozen with analyze.py)

1. **Frequency** (played tree audit and pruned shadows): share of searched roots whose played tree holds a dominated
   edge; dominated edges per test; share of the root's simulations that entered a dominated edge (`wasteShare`); edges
   pruned per tested node in the pruned searches; guard hits; the test's share of the pruned search's CPU; all by
   group (hallway, elite, boss, Shield and Spear, Heart).
2. **Soundness** (descriptive): for dominated pairs in the played tree where both the dominated child and the
   dominating state have ≥ 64 (and ≥ 256) simulations, the share where the dominated child's max-backed Q exceeds the
   dominator's, and the mean difference. Exact dominance predicts ≤ 0 up to search noise.
3. **Equal-CPU picks** (§797's metric): loss = Q_ref(best) − Q_ref(pick), Q_ref the played 16k tree's max-backed Q.
   - paired: dom:b − §797 p1:b at the same Gumbel seed (same candidates; only pruning differs), and its CPU ratio;
   - frontier: dom:b − F(CPU), F the lower convex hull of §797's 1k-16k points (CPU scaled to this machine by the
     ratio of the played searches' CPU, as §798);
   - run-clustered bootstrap, 10,000 resamples, seed 20261115, 95% intervals.

## Decision rule (pilot)

- **ASK_FULL_RUN** if dom:16000 or dom:8000 has a frontier Δ below 0 with its 95% upper bound < 0, or a paired Δ < 0
  with upper bound < 0 at a CPU ratio ≤ 1.1, and the soundness share at ≥ 256 simulations is ≤ 50% (no sign of
  systematic error). Then ask Philipp for §797's full 256-run block on workers (its own pre-registration).
- **DROP** if both arms' point estimates are ≥ 0 on both comparisons, or the waste share is below 1% of simulations.
- Otherwise **INCONCLUSIVE**: report and let Philipp decide.
- The reference favours picks like the unpruned played search's, which works against the pruned arms
  (conservative).
