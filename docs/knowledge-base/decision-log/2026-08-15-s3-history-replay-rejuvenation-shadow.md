# Searcher3 history-replay rejuvenation shadow probe

Date: 2026-08-15
Session/task: Opt-in, shadow-only rejuvenation probe for Searcher3 (branch
`exp/s3-history-replay-rejuvenation-shadow`).

## Decision

Implement an opt-in (`STS_S3_REJUV_SHADOW=1`, off by default) telemetry probe
that, when the persistent filtered posterior loses support at a real-observation
boundary (`filterStats.compatible <= STS_S3_REJUV_TRIGGER`, default 16),
replays the full recorded real observation/action history under freshly sampled
hidden-state hypotheses to test whether compatible hypotheses can be generated
at all. The probe records each committed boundary (semantic action identity +
raw bits + real post-action observation + outcome) into a per-combat history
anchored at battle start, samples `STS_S3_REJUV_PROPOSALS` (default 256) fresh
hypotheses from the anchor observation on a dedicated deterministic RNG, and
replays the full history under each using position-independent semantic action
remap and bare `Action::execute` (exact live transition semantics). A hypothesis
is accepted iff it reproduces every recorded post-action observation and outcome
exactly. Uniqueness, novelty, and milestone counts (4/8/16/32) use the
equality-backed `FullHiddenStateKey` (ordered canonical draw-pile identity +
all six RNG seed0/seed1/counter triples), never a combined hash.

## Rationale

The persistent-filtered-posterior A/B and posterior-lifetime diagnostics
showed collapseFresh rebuilding fresh beliefs at a large fraction of filtered
boundaries (e.g. §persistent T1 rerun: 434/2,867 = 15.14%). Before any
resampling/rejuvenation policy change can be justified, the mechanical question
is whether new full-history-compatible hypotheses exist at all (particle
depletion — in-principle recoverable) or whether the hidden-state model is
inconsistent with the real history (hard failure). The probe answers only that
question. It never mutates the live battle, the searcher, its belief, or any
battle RNG: replay uses copies of the battle-start anchor and a dedicated probe
RNG, and with the probe off the fair-S3 path is bit-identical (proved by the
non-interference test).

## Alternatives considered

- Rejuvenating the live belief with accepted proposals — rejected; that is a
  gameplay/policy change requiring its own preregistered gate, and the probe is
  deliberately shadow-only to keep this change behavior-neutral.
- Snapshotting the pre-filter survivor set for novelty — rejected; that set
  describes hidden state before the committed action, while accepted proposals
  are extracted at the current/post-action boundary. Novelty therefore compares
  against the positive particles already in `s3.belief` after
  `filterRealTransition` when `compatible > 0`; when `compatible == 0` the
  pre-fallback survivor set is empty and no comparator is used.
- Defining uniqueness by a combined 64-bit hash — rejected; uniqueness/novelty/
  milestone accounting must be equality-backed (`FullHiddenStateKey`).
  Draw-order-only and RNG-only telemetry counts may use local hashes.
- Renaming/reworking `applyParticleImpl`'s 11 call sites — rejected; a small
  public `applyHiddenState` wrapper around the existing implementation suffices.

## Evidence

- `include/sim/search/S3RejuvenationProbe.h` / `src/sim/search/S3RejuvenationProbe.cpp`
  — history recording, semantic remap, full-history replay, shadow probe driver,
  CSV telemetry (one row per trigger).
- `include/sim/search/CombatObservation.h` — `FullHiddenCardId` /
  `FullHiddenStateKey` (exact equality + ordering); builders from
  `HiddenBattleState` and `BattleContext`.
- `src/sim/search/BattleScumSearcher3.cpp` — `applyHiddenState` wrapper;
  `resolveCardKeyInHand` extracted from `resolveSemanticCardEdge` (shared by
  probe remap; `resolveSemanticCardEdge` behavior unchanged).
- `src/sim/search/ScumSearchAgent2.cpp::playoutBattleFairSearcher3` — probe
  history + trigger at both boundary sites (forced-action path and main path).
- `apps/test_belief.cpp::testRejuvHistoryReplay` — true hidden state accepts the
  full history exactly (deterministic); contradictory hypotheses are rejected at
  an exact boundary index; a permuted replay hand still remaps to a legal action
  on the recorded card identity. Fixture: `TWO_FUNGI_BEASTS` (aiRng-rolled
  turn-1 moves) — CULTIST is observationally degenerate for the 10-card starter
  deck (scripted moves; every hand/pile multiset is particle-invariant).
- `apps/test_belief.cpp::testRejuvNoninterference` — public
  `ScumSearchAgent2::playoutBattleFair` with Searcher3 on: shadow OFF vs ON
  produce identical committed action bits (`gameActionHistory`), decision
  observation hashes, all-18 RNG field trajectories, positive-particle
  `FullHiddenStateKey` sequences, final state; sim-health counters untouched;
  shadow CSV written (9/9 rows at proposals=4).
- 8-seed mechanical run (seeds 126732–126739, 1,000 sims, 12 threads, run
  through `tools/seed_guard.sh`): 981 trigger rows, 251,136 proposals, 2,013
  full-history-accepted hypotheses (0.80%) in 128 rows; 83/66/37/21 rows
  reached 4/8/16/32 unique accepted hypotheses; acceptance concentrated at
  decision_idx 0–4 (80.4% of accepted rows) and ≈0 after ~8; all accepted
  hypotheses novel vs the surviving posterior; 0 action-illegal, 0 sim-health;
  probe CPU 1.76 ms/trigger. Per-row sanity and milestone-monotonicity gates:
  0 violations. Whole-run 4/8 wins (informational only). Details in
  ledger-06 results section.

## Status and follow-up

- Implemented and mechanically verified (build release, focused tests, 8-seed
  run through `tools/seed_guard.sh`).
- **Open question:** the 2-boundary CULTIST fixture revealed that with the
  10-card starter deck and fully scripted enemy moves, observation histories
  can be particle-invariant (accepted-by-every-hypothesis); the probe's
  accepted/novel counts on real runs must be read with deck-size and
  move-entropy context.
- **Unverified separate concern:** `belief_order_invariance` fails pre-existing
  on the baseline (multiset `operator==` vs position-sensitive
  `Belief::update`); unrelated to this change and not addressed here.
