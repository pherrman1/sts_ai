# Learned budget per decision: budget ladder at every root of G16 runs (pre-registration, 2026-11-12)

**Authorization.** Philipp, 2026-11-12, learned-budget thread: "ich will ein fucking model haben das den context
sieht und sims vorschlägt" (20:15 CET), "okay trainier das netz, aber mach es doch auf der gpu" (20:32 CET), then the
decision card "Datenlauf mit Budgets pro Zug" (20:49 CET). This is a data run, not a gate. Seeds and worker count
needed his typed go (AUTHORIZATION line below).

AUTHORIZATION: Philipp, 2026-11-12 21:02 CET, in this thread: "ich geb dir jetzut schonal go für 40 worker" (40 workers, the 256 seeds above).

## Background

- §794 and §796: a learned *per-fight* budget is NOT_SHOWN over 1k-64k. Per fight there is little reproducible
  signal (split-half r 0.13 for 1k → 16k).
- Offline step 1 ([search_gain_net_20261112](../search_gain_net_20261112/results/result.json), tools/combat_net/search_gain.py):
  on D2's 3.1 M Gumbel roots, a net on the full combat state (CombatNet trunk, init T1 N_f1, gain head) ranks roots by
  the 16k search's gain over the prior's top action far better than root statistics: Spearman 0.49 vs 0.36 on 562
  held-out runs; the top 10 % of roots by the net hold 36 % of the total gain (baseline 25 %, random 10 %), the top
  50 % hold 89 % (73 %); within room classes 0.45-0.51 vs 0.31-0.37.
- That data has only two budget points (0 = prior, 16k) and no CPU per root, so it cannot say which budget a root
  needs. This run adds both.

## Question

At each combat decision, does a model that sees the full state choose a budget from {0 (prior), 1k, 2k, 4k, 8k, 16k}
so that the value lost to a strong reference search is smaller than with a uniform budget at the same CPU?

## Data run

- **Generator.** `one_combat silverazgen` with D2's environment ([record_env.sh](record_env.sh); §775's G16 arm:
  net-0420 out of combat at temperature 0, every fight under the whole-run Gumbel root k 16 at flat 16,000 with max
  backup 4, boss prior playouts, Act 4 strong), plus `STS_AZGEN_BUDGET_LADDER=1000,2000,4000,8000,16000`.
- **Ladder.** After the played search of every searched multi-edge root, the root is searched once per ladder budget
  by a fresh searcher configured as the played one (same prior, tree prior, playouts, max backup; no reuse), each with
  its own Gumbel seed. Each pick is recorded as an index into the played root's edges, with its thread CPU seconds,
  and the played search's CPU (`mainCpu`). Play, the played tree and every RNG it reads are unchanged: the main line
  is bit-identical with the ladder on or off (SMOKE.md).
- **Reference.** The played search (16k, with reuse) is the evaluator: each pick is scored by the played tree's
  max-backed Q of that edge. The ladder's own 16k pick is a fresh, independent search, so the 16k arm is scored like
  every other arm and the evaluator's preference for its own pick does not favor any arm.
- **Seeds.** 111980000-111980255 (256 A20 runs, a fresh block no ledger entry has used; smokes 111989990-999).
  `run_unit.sh` refuses any other seed. Units of 1 run (256 units; a heavy run takes up to about 1.5 h, and container resets kill units after 2-3 h).
- **Code / binary.** Code commit and binary sha256 in campaign.manifest (main + the ladder recorder, default off).

## Analysis (frozen with this file, run after the data; PC GPU)

- **Rows.** Searched multi-edge Gumbel roots with a root prior whose ladder has all 5 picks matched (pick edge ≥ 0)
  and whose picked edges all have a finite max-backed Q in the played tree. Dropped rows are counted by reason.
- **Loss per root and budget.** loss_b = Q_ref(best) − Q_ref(pick_b), with Q_ref the played tree's max-backed Q and
  best its maximum over visited edges; loss_0 uses the prior's top action. CPU_b = the ladder search's CPU
  (CPU_0 = 0).
- **Models.** Cross-fitted by run (5 folds, the T1 hash split for folds). Each predicts loss_b and log CPU_b for all
  six budgets:
  - M0: per-budget constants (= uniform policies);
  - M1: gradient-boosted trees on the root statistics of search_gain.py's B0 (+ encounter);
  - M2: the CombatNet trunk (init T1 N_f1) with a 6 × 2 head on [CLS, the same statistics] (search_gain.py
    extended), trained on the PC GPU.
- **Predictions.** Predicted losses are made non-increasing in the budget (cumulative minimum over b); predicted
  CPU is exp(the log-CPU prediction) times Duan's smearing factor from the training rows, so it estimates mean CPU.
- **Policy.** b*(x) = argmin_b loss_hat_b(x) + λ · cpu_hat_b(x), λ by bisection so that the mean predicted CPU of the
  out-of-fold predictions equals the target (predictions only, no realized outcome). If no λ reaches the target, the
  policy at the smallest λ is scored at its realized CPU.
- **Targets.** The mean CPU of uniform 2k, 4k and 8k.
- **Primary contrast.** Per root, the policy's realized loss minus the uniform frontier's loss at the policy's
  realized mean CPU (the lower convex hull of the 6 uniform budgets, linearly interpolated), in Q units. Run-clustered
  bootstrap CIs (10,000 resamples, seed 20261112) at 98.33 % (Bonferroni for 3 targets, α 0.05), for M2; M1 is
  co-reported.
- **Decision rule.**
  - **GAIN** if M2's contrast has CI upper < 0 at one or more targets. A whole-run gate of the M2 budget policy
    against G16 (and against a uniform budget at the same CPU) would follow, with its own go.
  - **NOT_SHOWN** otherwise (ledger, parked).
- **Co-reported.** Realized CPU vs target; M2 vs M1; the choice mix per room class; losses by act × room; the oracle
  (per-root argmin of realized loss + λ · CPU) as an upper bound; split by whether the root inherited visits.
- **Caveats.** Losses are in the search's own value scale (Silver score), not Heart probability; the fresh ladder
  searches have no tree reuse, while the stack reuses trees, so a reused root needs less than a fresh one; Q_ref is
  one 16k search and noisy.

## Cost and schedule (SMOKE.md)

See SMOKE.md for the measured cost per run. Queue on the approved workers × 4 lanes, lease 90 min, unit timeout
10 h (rc 124 final, listed as a drop).
