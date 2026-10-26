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
  (`include/sim/search/KnownRngSearcher.h`, `src/sim/search/KnownRngSearcher.cpp`). They restore only the non-fair
  path of `BattleScumSearcher2` as of `e45820fd^`:
  - plain UCB with random rollouts to the end of the battle. The rollouts use P300's accepted sampler: while a card is
    playable END_TURN is kept one draw in ten, and half of the card draws pick among the best expert play ordering.
    With plain uniform rollouts the search never found a Heart kill in the Stage 0 smokes;
  - the original `evaluateEndState`, with potion keep value 4;
  - one persistent tree per battle, re-rooted after every action;
  - up to 15 actions of the best line found when it survives, otherwise up to 5 most-visited actions;
  - the 1,000-decision stall guard.

  Fair determinization, PUCT/VNet priors, the transposition table, convergence stops and every other Searcher2
  option stay deleted.
- Only `act4replay` can select it, with `STS_ACT4REPLAY_COMBAT=known`. Unset or `fair` keeps native Silver, and any
  other value is fatal.
  - The `act4replay` CSV gains a last column, `regime` (`fair` or `known_rng`).
  - The known arm uses SIMS × 3 per decision at the Heart (Boss multiplier 3, P300's setting).
  - Its planner RNG is seeded from the same per-copy key as Silver's planner seed.
- `run`, `bestbench`, generators, the OOC planner and the live advisor cannot reach it.

## Consequences

- Known-RNG rows are an optimistic, separate series (ADR-0002). They never enter fair baselines or tables.
- Fair `act4replay` rows are unchanged except for the new `regime=fair` column. Stage 0 check: 4 Heart decks × 2
  copies (seeds 111305990–997) gave identical fair rows on main and on this change.
- A completed winning plan must end exactly as simulated, because the search ran on the real RNG. The arm prints
  `[known-rng] plan mismatch` otherwise; the Stage 0 smokes had none.
- The searcher reuses the current engine's action enumeration, card-select enumeration and potion rules, so engine
  fixes since `e45820fd` apply to it.
