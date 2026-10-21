# Java/native differential correctness

Last verified: 2026-09-28 against the native adapter and a bounded live capture; parity probe section 2026-10-19 against its unit tests; Mayhem paragraph 2026-10-19 against the pinned bytecode; Magnetism paragraph 2026-10-20 against its unit test and the live verdicts (Java semantics recalled, not re-read from bytecode).

## Purpose

The differential harness is a debug correctness boundary between a fixed-seed
vanilla Ironclad run and sts_lightspeed. It records stable MCP decision
boundaries as versioned JSONL and lets a native adapter compare state,
re-enumerated legal semantic actions, and the selected action without
resynchronizing random streams.

## Current implementation

tools/live_game_driver.py --differential-trace adapts the existing live
driver. The ordinary Silver/OOC provider and deterministic fallback policy are
unchanged. Run-control actions execute without requiring a native decision identity or
post-action canonical state. Their rows are excluded; each stable decision contains
normalized pre/post state, the complete captured legal candidate set, the
canonical selected identity, and the concrete MCP tool call.

Combat identities use the existing Silver fingerprint. OOC identities use the
provider's existing semanticKey; MAP retains its primitive x,y identity.
The trace records the OOC policy in header provenance and each OOC decision;
missing, unknown, or conflicting policy tags fail closed. MCTS retains its
semantic target candidates, while V4 uses its current-screen primitive
identities. Replay applies only the selected source primitive, leaving any
following selector to its own recorded decision. Each OOC decision also records
whether it uses a fresh policy score or the advisor's retained compound target.
Retained selectors enumerate all physical card occurrences; independently
scored MCTS selectors group equivalent copies just as the provider does.
An action without a native-replayable identity is recorded as
UNSUPPORTED_BOUNDARY instead of being guessed.

tools/differential_replay.py consumes a trace and a native JSONL adapter. The
adapter receives one decision row at a time and returns state, legalActions,
after, and optionally rng/postRng. The replay compares the pre-action state,
legal identity set, unique selected-action resolution, and post-action state,
stopping at the first difference. It reports STATE_DIVERGENCE,
RNG_CONSUMPTION_DIVERGENCE, LEGAL_ACTION_SET_DIVERGENCE,
RECORDED_ACTION_NOT_FOUND, RECORDED_ACTION_AMBIGUOUS,
UNSUPPORTED_BOUNDARY, or BOUNDED_PREFIX_EQUIVALENT. Replay requires one header,
one closing summary, consistent trace identities, increasing decision indices,
and a matching summary count and content hash. A trace with no decision records
fails with TRACE_OR_SCHEMA_ERROR (`no_decisions_captured`). An errored or
truncated capture cannot report equivalence; capture exceptions retain an
explicit failed boundary, including failures after a command executes.

Only a successfully bounded capture (`outcome=max_steps`) can return
BOUNDED_PREFIX_EQUIVALENT. It does not claim complete-run parity. Terminal
post-states currently have no qualified shared representation and are recorded
as `UNSUPPORTED_BOUNDARY: terminal_state_unqualified`, instead of comparing raw
MCP output with native canonical state. No full-run equivalent result is emitted.

Hidden RNG is separate from public observations. --capture-hidden-rng records
only an inspector-supplied debugRng object under the differential trace
record. tools/differential_rng.py verifies the installed vanilla
Random.counter, RandomXS128.seed0/seed1, and getState(int) contract. No RNG
values are imported into Silver, OOC observations, policy scoring, or native
execution.

Canonical OOC comparison excludes reward-pity counters, including
importer placeholders, and room fields the public importer does not populate. Details are restricted to the active screen, and sold
shop slots use a common unavailable representation. This is a public-state
projection, not equality of hidden counters or stale simulator storage.

## Verification

Focused checks:

    python3 -m unittest tests.test_differential_trace tests.test_live_game_driver -q
    ctest --test-dir <build-dir> -R differential_trace --output-on-failure

