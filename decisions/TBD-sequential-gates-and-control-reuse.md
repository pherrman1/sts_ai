# ADR-TBD: Paired A/B gates stop sequentially (SPRT) and may reuse a recorded control arm

Date: 2026-11-01
Status: accepted

Amends the "Gate protocol" of the [benchmark protocol](../docs/knowledge-base/evaluation/benchmark-protocol.md)
(hard-cap-only promotion) for whole-run and stage-replay campaigns.

## Context

Every change is gated by a paired A/B on common seeds. The paired SD per pair is about 0.44, so 1,024 pairs give
±2.6 pp; each production pair costs about 0.46 core-h. Campaigns always ran to their fixed size, even when the answer was
clear after a fraction of it (§727 lost −15 pp; §724 won +5.9 pp per state). The literature review
([search-and-value-literature.md](../docs/knowledge-base/research/search-and-value-literature.md), ranks 1 and 2)
proposed two cheaper designs, and Philipp asked to make both the standard (2026-11-01 07:25Z: "führe 1 und 2 als
Standard ein. Ersparnis für Rechenzeit darf auch bei 10% liegen").

Evidence ([sequential_gates_20261101](../docs/experiments/evidence/sequential_gates_20261101/RESULT.md), ledger §TBD):

- **Sequential stopping:** replaying the SPRT on seven recorded campaigns (§661, §676, §683, §691, §693, §724, §727)
  changed no verdict (0 of 7; 0% over 200 random seed orders each) and needed 3,776 of 6,224 pairs (39% saved).
  Clear effects stop at 17-63% of the pairs; effects between the hypotheses run to the cap at today's cost.
- **Control reuse:** see Part B of the same evidence (determinism smoke on 32 recorded control games).

## Decision

1. **Sequential gate (standard for new paired campaigns).** `tools/sprt_gate.py`: generalised SPRT with the normal
   approximation (Fishtest), α = β = 0.05, on the per-pair difference of the pre-registered primary metric.
   - Variants: **gainer** H0 δ = 0 vs H1 δ = +2 pp (H1 = PASS, H0 = NOT_SHOWN); **non-regression** H0 δ = −1.5 pp vs
     H1 δ = 0 (H1 = NOT_WORSE, H0 = WORSE) for guards and CPU savings. A pre-registration may set other bounds.
   - Pairs count in the pre-registered order (ascending seed or unit index); a look after every 64 contiguous
     completed pairs; a gap waits for its unit.
   - Hard cap = the campaign's pre-registered size (the fixed design it replaces). No crossing by the cap: read the
     full data with the pre-registered fixed-sample CI, as before.
   - When a boundary is crossed, the author stops the workers (`tools/cloud/worker.sh stop`); finished extra units are
     reported but do not change the verdict.
   - Secondary metrics and CIs are reported on the pairs played; they are descriptive.
2. **Control-arm reuse (allowed, not required).** A campaign may take arm A from a recorded control bank instead of
   playing it, if (a) the bank's configuration (binary, flags, models, seeds) is the candidate's baseline, and (b) a
   **sentinel** passes first: the candidate binary with its flag off replays 32 bank seeds, and every game must be
   identical under `compare.py`'s rule (all state, decision and outcome rows exact; header identical except
   producer SHA and the student_sel path; CTM rows exact). A failed sentinel stops the campaign before arm B runs and
   forces a fresh arm A. A default change makes the bank stale until it is re-recorded. Keep a separate confirmation
   bank so that no seed bank is reused for every decision.

## Consequences

- Clear results cost about 40% less; inconclusive ones cost the same. Small effects still need bigger gates.
- Pre-registrations name the variant, bounds, look size, order and cap; reviewers check the stopping record
  (`sprt_gate.py` output on the pairs file) against them.
- Pairs files (`key,a,b`) become a standard campaign output.
- `selfplay/loop.sh::gate_stats` (the retired self-play gate) is unchanged.
