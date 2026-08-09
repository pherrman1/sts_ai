# 2026-08-08 — Infinite-combo research investigation and phased plan designed

Date: 2026-08-08
Session/task: User question — "how could we guide our models toward
discovering and executing infinite combos in STS?"

## Decision

A 5-investigator, 1-architect session produced
`docs/knowledge-base/plan-infinite-combos-2026-08-08.md` — a concrete
4-phase plan as a future research direction. No code changes made. The plan
is not scheduled for implementation.

## Key findings logged

1. **The simulator loop guard is the decisive blocker:**
   `BattleContext::executeActions()` (BattleContext.cpp:748-768) unconditionally
   sets `PLAYER_LOSS` at `loopCount > 1,000,000 || turn > 500`. A genuine
   winning infinite (Dropkick vs. ~200 HP ≈ 40 plays) is scored as a loss.
   The reward surface never contains "this loop wins."

2. **All infinite mechanics are already simulatable:** Dropkick energy/draw
   refund on Vulnerable (Actions.cpp:1035), Sundial 3-shuffle energy
   (BattleContext.cpp:2827-2843), Corruption free+exhaust skills, on-exhaust
   triggers, hand caps, Choker/Normality caps. Nothing detects "infinite
   potential."

3. **No ecosystem precedent for runtime infinite detection:** Surveyed
   scumthespire, bottled_ai, sts_lean, Slay-I, multiple RL projects, and
   the broader STS AI literature. No production-grade runtime detector exists.
   `sts_lean` has formal cycle-closure detection (anchored state return with
   accumulated damage) — the closest transferable concept.

4. **The PUCT-prior channel is the best bet:** Every rollout-policy
   intervention gated in the last week lost (§119, §124c, §133, §135b).
   PUCT-prior multiplication (boosting combo-card priors during tree descent)
   targets a different channel with no historical falsification.

5. **Strategic labels lack combo signal:** Tier-B one-ply labels don't
   distinguish tempo from build-around picks. The §105 one-ply-label ceiling
   is the binding constraint, not architecture. Phase 4 is explicitly
   contingent on Phase 3 success.

## Rationale

- The plan is phased and gated — each phase verifiable before proceeding,
  consistent with the historical pattern that gate failures should stop
  lines cleanly.
- Phase 1 (simulator fixes) is correctness work, not a policy bet.
- Phase 2 (mechanical detector) is narrow (Dropkick only) to minimize
  scope; detector infrastructure accepts additional archetypes later.
- Phase 3a (PUCT-prior boost) avoids the historically-failing
  rollout-modification channel. Phase 3b (cap lift) is secondary and
  independently toggleable.
- All new env flags are opt-in, default-off, byte-identical when unset.
- Pre-registered verdicts prevent p-hacking.
- Hand-authored combo detector is consistent with AGENTS.md: it's a
  search-steering mechanism, not a hand-authored card tier or
  deck-bloat penalty as a learning objective.

## Alternatives considered

- **Jump straight to learned combo detection:** rejected — there are no
  labelled infinite-execution examples to train on; a hand-authored
  detector bootstraps the data. The §105 lesson says label ranking is
  the ceiling; with no labels at all there is no floor.
- **Modify rollout action selection:** rejected — every rollout-policy
  intervention gated in the last week lost. The PUCT-prior channel is
  the theoretically distinct alternative.
- **Start with Sundial/Corruption exhaust engines:** rejected — Dropkick
  is simpler (fewer cards, smaller deck, no shuffle-dependent energy).
  The detector infrastructure accepts additional archetypes.
- **Full benchmark instead of phased gates:** rejected — a 256-seed
  paired gate on an untested combo steering mechanism is wasteful.
  Phased unit tests → 8-seed smokes → 32-seed exploratory gate controls
  cost.

## Evidence

- `src/combat/BattleContext.cpp:748-768` — loop guard
- `src/combat/Actions.cpp:1035-1046` — DropkickAction
- `src/combat/BattleContext.cpp:2827-2843` — Sundial onShuffle
- `src/sim/search/BattleScumSearcher3.cpp:784,799` — 200-step rollout cap
- `src/sim/search/ExpertKnowledge.cpp` — Dropkick obtain=2, Sundial absent
- `include/combat/Player.h:71,79` — sundialCounter, cardsPlayedThisTurn
- `src/sim/search/CombatObservation.cpp:52-57` — visibleHash includes counters
- EXPERIMENTS.md: §12/§13 (causal/synergy), §14 (turtle equilibrium),
  §109/§110/§116/§118 (TERM_WIN + counter sensitivity), §119/§124c/§133/
  §135b (falsified rollout interventions), §105 (one-ply label ceiling)
- External: `github.com/collinzrj/sts_lean` (formal combo semantics),
  `github.com/boardengineer/scumthespire`, `github.com/xaved88/bottled_ai`

## Status

Investigation complete; plan documented as future research direction.
No implementation scheduled.
