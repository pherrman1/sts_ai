# Searcher3 real-boundary belief-filter audit

Date: 2026-08-10

## Finding

The existing `Belief::update` predicate is not a posterior test for a real
combat transition. `drawOrderConsistent` in
`src/sim/search/CombatObservation.cpp` compares an old particle's stored draw
order position-by-position with the newly visible draw pile. It assumes that
the only transition is consuming a prefix of that order. Real transitions can
instead play or discard cards, exhaust cards, create cards, retain cards,
reshuffle, insert status/curse cards, and advance automatic enemy/card action
queues. End-turn transitions also include enemy effects and the next draw.
Random card effects and enemy behavior advance several independent RNG streams.

That comparison therefore overstates particle staleness: a particle can be
correct while its old order no longer has the new pile as a positional prefix.
Conversely, a prefix match does not prove that the particle predicts the full
visible transition.

## Transition semantics

`ScumSearchAgent2::playoutBattleFair` snapshots the live `BattleContext` before
the chosen action, calls `takeAction`, and then observes the resulting context.
`Action::execute` in `src/sim/search/Action.cpp` sets
`InputState::EXECUTING_ACTIONS` and calls `BattleContext::executeActions`.
`executeActions` in `src/combat/BattleContext.cpp` drains queued card/action
effects until player input returns or combat reaches an outcome. This is the
available exact transition oracle for a particle: copy the pre-action visible
state, install its hidden state, execute the same real action, drain the same
queue, and compare only `CombatObservation` fields.

`CombatObservation::operator==` compares player-visible combat facts and pile
contents as multisets. It intentionally does not compare draw order, RNG
seeds/counters, or other hidden internals. That is the appropriate equivalence
for posterior conditioning, subject to the simulator's visible-state model.

## Hidden-state limits

`HiddenBattleState` currently stores one draw-pile order and six RNG seed pairs,
but no per-stream counters or transition history. `applyParticleImpl` installs
the seed pairs and resets counters to zero. Exact particle propagation is thus
possible for the current simulator transition from the copied pre-action
state, but post-transition RNG signatures are only seed-based and do not
represent exact counter positions. A particle whose stored order is not the
same multiset as the pre-action draw pile cannot be propagated exactly; it must
be counted as a propagation failure rather than passed through the old shuffle
fallback.

Hypothetical MCTS paths remain local. The `Belief::update` calls in
`BattleScumSearcher3::step` are gated by `STS_S3_INTERNAL_BELIEF_UPDATE`, which
defaults off and must remain off. Only the real action plus the real resulting
observation may invoke the new boundary filter.

## Consequence

The experiment should filter by exact predicted `CombatObservation` after
propagating each particle through the real action. It should report illegal or
otherwise unpropagatable particles explicitly, preserve a safe documented
fallback on posterior collapse, and leave the existing weak update untouched
when the new opt-in flag is off.

Status: pre-implementation audit; filtering and benchmark results are open.
