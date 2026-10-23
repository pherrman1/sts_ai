# Same-turn combat infinity oracle v0

Baseline: `a8b801390a2e730c30312522b71a056c3eaca7c7`. This is synthetic correctness evidence for a standalone
research executable, pending independent review. No gameplay or model promotion.

## Result

The bounded fixture decision rule passes: Dropkick certifies actual victory,
the one-variable no-Vulnerable near miss does not certify, a zero-damage draw
loop is a stall, and an Awakened One phase transition rejects a productive
candidate. Time Warp also prevents a repeated control state. A repetition-cap
fixture cannot certify. No false certified positives occurred in these fixtures.
This does not establish prevalence or recall on natural combat roots.

| Fixture | Classification | Nodes | Max depth | CPU ms (Debug) | Replay result |
| --- | --- | ---: | ---: | ---: | --- |
| dropkick | CERTIFIED_KILL | 7 | 6 | 1.191 | VICTORY |
| dropkick_no_vulnerable | NONE | 2 | 1 | 0.050 | — |
| flash_invincible_stall_544_class | STALL_LOOP | 7 | 6 | 0.237 | — |
| awakened_one_phase1 | PRODUCTIVE_LOOP | 7 | 6 | 0.547 | witness_illegal_or_identity_changed |
| time_warp | NONE | 12 | 11 | 0.298 | — |
| repetition_cap | PRODUCTIVE_LOOP | 7 | 6 | 3.390 | repetition_cap |
| branching_budget | NONE | 2000 | 24 | 34.802 | — |
| unsupported_information_set | NONE | 0 | 0 | 0.007 | — |

Eight synthetic states: 7 supported, 4 with repeated control states, final
classifications 1 STALL_LOOP, 2 PRODUCTIVE_LOOP, 1 CERTIFIED_KILL, 4 NONE
(including one explicitly unsupported information-set state). Three candidates
were productive before replay; two were rejected. Mean/max nodes: 255.25 /
2000; mean/max CPU: 5.065 / 34.802 ms. Maximum depth: 24. Timing uses process
CPU (`std::clock`) around detection and replay, excluding JSON output and
fixture setup. One measurement per state, no statistical throughput claim.

The Dropkick witness reaches a recurring state after four plays, then repeats
physical Dropkick #0 → enemy 0, Dropkick #1 → enemy 0. The period deals 14 damage
(7 per play), costs no net energy or HP, and consumes no finite resource. From
that state, victory occurs after 25 replay actions: 12 complete periods and the
first action of period 13. The original fixture has 200 enemy HP and 1 energy.
`fixtures.jsonl` stores reach actions, raw action bits, human descriptions,
existing semantic fingerprints, deltas, replay status and bounds.

The Awakened One uses the same witness and 200 HP in constructed phase 1. After
25 replay actions it is half-dead awaiting rebirth; the next card cannot legally
target it. The result stays PRODUCTIVE_LOOP. The high-HP fixture stops after
128 complete periods (256 replay actions), reason `repetition_cap`, and also
stays PRODUCTIVE_LOOP. Time Warp starts with counter 1 and forces the turn to
end after 11 plays, so no same-turn control state repeats. A valid Cultist intent
lets that forced turn run through normal mechanics.

## Design and conservative equality

Only `apps/combat_infinity_oracle.cpp` contains detector code. Its standalone
CMake target links the existing simulator objects. Production target source
lists, compiler options and all `src/`/`include/` files are unchanged, so the
unused detector has no code path into Silver, AZ, OOC MCTS or gameplay.

A deterministic DFS enumerates legal physical card plays through `Action`,
never End Turn or potions. It visits quiet PLAYER_NORMAL decisions with concrete
ordered draw piles, empty queues, visible intents, no pending end turn, and no
known undefined behavior. It stops on card selections, forced turn changes,
terminal states and safety boundaries. These restrictions are explicit recall
limits, not positive evidence of absence.

The control fingerprint reuses `hashBattleState` for bucketing and checks every
hit with `BattleContext::operator==` on normalized **copies**. Hash collisions
cannot establish equality. Ordered hand, draw, discard and exhaust piles retain
physical IDs, upgrades, special data, base/turn cost, retention and free-play
flags. Player HP/maxHP, energy, block, powers/statuses, gold, potion slots and
capacity, relic bits/counters, turn, enemy identity/liveness/phase/intent,
block/powers/statuses and all remaining comparison fields stay exact.

The audited normalizations, fixed before fixture execution, are:

- Living enemy current HP is the progress coordinate. Dead/half-dead flags and
  monster counts are retained. Replay handles HP thresholds and phase changes.
- At quiet decisions the stale `curCardQueueItem` is history, as documented by
  the existing `equalForSearch` rule. Loop/statistics counters `loopCount`,
  `energyWasted`, `cardsDrawn` are omitted from the key; the real copied replay
  retains them and observes engine safety guards.
- `cardsPlayedThisTurn` saturates at 4 only without Velvet Choker, Normality
  anywhere in the card zones/stasis, or Echo Form. This preserves the engine's
  remaining `<=3` Pocketwatch threshold. Those three consumers keep exact counts.
- Without Kunai, Shuriken and Ornamental Fan, attack count saturates at 1,
  preserving Art of War's zero/nonzero test. With those relics it stays exact.
  Skill count stays exact with Letter Opener and is otherwise bookkeeping.
  Discard count and all other counters remain exact.
- Only for exactly two physical Dropkick/Flash of Steel cards, no player powers,
  no exhausted cards, and relics limited to Burning Blood/Sundial, shuffle RNG
  is omitted from lookup. The played card is absent during its one-card draw,
  so reshuffles contain at most one card and cannot vary order. All other RNG
  stays exact. A third-card fixture disables this quotient and tests both hard
  search caps. Sundial's counter and energy remain exact; no Sundial positive
  coverage is claimed.

