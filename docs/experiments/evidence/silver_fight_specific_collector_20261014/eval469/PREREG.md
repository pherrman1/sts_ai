# §469 Collector prior online check: pre-registration (written 2026-10-14 12:50Z, before any 99M data)

Philipp 12:27Z tapped "Online check". Baseline (§467): the Collector fine-tune of gen 4
(`combat_policy_mlp_collector467.txt`, sha256 d78f80c9…) is a CANDIDATE offline: fold-4 CE on the old Collector
test roots -0.0125 [-0.0157, -0.0094]. Question: does it play the Collector fight better than gen 4?

## Design
`one_combat silverfocusevalgen` at code 0ce7bc4e (branch claude/project-thread-byhf2a, PR #531), binary 755be7be.
Per seed: the Collector is forced as act-2 boss; the run reaches it with the gen-4 prior at 2k flat exact Silver,
root bonus on (the default settings of the env prior, `env.sh`). Seeds that die before the Collector or never reach
it contribute nothing. At the Collector, 8 copies of the fight (copy 0 the natural battle seed, copies 1-7 a fresh
`gc.seed`, one Silver planner seed per copy); each copy is played by arm A (gen-4 prior, 3ebeab9d) and arm B
(Collector prior, d78f80c9) at 2k flat exact Silver, K = 8, weight 400 as root and tree prior. Both arms of a copy
share battle seed and planner seed, so they differ only in the prior (smoke: A = B gives identical rows).
Seeds 99000000-99000999 (1,000 runs, 250 units of 4). Smokes: author 74070250-277, reviewer 74070300-349.
Author smokes: about 63% of seeds reach the Collector; about 41 core-s per seed, about 11.5 core-h in total.

Sims 2k (not the 10k teacher budget): the prior matters most at low budgets, and 2k matches §460's online check.
**Inference:** a difference at 2k need not carry over to 10k; out of scope here.

## Primary metric and decision rule (analysis code `analyze_469.py`, sha256 c806480e…)
Fight score per copy: 0 on death, else 53 + curHp + 11 * potionCount + 0.25 * gold + 2 * maxHp (§460).
A copy counts only if both arms' rows are valid. Per seed, each arm's score is the mean over its counted copies;
B - A is paired per seed; 95% CI from a bootstrap over seeds (10,000 resamples, RNG seed 0).
- CI above 0: HELPS. Then propose to Philipp how to use fight-specific priors (one net per hard fight, or an
  encounter input in the general net) - a separate decision.
- CI below 0: HURTS.
- otherwise: NOT_SHOWN.
Secondary, descriptive: death rate B - A (same pairing and bootstrap), CPU seconds per fight B - A, reached seeds.

## Integrity
- A unit (4 seeds) whose one_combat runs over 1,800 s is backtraced and killed (rc 137); a unit that exits
  nonzero for any reason has its csv/manifest renamed `*.failed`. All seeds of such a unit are dropped whole,
  never rerun or replaced, and the count is reported. The analysis reads only `*.csv`.
- A container restart reruns that worker's seeds whole from scratch (deterministic).
- Analysis aborts on any duplicate (seed, copy, arm) row.
- Reported: manifests, requested / completed / reached seeds, dropped units and copies.
