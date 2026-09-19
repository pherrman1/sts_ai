# Silver same-turn Bash/Strike dominance audit

Status: bounded audit; no production pruning, gameplay, equality, hash, or
search behavior changed.

## Provenance

- Reviewed baseline: `46206a59817d1b664566b5f46682110c7bc991bc`
- Tested implementation checkpoint: `10b1a56ee29d87c86f76b0b07b010ac76638abb0`
- Silver upstream revision: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`
- Debug executable: `build/linux-gcc-debug/silver_search_optimization_test`
- Debug executable SHA-256: `6b6e3ddc4663b7c1412ce12f526bbb05e7537691e7db1a3a91301ebdf9507f4d`
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

The unconditional lower-HP/order rule is rejected. A useful restricted
nonterminal dominance rule remains **inconclusive**: the fixtures expose
path-sensitive endpoint differences and a shared-continuation difference, but
they do not establish optimal continuation values or an integrated search
guard. A terminal exact-value comparison is a separately sufficient closed
case, not a useful nonterminal Bash/Strike dominance rule.

## Executable evidence

The focused fixture was added to `apps/silver_search_optimization_test.cpp`.
Its raw output was:

```text
same_turn_plain BashThenStrike_damage=17 StrikeThenBash_damage=14 hp=83/86 vulnerable=2 endpoint_difference=target_hp+curCardQueueItem rng_counter=7 omitted_eval_counters=energyWasted,cardsDrawn
same_turn_reaper shared_continuation lower_hp=1 continuation_player_hp=51 higher_hp=4 continuation_player_hp=54 terminal=PLAYER_VICTORY/PLAYER_VICTORY
same_turn_rejections information_boundary=CARD_SELECT insufficient_energy=remaining_Bash_101_present_but_illegal positive_control=energy3 PASS
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
equal under `equalForSearch`. Without that normalization they do not. The
`curCardQueueItem` inequality is an observed path-sensitive endpoint
difference; by itself it is not proof of a semantic obstruction. The two
sequence endpoints have different immediate parents, so any valid comparison
requires the common-ancestor decision context and the parent-edge/sequence
identity to remain explicit.

The test also constructs two states equal in every other field but with
different `energyWasted` and `cardsDrawn`. They have the same
`equalForSearch` result and the same `hashBattleState`, even though
`evaluateEndState` reads both counters. The Bash/Strike fixture does not change
those counters, but a general dominance guard must not assume equality/hash
covers every evaluation input.

The Reaper shared-continuation fixture uses one ordinary Jaw Worm-shaped target
starting at HP 18, Reaper in the original hand, and 5 energy. Bash → Strike
leaves the target alive at HP 1; Strike → Bash leaves it alive at HP 4. Both
endpoints are nonterminal. Resolving the same Reaper continuation reaches
`PLAYER_VICTORY` from both endpoints, but heals the player to 51 versus 54 HP
and preserves those values in `postBattleHealedHp()`. This is a comparison of
one shared continuation from a common ancestor, not a claim about either
endpoint's optimal continuation value. It rejects the unconditional HP/order
rule but does not settle a useful restricted nonterminal dominance rule.

Two rejection fixtures also pass. WARCRY creates an intervening `CARD_SELECT`
boundary, so the second card is not legal until new information/choice is
resolved. In the energy fixture, Bash ID 101 is asserted present before the
first action; after Strike consumes the only energy, the remaining Bash is
still present but illegal. A copied post-Strike state with sufficient energy
resolves that same Bash successfully. Neither insufficient case is eligible
for a same-turn dominance comparison.

## What is and is not proved

- A: **confirmed in this fixture.** Bash → Strike deals 17 immediate damage
  versus 14 for Strike → Bash.
- B: **not confirmed for an HP-only dominance dimension.** The actual endpoint
  also differs in `curCardQueueItem`; that inequality alone is not a semantic
  obstruction, and fields omitted by search equality/hash can be
  evaluation-relevant in general (`energyWasted`, `cardsDrawn`).
- C: **unconditional rule rejected; restricted rule inconclusive.** The Reaper
  shared continuation makes the higher remaining enemy HP endpoint yield more
  player HP at victory, but this does not evaluate optimal continuation values.

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

The two sequence endpoints have different immediate parents even though they
share the original decision state. The unresolved integration problem is how
to retain any parent-edge/sequence exclusion with common-ancestor context,
without contaminating shared node statistics or making the rule invalid after
reroot. Integration remains unresolved and is not justified by this audit.

## Opportunity screen

Not run. The terminal-only guard was not a useful surviving nonterminal rule,
so the predeclared first-16 `hard64-dev-snapshots.jsonl` screen, 1,000-simulation
searches, stored-graph inspection, and opportunity/coverage accounting were
not authorized by the task's “only if the guard survives” condition. Coverage,
candidate pairs, guard-eligible pairs, rejection counts in that snapshot, and
attributable edge visits are therefore unmeasured. No full-combat replay,
model inference, new seed, parameter sweep, or HOLDOUT was run.

## Checks and decision

Prior audit commands and outcomes:

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

Correction rerun commands:

```text
cmake --build --preset linux-gcc-debug-build -j2 --target silver-search-optimization-test
bash tools/seed_guard.sh ./build/linux-gcc-debug/silver_search_optimization_test
ctest --test-dir build/linux-gcc-debug -R '^silver_search_optimization$' --output-on-failure
```

The correction rerun at implementation checkpoint
`10b1a56ee29d87c86f76b0b07b010ac76638abb0` rebuilt the focused target, passed
the seed guard, and passed focused CTest `1/1` in `0.75 sec`. No broad suite or
gameplay benchmark was run. The focused test is implementation evidence only,
not a universal dominance theorem, optimal-continuation evaluation, or runtime
measurement.

Decision: **unconditional HP/order rule rejected; useful restricted nonterminal
dominance `INCONCLUSIVE`**. The terminal exact-value case remains a closed
sufficient condition, but no integrated nonterminal rule was accepted and no
opportunity screen was authorized.

Knowledge impact: durable experiment evidence only; no Silver search behavior,
runtime policy, model, RNG, schema, or gameplay default changed.