The trace test replays a native self-fixture and covers precise state diffs,
RNG-only diagnostics, missing and ambiguous identities, legal-set mismatch,
schema round-trip, hidden-RNG isolation, and vanilla-JAR preflight.

## Native replay and current boundary

`one_combat differentialreplay` now constructs an Ironclad run from the trace's
numeric seed and ascension, resolves recorded semantic actions uniquely, and
steps the current native simulator. Combat legal actions use native Silver's
root enumeration without running search. OOC source identities share the live
policy's identity contract. A trace must start at the initial Neow
boundary; replay does not reconstruct an arbitrary resumed run.

Set `STS_DIFFERENTIAL_TRACE=1` in the advisor environment to emit canonical
comparison states. It is off by default. Set `STS_DIFFERENTIAL_DEBUG_RNG=1` in
the game's environment when requesting hidden-RNG diagnostics. RNG tuples are
captured on the game thread with the immutable observation and retained when
its asynchronous advisor response arrives; they never enter the public
observation, its hash, or the advisor request.

The focused `native_differential_replay` check exercises native self-replay.
It establishes adapter plumbing, not Java/native equivalence. Live capture
must retain the first precise mismatch or unsupported boundary; do not change
simulator semantics or resynchronize RNG to make the harness pass.

The real Java fixture `tests/fixtures/differential/neow-intro-unsupported.jsonl`
records seed 0 / A0 stopping at the initial Neow Talk page with
`EVENT_PHASE_UNREPRESENTABLE:Neow:1`. Two native replays return the identical
unsupported result. There is one captured boundary and zero compared supported
decisions. This is evidence for precise failure reporting, not Java/native
parity or a complete-run pass. The adjacent receipt records executable hashes.

## Exact one-step combat parity probe

The whole-run replay above stops at its first difference and has compared no
real decision yet. The combat parity probe instead restarts every step from
the game's own state, so one difference does not end the comparison.

- Recording: run the game with `STS_DIFFERENTIAL_DEBUG_RNG=1` and the driver
  with `--parity-trace`. Each advisor row then keeps the raw observation, all
  12 RNG streams and, in the same `debugRng` envelope, `drawPileUuids`: the
  true draw-pile order, bottom to top. The public observation still sorts the
  draw pile, and decisions are unchanged.
- Replay: `combat_parity_probe` imports each Silver combat decision with the
  live importer and reorders the draw, discard and exhaust piles into the true
  order. It then seeds the six combat RNG streams from the game, applies the
  recorded action with `ScumSearchAgent2::takeAction`, and projects the result
  with `wireFromSearchState`. The next recorded observation is imported and
  projected the same way. Fields that round-trip through the importer on both
  sides are comparable. Native bookkeeping that Java never exports is not:
  the importer fills a default on the game side while the engine evolves it.
  These are `loopCount`, `cardsDrawn`, `energyWasted`, `monsterTurnIdx` and
  `curCardQueueItem`, listed in `UNOBSERVABLE_FIELDS` and reported in their
  own section, never in verdicts. Before projecting, both sides drop payloads
  whose flag is off, because the engine clears some states by their bit only
  and a fresh import starts from zero: `statusMap` entries of inactive player
  statuses, `uniquePower0` of a monster with no status from `ANGRY` to
  `TIME_WARP` (Hexaghost keeps its orb counter), and `cardSelect` outside
  `CARD_SELECT`. No Draw's amount is set to 0 (native stores 1, Java -1;
  only its presence is read).
- Action identity: the recorded fingerprint embeds importer card ids, which
  depend on which rows were imported. The probe matches without those ids
  and picks the copy by the Java UUID the driver clicked.
