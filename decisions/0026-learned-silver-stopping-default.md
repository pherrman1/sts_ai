# ADR-0026: Learned stopping is the default Silver budget for whole-run play

Date: 2026-10-03
Status: accepted

Amends: [ADR-0018](0018-silver-default-combat-backend.md). The whole-run
default was retained-root adaptive Silver (#199); learned stopping replaces it.

## Context

Since #199, a flag-free `run`, `bestbench` or `reprobench` without a sims
argument has used the #199 budget rule:
- a retained root stops at 500 simulations when its top-two visit-share gap is
  at least 0.293;
- every other root searches 10,000.

Learned stopping (`STS_SILVER_LEARNED_STOP=1`, model `gbt-770201c31f7b`,
threshold 0.0323) searches each multi-action root to the checkpoints
250/500/1k/2k/4k/8k/10k. It stops at the first strict visit lock or when the
model's risk that the leader still changes falls below the threshold.

It passed three frozen, independently reviewed tests against #199:
- ledger §370 (v1 model) and §372 (v2 model), fight replay: non-inferior
  signedOutcome with about 20% fewer simulations. A lock-only arm showed that
  the model carries the saving.
- ledger §377, a 1,024-pair live run with Bonferroni-corrected gate
  `PROMOTE_learned`: +0.49 floors, 98.33% CI [+0.08, +0.91]; 80.3% vs 78.3%
  wins; 0.81× time per run.

All three tests ran `bestbench` with explicit environment under
`docs/experiments/evidence/silver_learned_stop/live_env.sh`, which enables the
V4 strategic OOC token net and gate stack. A flag-free run uses the heuristic
OOC stack instead. The combat budget policy is the same in both, but the gain
under the heuristic OOC stack is **Inference**, not measured.

Philipp chose to make it the default on 2026-10-03.

## Decision

For `run`, `bestbench` and `reprobench` called without a sims argument,
`one_combat` resolves an unset Silver budget policy to learned stopping. It
writes `STS_SILVER_LEARNED_STOP=1` and `STS_SILVER_ADAPTIVE=0` to the process
environment. This happens only when none of the following is set:
`STS_SILVER_ADAPTIVE`, `STS_SILVER_ADAPTIVE_RETAINED_ONLY`,
`STS_SILVER_ADAPTIVE_TOP_GAP`, `STS_SILVER_LEARNED_STOP` or
`STS_SILVER_STOP_TRACE`.

- An explicit `STS_SILVER_ADAPTIVE=1` (or a set adaptive knob) still selects
  #199. `STS_SILVER_LEARNED_STOP=0` alone also selects #199.
- An explicit `STS_SILVER_LEARNED_STOP=1` now resolves an unset
  `STS_SILVER_ADAPTIVE` to `0` in every mode.
- An explicit sims argument still selects flat Silver at that budget, as in
  ADR-0018.
- The backend's own default when no executable resolution applies is
  unchanged (#199).
- The research-only boss options (`STS_SILVER_LEARNED_STOP_BOSS_FALLBACK`,
  `_BOSS_MAX`) stay off. Neither beat plain learned stopping in §377.

## Alternatives considered

- **Keep #199 and leave learned stopping opt-in.** Rejected. It played at
  least as well in all three tests and was ahead in §377, at about a fifth
  less time.
- **Learned stopping with boss rooms on #199, or a 30k boss cap.** Rejected.
  In §377 both were about 0.2 floors behind plain learned stopping, and the
  30k cap was slower than #199.
- **Change the backend default instead of the executable resolution.**
  Rejected. The backend requires `STS_SILVER_ADAPTIVE=0` for learned stopping,
  and ADR-0018 already resolves whole-run defaults in `one_combat::main`.

## Consequences

- Flag-free whole-run results from this change on use learned stopping and
  form a new series. The bestbench sidecar records `silverAdaptiveEnabled:
  false` and `silverLearnedStopModel: gbt-770201c31f7b`, and the banner says
  "learned stop".
- `tools/seed_guard.sh` requires a seed count for `bestbench`, so a guarded
  `bestbench` always passes a sims argument and runs flat Silver. The default
  therefore reaches only flag-free `run`, `reprobench` and unguarded
  `bestbench`, as under ADR-0018. Frozen benchmarks of the default must set
  `STS_SILVER_LEARNED_STOP=1 STS_SILVER_ADAPTIVE=0` explicitly.
- Frozen research contracts that pin `STS_SILVER_ADAPTIVE` or pass a sims
  argument are unaffected.
- Retraining the stop model changes the default policy. A new model needs its
  own frozen confirmation before it replaces `gbt-770201c31f7b`.

## Affected files

- `apps/one_combat.cpp`
- `docs/knowledge-base/architecture/combat-search.md`
- `docs/knowledge-base/operations/environment-variables.md`
- `docs/knowledge-base/evaluation/current-research.md`
- `docs/knowledge-base/evaluation/current-baselines.md`

## Evidence

- Ledger-06 §370, §372, §377, and the packets under
  `docs/experiments/evidence/silver_learned_stop/`.
- Smoke on this change, flag-free `one_combat run`:
  - with no environment, the banner shows "learned stop";
  - with `STS_SILVER_ADAPTIVE=1` or `STS_SILVER_LEARNED_STOP=0`, it shows
    "adaptive".
