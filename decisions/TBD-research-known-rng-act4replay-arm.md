# ADR-TBD: A research-only known-RNG combat arm in `act4replay`

Date: 2026-10-26
Status: accepted

Partly reverses [ADR-0020](0020-silver-only-combat-remove-searcher2-and-selfplay.md) for one research mode.
[ADR-0002](0002-fair-and-known-rng-are-separate-regimes.md) applies to its rows.

## Context

P300 (destire-mio/sts-ironclad-agent) reports Heart stage values of +10 to +14 pp for adding Feel No Pain, Demon
Form, Impervious, Corruption or Barricade to a real Heart-entry deck. §684 measured these cards near 0 under fair
Silver combat, for example Impervious 0.0 pp (SE 3.9). P300's fights use gamerpuppy's `BattleScumSearcher2`,
which searches copies of the real battle including its RNG streams, so it sees the draw order and every roll. It
also fought at full HP. To test whether clairvoyance explains the gap, the same decks must be fought under fair and
known-RNG combat in one engine. Since ADR-0020 no searcher in `one_combat` reads the battle RNG.

Philipp chose this option on 2026-10-26 (21:51 CET, decision card "Restore known-RNG Searcher2 as a research-only
act4replay arm?").

## Decision

- Add `search::KnownRngSearcher` and `search::playoutBattleKnownRng`
  (`include/sim/search/KnownRngSearcher.h`, `src/sim/search/KnownRngSearcher.cpp`). They implement P300's
  stage-value combat search. That search is gamerpuppy's `BattleScumSearcher2` / `ScumSearchAgent2` non-fair path
  with P300's `sim_patch` search chain applied in order, at destire-mio/sts-ironclad-agent `f8486daf`:
  - **`search_rollout`:**
    - the best value starts at `lowest()`;
    - unvisited edges are searched first;
    - quality is `(value − min) / range`, and 0 while every return is equal;
    - exploration divides by the visit count;
    - rollouts keep END_TURN only one draw in ten while a card is playable.
  - **`search_order`:** half of the rollout card draws pick uniformly among the cards with the best expert play
    ordering.
  - **`search_bounded_loss`:** nodes back up the best sampled return (max backup), and a loss's draw + turn bonus is
    capped at 20.
  - **`search_replanning_limit`:** at most 256 searches per battle. After that, the arm plays out the cached winning
    plan or the latest search's best terminal line.
  - **Agent loop:**
    - a fresh searcher per decision with SIMS simulations, ×3 at the Heart (Boss multiplier 3);
    - up to 15 actions of the best winning line found so far, otherwise up to 5 actions down the most-visited path;
    - the searcher RNG is seeded with `seed + floorNum` (act4replay sets the run seed to the battle seed);
    - the original `evaluateEndState`, with potion value 4.
  - **Turn 500:** rollouts end there, and a battle that reaches turn 500 is left undecided (an invalid row). This is
    later P300 behavior; it never binds at the Heart.
  - **Version caveat:** P300's D4 Heart table has no run manifest pinning its engine, and D4 postdates all four
    patches. P300's later combat4r engine adds performance work and flag-gated changes (75% expert order, focus
    targets, thief value), which are not used here.
  - **What stays deleted:** fair determinization, PUCT/VNet priors, the transposition table and every other removed
    Searcher2 option.
  - **Enumeration:** actions, card selects and potions come from this engine. Card-select edges keep real draw-pile
    indices, which is exact under known RNG.
- Only `act4replay` can select it, with `STS_ACT4REPLAY_COMBAT=known`. Unset or `fair` keeps native Silver, and any
  other value is fatal. The `act4replay` CSV gains a last column, `regime` (`fair` or `known_rng`).
- `run`, `bestbench`, generators, the OOC planner and the live advisor cannot reach it.

## Consequences

- Known-RNG rows are an optimistic, separate series (ADR-0002). They never enter fair baselines or tables.
- Fair `act4replay` rows are unchanged except for the new `regime=fair` column. Stage 0 check: 4 Heart decks × 2
  copies (seeds 111305990–997) gave identical fair rows on main and on this change.
- A completed winning plan must end exactly as simulated, because the search ran on the real RNG. The arm prints
  `[known-rng] plan mismatch` otherwise; the Stage 0 smokes had none.
- **Smoke strength** (8 fights per cell, Heart decks 0–3 of §684 Stage A): 7/8 wins at full HP and 4/8 at natural
  HP. P300 reports 68% at full HP on its own decks.