- Comparison: `tools/combat_parity.py run TRACE --probe BIN --out-dir OUT`
  diffs every other field (ignoring only `uniqueId`, `isolatedSearchSeed`,
  `observedGeneration` and `nextUniqueCardId`) plus the six RNG counters and
  seeds. The exhaust pile is compared as a multiset, because Java exhausts
  end-of-turn ethereal cards in an unseeded shuffled order
  ([Java reference audit](../behavior/java-reference-audit.md#ethereal-exhaust-order-at-end-of-turn-parity-not-reproducible)). A change in any of the six Java streams with no native combat
  counterpart (`cardRng`, `eventRng`, `merchantRng`, `monsterRng`,
  `relicRng`, `treasureRng`) during a combat step is a mismatch. It writes `verdicts.jsonl`, `summary.json` and `REPORT.md` with
  mismatched fields, skip reasons and coverage per action, encounter, relic,
  potion, power and card. A step whose next state is out of combat compares
  only the outcome; the HP difference is informational, because post-combat
  heals apply first in Java.
- A mismatch is an engine, importer or exporter defect, or a representation
  gap; triage each one with the Java reference audit before changing the
  simulator. Runic Dome steps, steps without RNG or draw order, selections
  holding cards outside the piles (Exhume, Armaments, Dual Wield), fallback
  actions, rows without `post_screen_kind`, and actions the native root
  cannot resolve are skipped by reason.
- Known limit: at a mid-card selection, `battleContextFromWire` replays the
  interrupted card before the game RNG is applied, so that replay uses the
  isolated search seed. Its effects already happened in Java and are in the
  imported state; only RNG drawn by the replay itself is not the game's.

`tests/test_combat_parity.py` (ctest `combat_parity`) uses a real
observation fixture with synthetic RNG and draw order. It proves the
plumbing (draws follow the given order, RNG comes from the game, skip
reasons) and has a positive control: Defend with a hand-written correct
successor gives MATCH, and one wrong field gives exactly that mismatch. It
does not prove parity.

The first canary (§531; 2026-10-18, one A20 run on the PC, 69 steps, 3 encounters)
compared 34 combat steps: 26 matched, 8 mismatched, 2 were skipped. Seven
mismatches were the export leftovers above. One was an engine difference:
when Uppercut kills its target, the game applies no Weak or Vulnerable to the
dead monster, while the engine did. `STS_DEAD_TARGET_DEBUFF_FIX` (default on,
`=0` restores) now makes a debuff or buff on a dead, half-dead or escaped
monster do nothing, matching the guard read from the bytecode (see the
[Java reference audit](../behavior/java-reference-audit.md#powers-on-dead-targets-mismatch-fixed)).
**Inference:** this matters only where a dead monster's powers survive, such
as a Darkling or Awakened One coming back. The canary
stopped on a driver mapping bug: MCP lists the untargeted Explosive Potion
once per monster. The driver now takes the first of those identical
candidates when Silver gives no target. Parity traces also drop the Silver
search tree (about 85 MB per combat row).

The flag-only clearing behind those leftovers is harmless for game rules,
because re-applying a power overwrites the old amount. It did reach the combat
net features: `powerVal` read the leftover amount, so a spent Vigor or an
ended Flame Barrier kept its old value for the root prior and root table nets.
`STS_ACTIVE_POWER_FEATURES` (default on, `=0` restores) reads 0 for a power
whose flag is off.

The second canary (§536; 2026-10-18, a full A20 run on the PC that reached
floor 16 in Act 1, 9 encounters) compared 135 combat steps: 126 matched and 9
did not. The probe now also ignores a dead monster's powers, because Java
clears them only in `updateDeathAnimation`. `STS_CURL_UP_LETHAL_FIX` (default
on, `=0` restores) stops native Curl Up on a lethal hit. Still open:

- A Discovery pick leaves `cardRandomRng` at counter 184 in Java and 3
  natively.
- A card whose cost was set to 0 for the turn keeps `costForTurn` 0 in the
  discard pile natively; Java resets it. Fixed by `STS_PILE_COST_RESET_FIX`
  (see below).
- Perfected Strike counts one Strike fewer after Havoc exhausts a Strike
  (fixed, §556 below).
- Havoc's random target differs (`lastTargetedMonster`).
- Hexaghost records Inferno twice in Java's move history (resolved below).

The run ended on a live advisor crash, not a parity issue. The live importer
sent every reward exit to the map, but after an act 1 or 2 boss the player
sits on map row 15, which has no node to pick. An OOC rollout from the boss
card reward then reached a map screen with no legal action, and
`ScumSearchAgent2::stepRandom` read past the empty list. Leaving those
rewards now opens the boss chest, as native `afterBattle` does, and
`stepRandom` throws instead of reading out of bounds
(`tests/fixtures/live_act1_boss_card_reward.json`, checked by
`live_ooc_parity`).

Continuing canary 2 past the crash (after #672, #676 and #677) reached floor
29 in Act 2, with 260 matching and 30 mismatching steps in total. It found one
more engine bug: a Blood Potion drunk in combat healed 40% of max HP without
Sacred Bark and 20% with it, the reverse of the game.
`STS_BLOOD_POTION_HEAL_FIX` (default on, `=0` restores) fixes it. Also open:
- Java draws one more `aiRng` value when Blood for Blood kills a Mugger.
- Native sets a `miscBits` flag in the Two Thieves' turn that Java has not.
- After a Discovery, end-of-turn draws differ by one `shuffleRng` draw and
  an upgrade flag sits on another copy. Not Discovery: the old importer
  aliased Matryoshka onto Warped Tongs, which upgrades a random hand card with
  `shuffleRng` at the start of the turn. Re-running these steps with the
  `STS_IMPORTER_HIGH_RELIC_FIX` probe (below) matches; with `=0` it
  reproduces the mismatch.
- The run stopped on a Headbutt selection with pending actions
  (`silver_selection_pending_actions`). Cause (javap of the pinned JAR):
  the Headbutt hit's monster reactions are still queued with `addToBot`
  behind the open grid (Shelled Parasite `ReducePowerAction` Plated Armor;
  Writhing Mass Malleable `GainBlockAction` and Reactive `RollMoveAction`,
  also overnight seed 111194455 floor 38; defensive Guardian Sharp Hide
  thorns, seed 111200382 floor 16; Byrd Flight `ReducePowerAction`, seed
  111200385 floor 21; offensive Guardian crossing Mode Shift, `VFXAction` and
  `ChangeStateAction` "Defensive Mode", seed 111200388 floor 16; louse Curl Up
  `ChangeStateAction` "CLOSED", `GainBlockAction` and `RemoveSpecificPowerAction`,
  seed 111200389 floor 5; Headbutt killing a Darkling to half-dead, its queued
  Regrow `SetMoveAction`, seed 111200400 floor 35; a lethal Headbutt into a Byrd,
  whose Flight `ReducePowerAction` stays queued, seed 111200421 floor 28; Headbutt
  removing Donu's last Plated Armor, seed 111200422 floor 50). The producer now emits them and
  the importer imports them; see live-model-inspector.md.
- The run stopped on a Discovery choice under Hex
  (`silver_card_reward_pending_actions`, seed 111200415 floor 21, Chosen and
  Byrds): `HexPower.onUseCard` queues `MakeTempCardInDrawPileAction(Dazed)`
  behind the choice. The producer now emits it as `SHUFFLE_DAZED` and the
  importer imports it; see live-model-inspector.md.
- Same stop on a Colorless Potion offer (seed 111200417 floor 37, Transient):
  Toy Ornithopter's `HealAction(5)` is queued behind the choice. The offer now
  carries it as a `public_actions` tail.

Overnight live play on 2026-10-19 (seeds 111194452-460) found that the live
importer gave the player phantom relics. The combat `Player` has 128 relic
bits, but `importSilverRoot` shifted every relic id, so ids >= 128 set the bit
of id - 64: Thread and Needle became Strike Dummy (+3 on Strikes), Maw Bank
became Wrist Blade (+4 on 0-cost attacks). This affected the live advisor and the
parity probe, not the simulator's own `GameContext` path.
`STS_IMPORTER_HIGH_RELIC_FIX` (default on, `=0` restores) gives those relics no
combat bit; no combat code reads them.
The same importer also lacked the native leader victory rule: Java has no
power for it (`GremlinLeader.die` makes the other monsters escape;
`Reptomancer`, `TheCollector` and `BronzeAutomaton.die` kill them), so killing
the Gremlin Leader with a minion alive returned `UNDECIDED` natively where the
game returned victory. `STS_IMPORTER_MINION_LEADER_FIX` (default on, `=0`
restores) sets native `MINION_LEADER` on those four monsters at import.
The same night, on seed 111194455, player Thorns killed a Byrd partway
through its Peck; the game skipped its remaining pecks and native landed them
(46 vs 44 HP). `STS_DYING_ATTACKER_FIX` (default on, `=0` restores) cancels a
dead or half-dead monster's queued hits, as Java's `DamageAction` does.

The same overnight runs (problem 10) showed Perfected Strike hitting harder
natively (53 -> 26 HP vs 29 in the game: one more Strike counted). Java
`PerfectedStrike.countCards` counts Strike-tagged cards in hand, draw and
discard only. The live importer recounted `strikeCount` over every imported
card, including the exhaust pile and Stasis cards, while native combat drops a
Strike from the count when it is exhausted or taken by Stasis. So every Strike
exhausted earlier (Havoc, Fiend Fire) added one, and the probe's post-step
recount showed the canary's "game 5 / native 4" after Havoc exhausted a
Strike. Also, a Perfected Strike autoplayed by Havoc or Mayhem is off the draw
pile when its damage is calculated (`PlayTopCardAction` moves it to limbo and
`UnlimboAction` removes it before it is queued), so Java does not count it;
natively it counted itself. `STS_STRIKE_COUNT_FIX` (default on, `=0`
restores) fixes both. Havoc's `lastTargetedMonster` difference is a separate
issue: Java's `PlayTopCardAction` writes no last-target field.

Four smaller monster-side differences from the same overnight list and the
canary 2 carry-overs are fixed behind default-on flags (`=0` restores):
`STS_SLIME_SPLIT_RNG_FIX` (native drew two extra `aiRng` rolls on a large
slime split), `STS_MUGGER_DEATH_RNG_FIX` (the game draws `aiRng` for the
Mugger's death sound), `STS_DEAD_MONSTER_BLOCK_FIX` (Curl Up block queued
before a later hit killed the louse) and `STS_IMPORTER_THIEF_GOLD_FIX` (the
importer never set the native stolen-gold bit, so the probe reported
`miscBits` 0 vs 1 in Two Thieves). After a split the game reports
`lastTargetedMonster` 1 when the targeted slime is gone (the inspector's
default for a target it no longer emits); native keeps 0. Only the Shield
and Spear fight reads that field, so it is left as a known
representation-only difference.

Live parity problem 29 (seed 111200385, Two Thieves) stopped Silver with
`silver_live_action_lowering` after the Looter fled. The inspector's `dead` is
`isDeadOrEscaped()`, which includes `isEscaping`, but its `escaping` field is
`AbstractMonster.escaped`, which Java sets only when the escape animation ends.
In between, the importer kept the 14-HP Looter as a targetable live monster,
while the live target list had already dropped it, so an action aimed at it had
no live target. `STS_IMPORTER_ESCAPING_MONSTER_FIX` (default on, `=0` restores)
imports a `dead` monster with HP left that is not half dead as escaping.
**Inference:** the state cleared after a game restart because the reloaded
combat no longer contains the fled monster.

The same night showed Blessing of the Forge upgrading Ascender's Bane natively
but not in the game (seed 111194457). The engine's upgrade-all-in-hand action
(Blessing of the Forge, Armaments+) upgraded every card, while Apotheosis,
Warped Tongs and the Armaments choice already skipped cards that cannot be
upgraded. `STS_HAND_UPGRADE_ALL_FIX` (default on, `=0` restores) skips them
there too, so a Burn in hand no longer becomes Burn+. **Inference:** the game
skips statuses here for the same reason it skips curses (its `canUpgrade`
rule); only the curse case was observed live.

The same overnight runs showed Mayhem playing the wrong card natively (seed
111194457: Reptomancer and Jaw Worm horde). The game plays the top card after
the start-of-turn draw (`MayhemPower$1` queues `PlayTopCardAction` at the
bottom when it runs, behind `DrawCardAction`); the engine played the pre-draw
top, so Burning Pact's hand selection never opened and a pre-draw Clothesline+
won a fight the game had not ended. `STS_MAYHEM_AFTER_DRAW_FIX` (default on,
`=0` restores) plays it after the draw.

A run on 2026-10-20 (seed 111200429, The Guardian, problem 39) played
Magnetism on turn 1; every later end-turn verdict had a six-card game hand
against a five-card native hand, with cardRandomRng diverging at the same
steps. The engine never implemented `MagnetismPower.atStartOfTurn` (the case
was a commented-out no-op), so it neither added the card nor rolled
cardRandomRng. The game, unless the monsters are basically dead, rolls
`returnTrulyRandomColorlessCardInCombat()` (cardRandomRng, the 34-card
non-healing colorless pool) once per stack immediately and queues
`MakeTempCardInHandAction` at the bottom, ahead of the turn's draw; Master
Reality upgrades the card and a full hand sends it to the discard pile.
`STS_MAGNETISM_FIX` (default on, `=0` restores) implements this
(`tests/magnetism_start_of_turn_test.cpp`).

A run on 2026-10-19 (seed 111194463, Act 3) stopped when the bot played
Panache, because the live importer refused it. Java `PanachePower.amount` is
the cards-left countdown and the damage is a private `damage` field, which the
producer did not send. The engine also differed: a new Panache started its
countdown at 0, so it dealt damage on the next card, and the countdown never
went back to 5, so it dealt damage on every later card that turn. The
producer now sends `panacheDamage`, the importer maps it, and
`STS_PANACHE_FIX` (default on, `=0` restores) makes the engine count from 5,
reset after damage, and let a second copy add damage only.

Live play on 2026-10-19 (seed 111200384, Slime Boss) stopped twice on a
Gambler's Brew hand selection as `silver_selection_pending_actions`. Toy
Ornithopter's `onUsePotion` queues `RelicAboveCreatureAction` and
`HealAction(p, p, 5)` behind the Brew's `GamblingChipAction` (game bytecode,
jar sha256 cfad868a…1673), so the heal is still in `actionManager.actions`
while the selection is open. The engine queues the same heal after the potion
effect in `drinkPotion`. The inspector now carries it as the public pending
action `HEAL_PLAYER` (amount 5, Toy Ornithopter only), and the importer
accepts it under `STS_SELECTION_TOY_HEAL_FIX` (default on, `=0` restores the
refusal). A refused pending queue now also names the blocking state and
action classes in `pendingActionsBlocker`.

The Discovery mismatches from canary 2 were read from the pinned JAR with
`javap` (2026-10-19):

- `DiscoveryAction.update` calls its card generator on every frame before it
  checks its duration. The choice screen pauses the action queue, so the
  first frame draws the three offered cards. After the pick, the action keeps
  ticking until its 0.25 s duration runs out and draws a fresh set of three on
  every frame, which it throws away. At the game's 240 fps limit that is about
  180 extra `cardRandomRng` draws (185, 187 and 194 were seen), and the count
  depends on frame timing. Native draws one set. The probe reports
  `cardRandomRng` on a Discovery pick as unobservable; the next step starts
  from the game's own RNG again. **Inference:** fair play is unaffected,
  because nothing reads that stream between the pick and the next observation.
- The copy itself matches: Java sets its turn cost to 0, and with a full hand
  `ShowCardAndAddToDiscardEffect` adds a stat-equivalent copy (turn cost 0)
  straight to the discard pile. The `costForTurn` mismatch was the played copy:
  `CardGroup.moveToDiscardPile` hands the card to a `Soul`, and when it lands
  `Soul.update` calls `clearPowers`, which calls `resetAttributes` (turn cost
  back to cost). The draw-pile soul paths (`shuffle`, `onToDeck`) and
  `ExhaustCardEffect.update` do the same. `STS_PILE_COST_RESET_FIX` (default
  on, `=0` restores) resets the turn cost on those native pile moves.

Seed 111194465 showed Centennial Puzzle still armed in every imported root
after it fired (all 39 `player.relicBits0` mismatches, bit 8). Vanilla keeps
the relic with `usedUp` false and records the once-per-combat draw in
`usedThisCombat`; native clears the relic bit when it draws, so the engine
semantics agree but the importer never saw the used state. Live Silver roots
therefore expected another free 3-card draw on the next HP loss. The mod now
emits `usedThisCombat` for Centennial Puzzle, and
`STS_IMPORTER_CENTENNIAL_USED_FIX` (default on, `=0` restores) requires it and
gives a used puzzle no combat bit. Traces recorded with an older mod lack the
field and are rejected as `silver_unmapped_relic_state` unless run with `=0`.

A Darkling killed into half-dead kept its Vulnerable and Weak amounts
natively (overnight, 9 diffs). Java `Darkling.damage` clears its powers;
native cleared only the status bits, and a later debuff on the revived
Darkling added to the old amount. `STS_HALF_DEAD_POWER_RESET_FIX` (default on,
`=0` restores) clears the amounts too. The probe ignores two
representation-only differences that no native decision reads:
- `cardSelect.pickCount` outside Exhaust-many and Liquid Memories (Exhume and
  Warcry 1 in Java, 0 natively), and the Exhaust-many count above the
  10-card hand (Elixir 99 in Java, 10 natively).
- The move before last of Hexaghost, Taskmaster and Fat Gremlin. Java appends
  a move on every `setMove` (Hexaghost sets Inferno twice), while native skips
  the roll of a single-move monster.

Seed 111200448 (live problem 59): Armaments+ upgraded a Blood for Blood whose
cost a hit had reduced to 3. The game ended at 2/2 (Java `BloodForBlood.upgrade`
calls `upgradeBaseCost(cost - 1)`), native at 3/3, because the generic upgrade
path reset both costs to the upgraded base. `STS_UPGRADE_COST_DELTA_FIX`
(default on, `=0` restores) follows Java `upgradeBaseCost` for every in-combat
upgrade (Armaments, Apotheosis, ...): Blood for Blood keeps its reduction, and a
cost-changing upgrade keeps the card's `costForTurn - cost` difference.

Seed 111200445 (live problem 54): a Headbutt that moved Pen Nib's counter
from 8 to 9 imported with the Pen Nib status bit already set, while native
still held its `BuffPlayer<PEN_NIB>` behind the Headbutt grid. The importer
turned the counter-9 sentinel into the bit even though the game's PenNibPower
was only queued. `STS_IMPORTER_PEN_NIB_PENDING_FIX` (default on, `=0`
restores) leaves the bit clear while a pending Pen Nib buff is queued and no
Pen Nib power is present.

Seed 111200436 (live problem 42): Fiend Fire grounded a Byrd at 1 HP, and
native kept the Flight status bit at amount 0 (`monsters[0].statusBits` bit
20). Java `ReducePowerAction` removes the power, so the grounded Byrd takes
full damage and gets no Flight back at its next start of turn; native still
halved damage and `applyStartOfTurnPowers` reset Flight to 3/4.
`STS_BYRD_GROUNDED_FLIGHT_FIX` (default on, `=0` restores) removes the status.

For localizing a divergence against the pinned game bytecode, see the
[STS1 Java reference audit](../behavior/java-reference-audit.md).

Knowledge impact: documents the native replay connection, opt-in comparison
state, and separation between capture/replay plumbing and gameplay parity.
