# ADR-0036: Silver charges a Smoke Bomb escape for the forfeited rewards by default

Date: 2026-10-14
Status: accepted

## Context

Silver's terminal score (`SilverSearcher::evaluateEndState`) scores a Smoke Bomb escape exactly like a win, although
the escape forfeits the fight's card reward, gold, potion chance and, in an elite, the relic. A seeded unit fixture
(`test silver_escape_penalty`) shows Silver fleeing Cultist and Jaw Worm at full HP. `SilverEvalWeights::escapePenalty`
and `eliteEscapePenalty` (#370) subtract a penalty, capped at half the HP left when escaping, and were 0 by default.
Before PR #540, `one_combat` rejected `STS_SILVER_ESCAPE_PENALTY` at startup, so no `one_combat` run used it.

Evidence: §473, whole runs on the §422 `off` stack (exact-10k Silver, V4 OOC policy, OOC MCTS off) with the ADR-0034
defaults, `12,35` vs `0,0`, 500 fresh paired seeds per cohort. A0: 414 vs 414 wins, Δwin 0.0 pp [−1.0, +1.0],
NOT_SHOWN. A20: Δfloor +0.024 [−0.168, +0.234], NOT_SHOWN. Only 46 (A0) and 21 (A20) pairs differ at all. No CPU
difference. The values 12 (normal) and 35 (elite) were fixed before the run from Silver's own weights, not fitted.

The flag audit (`/mnt/project-files/flag-audit/AUDIT-2026-10-14.md`, item 5) listed the escape-as-win score as a
modelling error. On 2026-10-14 (21:01Z, thread "Flag audit"), asked whether to turn `12,35` on by default, Philipp
answered: "yes keep it on and merge 545".

## Decision

- Native Silver (`NativeSilverBackend`) uses an escape penalty of 12 in normal fights and 35 in elite-trigger fights
  when `STS_SILVER_ESCAPE_PENALTY` is unset or empty. `0,0` restores the legacy escape-as-win score; any other
  `<normal>,<elite>` value overrides the default; malformed or negative values stay fatal.
- `SilverEvalWeights` struct defaults stay 0, so code that builds its own `SilverSearcher` (unit tests, the wire
  replay tools) is unchanged.

## Consequences

- Native Silver runs that hold a Smoke Bomb can play differently from before. Reproducing earlier results needs
  `STS_SILVER_ESCAPE_PENALTY=0,0`; comparisons against controls from an older binary must set it in the new arm or
  rerun the controls. The `base` arm of §473 used `0,0`.
- Generators whose fights run through `NativeSilverBackend` label with the penalty unless run with `0,0`
  (**Inference** from the code path; no generator was rerun). Teacher manifests do not record it, so replaying a frozen teacher from before
  this ADR needs `0,0`, which the loader cannot enforce.
- §473 ran before the ADR-0035 situational leaf terms existed; the combination was not tested.
- **Unverified:** a playing-strength gain. §473 was NOT_SHOWN in both cohorts; the default follows Philipp's
  decision, not a passed gate.

## Evidence

Ledger-06 §473 (`docs/experiments/ledger-06.md`); evidence `docs/experiments/evidence/silver_escape_penalty_473_20261014/`;
`tools/analyze_silver_escape_473.py`; `test silver_escape_penalty`; `architecture/combat-search.md`.
