# Fresh boss-relic selection precision: K4 versus K16

## Authorization, scope and clock

The user accepted a new four-hour continuation after being offered this exact
fresh-source experiment. Start: **2026-10-08 11:02:24 Europe/Berlin**. Overall
deadline: **15:02:24**. This is a separate conditional diagnostic within the
research charter, following the completed overnight campaign and draft PR #442.
The earlier RemoveLow champion, 512-pair confirmation and verdict remain closed.
No old confirmation outcome is a label, selector input or stopping rule here.

The accepted design is the prior `gen2_next_k_experiment_proposal.json`.
Resource limits are revised before new outcomes: use at most **six** one-thread
source processes, a **10,800-second** collection cap and an absolute collection
stop of **14:22:24**, whichever comes first. This leaves forty minutes for
analysis, independent review and packaging. Each source has an **1,800-second**
timeout. Standard `timeout` controls the entire `xargs` process group, with a
thirty-second termination grace; this grace is not additional scientific work.
No other campaign game job may run alongside these six workers.

All game commands pass through `tools/seed_guard.sh`. Use the existing reviewed
`run_gen2_source.py`, immutable producer and exclusive per-source output paths.
No scheduler, source replacement, retry, replenishment or adaptive extension.
An incomplete or invalid allocation is reported, not repaired by new games.

## Hypothesis and competing explanation

Four simulated selection futures may choose a noisy winner. Increasing this to
sixteen at the same state may improve the chosen action on independent futures.
Alternatively, near-ties, heterogeneous states or teacher/sampler limitations
may dominate, so additional selection precision gives no independent benefit.
Neither historical P0/F2 model selects an action in this comparison.

The only selector difference is the number of selection futures. The source
state, retained legal actions, continuation policy, sampling procedure, tie
rule and evaluation futures are shared. K4 is nested inside K16, so they are
correlated selectors rather than independent policy samples.

## Frozen allocation and producer

Use exactly **32 fresh sources, 610084200 through 610084231 inclusive**.
Retain at most one `BOSS_RELIC` state per source using the producer's existing
deterministic per-type reservoir. No selection by outcomes, apparent regret,
act or disagreement. The existing option cap retains at most six options and
the actual source-policy choice. Valid sources with no eligible state remain
in the primary denominator with zero incremental gain.

The producer is the previously reviewed immutable `3ed91ab3` binary, SHA256
`27a78efd3f5da731897d36dd9b50a622d2ace4f54dae69dfc157bf6712b027c7`.
Reuse its exact GEN2 Fprod teacher and unchanged model artifacts: Ironclad A0,
Act-3 cutoff, keys off, optional-Recall correction, native public8 fallback,
MCTS off, V4 gates/margin 1, native Silver learned stopping with nominal 10k
cap, adaptive/exact budgets off, allocated reuse cap 32768, OMP/BLAS threads 1.
Do not substitute the later RemoveLow teacher: that would also change the
source/continuation policy and weaken comparison with the original diagnosis.

`freeze.json` binds the source, executable, teacher, policy, models, runner,
seed guard, new verifier, analysis, imported helpers, protocol and actual
Python/NumPy runtime. Independent reviews and a ready bundle precede launch.
No gameplay-source modification or extra seed-based canary is needed for a
previously verified producer whose existing K loop supplies these samples.
Synthetic checks must cover the newly supported K32 verification and analysis.

Preserved K8 mixed-family data are reused only for cost and implementation
context; they cannot supply a fresh K16 selection plus sixteen-future evaluation.
The artifact/freshness inventory records the inspected allocations and its
limits. Protected historical TEST is never opened.

## Selection, freezing and evaluation

Collect **32 coupled futures per retained action**, k0 through k31. Siblings
share the producer's future identity for their source, decision and k. All
collection files remain custody-bound; no efficacy inspection occurs during
collection. The contract verifier may check validity/label domains and runtime
health, but does not report evaluation win counts or rank actions.

1. Require every allocated source/retained branch and its MAP companion to pass
   the reviewed contract. Any invalid source, missing/duplicate branch, changed
   artifact or fatal health finding blocks a clean primary inference. Do not
   require every branch to contain a combat; source/branch identity limits of
   the profiler remain explicit.
2. A reviewed selection program interprets final-win labels only for k0..15.
   K4 ranks each option by mean final-win outcome over k0..3; K16 uses k0..15.
   Both favor the actual source-policy choice on an exact maximum tie, then
   the lexicographically smallest semantic option key. No threshold or model
   scoring is fitted. Save both choices, their scores, state identities and
   all input hashes to a refuse-overwrite artifact.
3. Hash that choice artifact before opening evaluation outcomes. A separate
   evaluator accepts the exact choice hash and never reranks or recomputes a
   chosen action from evaluation data. It interprets only k16..31 for effects.
   No outcome-dependent extension, subgroup selection or changed tie rule.

## Primary estimand and fixed interpretation

For each eligible source, compute the mean of the sixteen paired differences
`finalWon(K16 choice) - finalWon(K4 choice)` on k16..31. Use zero for an otherwise
valid no-state source. The primary estimate is the equal-weight mean over all
32 allocated source values. Resample whole sources, not individual futures,
using the unchanged repository `paired_analysis.bootstrap_ci`, 10,000
replicates, percentile 95% interval and NumPy RNG seed 20261008.

With all gates passed:

- Lower interval bound strictly above zero:
  `LOCAL_K16_SELECTION_GAIN_SUPPORTED`.
- Upper interval bound strictly below zero:
  `LOCAL_K16_SELECTION_HARM_SUPPORTED`.
- Otherwise: `LOCAL_CONDITIONAL_INCONCLUSIVE`.

Failure/incomplete allocation is `EXECUTION_BLOCKED`, with all retained failure
evidence and no replacement. There is no two-percentage-point promotion rule:
this is a conditional diagnosis, not a population win-rate qualification.
Report the exact point estimate, interval, both discordance directions and
number of choices changed. Comparisons of each selector with the captured
source-policy action, per-act contributions, exposure/ties and selection means
are descriptive only; they cannot create additional winners or stopping rules.
A zero empirical interval with unchanged choices is not proof of equivalence.

## Cost and limitations

The previous BOSS labels cost 7.1863 game-thread CPU seconds per continuation.
Typical four-option exposure gives 4,096 branches, about 8.3 game-core-hours;
the conservative six-option ceiling gives 6,144 branches, about 12.4 core-hours
before tail overhead. At six processes these project about 1h23 and 2h04,
respectively. These are feasibility estimates, not completion guarantees.
Report actual source/branch CPU, process-wall sums and parallel elapsed time
separately. Thirty-two sources are not thousands of independent observations.

The existing sampler preserves latent counters and pool membership and is not
an exact posterior over only player-visible information. Only retained legal
options are covered. A result concerns selection precision at these reached
boss-relic states under this fixed teacher; it does not install an online
selector, establish live-game fidelity or qualify a whole-run policy. No
training, merge, production-default change or new holdout opening follows.

## Ownership and handoff

Coordinator owns this protocol, freeze, dispatch and final integration.
Learning owns the new analyzer/tests. Integrity authors the new verifier and
reviews the analyzer; strategy independently reviews that verifier and the
scientific design. The coordinator serializes commits and launch. Final raw
analysis and interpretation receive independent review. Add results to the
existing draft-PR handoff and maintained experiment/research destinations;
preserve every earlier result and raw artifact.
