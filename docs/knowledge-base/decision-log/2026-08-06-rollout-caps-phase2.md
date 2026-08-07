# 2026-08-06 — STS_ROLLOUT_CAPS: Phase 2 context-adaptive rollout caps — FALSIFIED at the paired gate (256 seeds)

Date: 2026-08-06
Session/task: Execute plan T6 (`plan-searchdiag-adaptive-continuation.md`):
measure the flat rollout stack at fair 3k (unmeasured until now), then
implement and gate per-context rollout caps (Phase 2 of the adaptive-budget
program).

## Decisions

1. **Cap design:** per-context caps replace the flat unlimited rollout when
   `STS_ROLLOUT_CAPS=1`: boss encounters, turn 0, and act 2-3 (floors 17..50)
   capped at 8 actions each (defaults); short late-fight states (monsters
   alive <= 1) uncapped so decisive rollouts play to terminal. Leaf
   evaluation stays the heuristic (`evaluateLeafState`) — the combat VNet was
   rejected at the gates (§97). Implemented as `rolloutCapForContext`
   (`src/sim/search/BattleScumSearcher2.cpp`) with the damage-biased weighted
   rollout pick applied whenever a context cap is active (same path the flat
   `g_maxRolloutDepth` used).

2. **Env gate stays opt-in and default-off.** When `STS_ROLLOUT_CAPS` is
   unset the helper returns the flat `g_maxRolloutDepth` (0 = unlimited), so
   default behavior is byte-identical — verified structurally and by the
   searchdiag smoke (default arm: 0 capped rollouts). No built-in default
   change regardless of gate outcome until two independent gates agree.

3. **Before/after protocol:** fair @3k searchdiag, same 6 seeds, before and
   after, using the `avgRolloutLen` / `rolloutDepthCapped` columns as the
   plan specifies; then a 256-seed paired gate (the arbiter) because the arm
   is policy-affecting (§6: every policy-affecting arm gets its own paired
   gate).

## Alternatives considered

- Apply the flat `g_maxRolloutDepth` per context by writing the global from a
  context callback — rejected: mutating shared global state from inside
  `playoutRandom` is racy and invisible; a pure context function returning
  the cap keeps the rollout loop free of context awareness.
- Cap at 6 or 10 instead of 8 — not swept: the 8/8/8/1 defaults sit inside
  the plan's 6-10 range and the gate verdict is far outside noise, so a
  ±2-action resweep cannot plausibly rescue the arm (see Evidence).

## Evidence

- **Baseline (fair @3k, 6 seeds, GCP, `build/sdiag_fair3k_flat.csv`):**
  avgRolloutLen 8.76 overall; MONSTER 7.1 / ELITE 9.0 / BOSS 12.4; per-act
  7.6 / 9.5 / 9.3; rollFrac 0.75; rolloutDepthCapped 0.
- **After (same protocol, `build/sdiag_fair3k_caps.csv`):** avgRolloutLen
  7.15 (−18%); 27% of rollout calls capped (BOSS 38%, act2 33%, act3 38%,
  act1 12%); rollFrac unchanged. The cut lands where the plan intended.
- **256-seed paired gate (GCP, 24 threads):** flat 22.3% / 57 wins / floor
  36.0 / hp 12.6 / cpu 8.64 vs caps 16.4% / 42 wins / floor 35.5 / hp 9.6 /
  cpu 7.97 (−7.8%). Paired delta **−5.9pp, 95% CI −5.9 ± 4.5pp (excludes
  zero)**, flips 13 up / 28 down.

## Status

**Falsified and closed.** The rollout-cap arm is net-negative with CI
excluding zero; the heuristic capped-leaf estimate at depth 8 loses more
decision quality than the saved sims gain. Line stopped, env gate stays
opt-in default-off, no promotion, no baseline-table change. Recorded as
EXPERIMENTS.md §119. Parked phases (plan §5) are unaffected by this gate;
Phase 2 is not revisited without a different leaf-estimation strategy.
