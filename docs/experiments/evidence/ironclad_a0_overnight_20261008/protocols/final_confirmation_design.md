# Final confirmation design, before champion selection

This document binds the already reserved final comparison without selecting a
champion or opening its outcomes. The final source/configuration manifest and
independent release review are still required before any seed is run.

Objective: fair Ironclad A0 Act-3 victory, keys off. The comparator is corrected
Fprod: public8 native fallback, optional Recall excluded when another action is
legal, original tracked models, learned stopping, MCTS off. Original Bprod
exposes hidden encounter identities and is diagnostic only. This changes the
information-boundary reference; no claim against its inflated/changed historical
scores will be made.

## Eligibility and nomination

Require every predeclared discovery and fresh-development pair for an eligible
candidate to be valid, with strictly more development wins than its matched
Fprod. No partial results, extra seeds, outcome-dependent retries or pooling.
The Wave3 cohort first resolves FullHp versus ShopOff by its frozen most-wins
rule and FullHp-first tie break. Compare that nominee with RemoveLow and,
only if its discovery advances, CardWinRank by greatest paired development gain,
then lower candidate CPU for the same128 sources, then earlier protocol.
This is exploratory selection across distinct cohorts, not a significance test.
No automatic combination. If nobody meets eligibility, leave final seeds closed.

## Fixed experiment

Freeze512 source pairs610083000..610083511, exactlytwo arms and1,024 full runs.
Use the selected candidate's already reviewed immutable producer for both arms,
unchanged model bytes, and exactly the selected one-factor profile difference.
Keep common diagnostic flags symmetric. Use the corresponding already reviewed
immutable analyzer; source, binary, models, runner, analyzer and all profiles are
hashed in the final manifest, including imported paired_analysis.py, tools/seed_guard.sh, the exact job list and Python/NumPy runtime versions. The only primary contrast is champion minus Fprod.

The observed development cost is approximately14 CPU seconds per run, so the
expected six-worker trial is about40 minutes plus overhead. Use at mostsix
simultaneous one-thread game processes, fixed alternating four-seed shards,
900 seconds per shard and a5,400-second outer cap. Start no later than07:30 local,
leaving packaging time before09:47. If pre-freeze resource measurements materially
contradict feasibility, stop before opening and document the limitation; do not
silently shrink or extend this512-pair design.

## Release and analysis

Before launch, independently verify implementation, scientific design,
information boundary, immutable artifacts and absence of confirmation outputs.
Freeze one champion record with an epoch, final manifest, seed list, analysis
identity, gates and selection evidence. After its independent release review,
write a refuse-overwrite holdout-opened latch binding those hashes and launch the
fixed job list through run_arm.py and tools/seed_guard.sh. The latch must precede
the first game. Existing output paths are a hard refusal, not a reason to replace
or rerun seeds. Save every exit, timeout, missing pair and output hash.

Do not read efficacy results until the entire fixed trial stops. All512 matched
pairs and all runtime contracts must pass. Use paired_analysis.bootstrap_ci with
10,000 replicates and RNG20261008. Superiority requires paired95% lower bound>0
and observed gain>=0.02. Report both discordance directions and descriptive
per-arm Wilson95 intervals. Do not change sample size, threshold, candidate,
configuration or analysis after opening. Invalid or incomplete execution cannot
support a clean superiority claim; preserve it without automatic replacement.

The analyzer's raw verdict is preserved verbatim. CONFIRMED_IMPROVEMENT maps to
the same campaign status. NO_CONFIRMED_IMPROVEMENT maps to PROMISING_UNCONFIRMED
when the observed gain is positive but either the lower-bound criterion or the2pp practical floor is not met. This includes a statistically positive gain below2pp; the failed criterion is stated explicitly. Zero/negative final gain maps
to NO_IMPROVEMENT_FOUND. Execution invalidity maps to EXECUTION_BLOCKED unless a
more limited valid completed result is separately identified. No merge, model
promotion or production-default change follows automatically.