These normalization consumers are audited against this baseline. New engine
consumers require revisiting the audit. No fingerprint was weakened to repair a
failing fixture: development repairs corrected API calls, the fixture's
Vulnerable application and its initially missing monster intent.

A productive candidate saves its original starting BattleContext on the path
and replays its exact witness on a copy with the real RNG, normal legality and
mechanics. It validates semantic identity before every action and full control
state at every completed period. Only actual PLAYER_VICTORY, with positive
player HP, no Smoke Bomb escape and unchanged player turn, certifies a kill.
There is no damage extrapolation. The existing observer-isolation pattern from
`proveSilverUselessBlock` prevents copied actions from touching an observer and
restores `g_debug_bc` afterwards. Fixtures also verify input-state immutability,
key sensitivity, conditional counter preservation and existing binary snapshot
round-trip identity.

## Bounds

Search depth and witness length: 24 actions each. Nodes: 2,000. Candidate cycles:
16. Per candidate: 128 periods and 1,024 replay actions. Across all candidates:
4,096 replay actions. The simulator's existing internal action safety bound
still applies; this utility does not add an interrupt inside one engine action.
The caps are compile-time constants, with explicit hit flags for search bounds.
DFS reports a bounded witness, not shortest distance or exhaustive reachability.

## Existing machinery and roots

Issue [#544](https://github.com/pherrman1/sts_ai/issues/544) is closed. Current
code bounds every Silver playout at 1,000 actions, caps zero-cost rollout
priority, and uses a descent-depth backstop. The fixes are present via the
merged #579/#625 line; both focused #544 regressions pass. Its coarse live
no-progress fingerprint is unsuitable for reusable-cycle equality because it
omits card zones and counters. Reuse here is the exact state comparison/hash,
Action legality/execution, semantic fingerprints, native wire importer and
observer isolation; no second state representation or production guard was added.

The historical `w03-hang-91000228.txt` contains stack samples and progress rows,
not the stalled BattleContext or card combination. The synthetic stall reuses
the two-Flash/zero-Invincible class of `testSilverRolloutLimit`; it is not an
exact reconstruction of the historical seed. No historical cohort was rerun.

The first attempted archive (`silver_prior_root_replay_20260923/prepared/roots.jsonl`)
has hidden-intent version-2 wires, which the current importer correctly refuses.
No migration or invented fields were added. The first eight rows from
`silver_quiescent_queue_item_20260922/native8-first-captures.jsonl.gz` reconstruct
successfully via the existing version-compatible wire importer. All eight have
information-set draw piles and are explicitly unsupported by this concrete v0
oracle: zero search nodes and no cycle verdict. They are reconstructed public
search roots, not recovered original private RNG trajectories. The root results
and source/selection hashes are preserved. No new capture infrastructure exists.

The existing `BattleContextBinary` snapshot API also round-trips the positive
concrete fixture exactly. Thus existing formats can carry roots; the available
sample does not provide concrete roots suitable for this oracle's cycle search.

## Reproduction and raw checks

```sh
cmake --preset linux-gcc-debug-ccache
cmake --build --preset linux-gcc-debug-ccache-build --target combat-infinity-oracle unit-test -j4
bash tools/seed_guard.sh build/linux-gcc-debug-ccache/combat_infinity_oracle --fixtures
python3 - <<'PYROOT'
import gzip
from pathlib import Path
src = 'docs/experiments/evidence/silver_quiescent_queue_item_20260922/native8-first-captures.jsonl.gz'
with gzip.open(src, 'rt') as f:
    rows = [next(f) for _ in range(8)]
Path('/tmp/infinity-native8-roots.jsonl').write_text(''.join(rows))
PYROOT
bash tools/seed_guard.sh build/linux-gcc-debug-ccache/combat_infinity_oracle --roots /tmp/infinity-native8-roots.jsonl
ctest --preset linux-gcc-ccache-test -R '^(combat_infinity_oracle|silver_rollout_limit|silver_rollout_zero_cost_loop)$' --output-on-failure
```

Final build exit 0; all three focused CTests pass (raw `build.log`, `ctest.log`).
The oracle test carries the `core` label so the existing Linux GCC CI selection
includes it. Worktree dependency check, staged diff whitespace check, and
`python3 tools/repo_health.py --baseline a8b801390a2e730c30312522b71a056c3eaca7c7 --json`
pass (repository health reports no warnings).
`provenance.json` binds source/binary and source-root hashes to this evidence.
No large cohorts, full-run quality experiment, Release timing campaign, model
training, AZ annotations, OOC integration or production binary comparison was
run. Structural isolation establishes unchanged production compilation inputs;
this is not a gameplay-quality qualification. Authoritative Linux GCC CI and
independent review remain separate requirements for merge.

## Decision and next research boundary

Successful bounded synthetic feasibility, pending independent review. The
smallest demonstrated result is recognizing a repeatable damaging card loop,
verifying a real same-turn kill, and rejecting a boss phase that defeats HP
extrapolation. Recall on ordinary larger decks, information sets, stochastic
cycles and card-selection continuations is unmeasured or unsupported.

Knowledge impact: research capability, its conservative equivalence contract,
fixture evidence and limitations are recorded in the combat-search KB, current
research page and §TBD ledger entry. No default changed.

The proposed next step remains **data collection only**: sparse existing AZ
roots with suitable concrete state, oracle labels and witnesses, then an encoder
signal study. No reward, model head, policy change or OOC sibling study is
implemented here.
