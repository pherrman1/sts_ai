# Silver same-turn Bash/Strike dominance audit

Status: bounded negative audit; no production pruning, gameplay, equality, hash,
or search behavior changed.

## Provenance

- Reviewed baseline: `46206a59817d1b664566b5f46682110c7bc991bc`
- Tested implementation checkpoint: `7b7af0697d36f05eb459139c9fba270a760d7f77`
- Silver upstream revision: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`
- Debug executable: `build/linux-gcc-debug/silver_search_optimization_test`
- Debug executable SHA-256: `a3765b4d8eecca7c9d9aca4177a71ef326f90eb693e3a34bf938025feb726675`
- Worktree: `/home/philippherrmann/.codex/worktrees/silver-same-turn-dominance-audit/sts_lightspeed`

The canonical checkout remained untouched. The managed worktree was checked and
its `json` and `pybind11` pins were repaired before configuration. The fixture
uses the same original card instances, tracked by unique ID (`Bash=101`,
`Strike=102`, and `Reaper=103`), and resolves the second card by identity after
the first card has fully executed; it never reuses a shifted hand index.

## Hypothesis and guard decision

The tested hypothesis was that Bash → Strike can safely dominate Strike → Bash
when both cards are ordinary, unupgraded, same-target, legal plays in one
`PLAYER_NORMAL` turn. The observed immediate-damage claim is true in the plain
fixture, but it is not a continuation-value proof.

The one conservative sufficient-condition guard left after the audit is a
terminal-only guard: require both fully resolved sequences to reach the same
terminal outcome and compare the complete current Silver terminal objective,
including all reward and HP terms. This is sufficient because no continuation
remains, but it is a terminal exact-value comparison rather than a useful
nonterminal Bash/Strike dominance rule. No nonterminal guard based on lower
enemy HP survived the evidence below.

## Executable evidence

The focused fixture was added to `apps/silver_search_optimization_test.cpp`.
Its raw output was:

```text
same_turn_plain BashThenStrike_damage=17 StrikeThenBash_damage=14 hp=83/86 vulnerable=2 endpoint_difference=target_hp+curCardQueueItem rng_counter=7 omitted_eval_counters=energyWasted,cardsDrawn
same_turn_reaper lower_hp=0 continuation_player_hp=54 higher_hp=3 continuation_player_hp=57
same_turn_rejections information_boundary=CARD_SELECT energy_boundary=1+1>1 PASS
silver_search_optimization PASS
```

The plain state is an ordinary Jaw Worm-shaped first-turn state with target HP
100, no block/status modifiers, and 3 energy. Bash → Strike deals 17 and leaves
target HP 83; Strike → Bash deals 14 and leaves target HP 86. Both paths:

- fully drain the action/card queues and return to `PLAYER_NORMAL`;
- leave the same energy, hand size, discard size, target block/vulnerability,
  player HP, and RNG counter (the sequence consumes no additional RNG); and
- leave different `curCardQueueItem` values containing the last executed card.

After normalizing target HP and that last-card queue item, the endpoints compare
equal under `equalForSearch`. Without that normalization they do not. Thus the
endpoint is not “only target HP” in the actual search state.

The test also constructs two states equal in every other field but with
different `energyWasted` and `cardsDrawn`. They have the same
`equalForSearch` result and the same `hashBattleState`, even though
`evaluateEndState` reads both counters. The Bash/Strike fixture does not change
those counters, but a general dominance guard must not assume equality/hash
covers every evaluation input.

The continuation counterexample uses two Fungi Beast-shaped targets, with the
first at HP 17 and the second at HP 4, plus Reaper in the original hand and 5
energy. After the two-card sequences, the lower-HP endpoint has killed the first
target, while the higher-HP endpoint leaves it at 3 HP. Resolving the same Reaper
continuation reaches victory in both cases, but heals the player to 54 versus
57 HP and preserves those values in `postBattleHealedHp()`. The lower enemy HP
endpoint is therefore not no-worse under the current continuation/reward
objective.

Two rejection fixtures also pass. WARCRY creates an intervening `CARD_SELECT`
boundary, so the second card is not legal until new information/choice is
resolved. With only 1 energy, Strike can be played but the subsequent Bash
cannot legally finish in the same turn. Neither case is eligible for a
same-turn dominance comparison.

## What is and is not proved

- A: **confirmed in this fixture.** Bash → Strike deals 17 immediate damage
  versus 14 for Strike → Bash.
- B: **not confirmed for an HP-only dominance dimension.** The actual endpoint
  also differs in `curCardQueueItem`; fields omitted by search equality/hash can
  be evaluation-relevant in general (`energyWasted`, `cardsDrawn`).
- C: **rejected for the nonterminal rule.** The Reaper continuation makes the
  higher remaining enemy HP endpoint yield more player HP at victory.

This is not a universal impossibility theorem. It establishes only that the
proposed cheap nonterminal Bash/Strike rule needs a closed-world continuation
proof or a growing catalogue of exclusions. Future cards, potions, relics,
enemy thresholds, HP-sensitive effects, death-triggered rewards, and reward
state all remain in scope for C; hand/HP inspection alone is insufficient.

## Design-only pruning location

If a later task revisits a terminal or otherwise formally closed rule, the
smallest plausible insertion point is the same-parent deterministic CARD
expansion in `BattleSearcher::step`, after a copied action has fully resolved
and before its child is admitted as a selectable sibling. The comparison must
be parent-local and path-specific. It must not:

- remove Strike at the root merely because a Bash → Strike sequence dominates
  a sibling sequence; the dominating alternative must remain reachable from the
  same decision context;
- attach an exclusion to a shared transposition node, because that node may be
  reached through a different path with different available alternatives;
- assume the earlier alternative remains available after live action/reroot;
- prune a chance outcome, since chance outcomes are not selectable alternatives;
- redirect an inferior state to a superior state or credit the inferior edge
  with the superior state's sampled returns; or
- infer a particular UCT backup or root-visit selection change from the
  dominance relation alone.

The unresolved bookkeeping problem is how to retain a parent-edge/sequence
exclusion without contaminating shared node statistics or making the rule
invalid after reroot. That is additional search design, not justified by this
audit.

## Opportunity screen

Not run. The terminal-only guard was not a useful surviving nonterminal rule,
so the predeclared first-16 `hard64-dev-snapshots.jsonl` screen, 1,000-simulation
searches, stored-graph inspection, and opportunity/coverage accounting were
not authorized by the task's “only if the guard survives” condition. Coverage,
candidate pairs, guard-eligible pairs, rejection counts in that snapshot, and
attributable edge visits are therefore unmeasured. No full-combat replay,
model inference, new seed, parameter sweep, or HOLDOUT was run.

## Checks and decision

Exact commands:

```text
python3 tools/agent/worktree.py preflight .
python3 tools/agent/worktree.py check .
python3 tools/agent/worktree.py repair .
bash tools/agent/doctor.sh
cmake --preset linux-gcc-debug
cmake --build --preset linux-gcc-debug-build -j2 --target silver-search-optimization-test
bash tools/seed_guard.sh ./build/linux-gcc-debug/silver_search_optimization_test
ctest --test-dir build/linux-gcc-debug -R '^silver_search_optimization$' --output-on-failure
git diff --check
```

The lifecycle preflight/check passed after the two pinned submodules were
repaired; the doctor then passed. The guarded executable passed, and the
focused CTest result was `1/1` in `0.72 sec`. No broad suite or gameplay
benchmark was run. The focused test is implementation evidence only, not a
universal dominance theorem or runtime measurement.

Decision: **`NO_GO_FOR_THIS_RULE`**. A useful nonterminal rule is obstructed by
real endpoint bookkeeping plus future continuation/reward counterexamples. The
only surviving sufficient condition is terminal exact-value comparison, which
does not justify a separate Bash/Strike dominance framework or opportunity
screen.

Knowledge impact: durable experiment evidence only; no Silver search behavior,
runtime policy, model, RNG, schema, or gameplay default changed.
