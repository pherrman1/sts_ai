# Java/native differential correctness

Last verified: 2026-09-28 against the native adapter and a bounded live capture; parity probe section 2026-10-19 against its unit tests.

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
  discard pile natively; Java resets it.
- Perfected Strike counts one Strike fewer after Havoc exhausts a Strike.
- Havoc's random target differs (`lastTargetedMonster`).
- Hexaghost records Inferno twice in Java's move history. **Inference:** no
  behavior reads it.

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
  an upgrade flag sits on another copy. **Inference:** the probe's draw-order
  reconstruction is incomplete once a combat-generated card is in the piles.
- The run stopped on a Headbutt selection with pending actions
  (`silver_selection_pending_actions`), which Silver does not support.

Overnight live play on 2026-10-19 (seeds 111194452-460) found that the live
importer gave the player phantom relics. The combat `Player` has 128 relic
bits, but `importSilverRoot` shifted every relic id, so ids >= 128 set the bit
of id - 64: Thread and Needle became Strike Dummy (+3 on Strikes), Maw Bank
became Wrist Blade (+4 on 0-cost attacks). This affected the live advisor and the
parity probe, not the simulator's own `GameContext` path.
`STS_IMPORTER_HIGH_RELIC_FIX` (default on, `=0` restores) gives those relics no
combat bit; no combat code reads them.

A run on 2026-10-19 (seed 111194463, Act 3) stopped when the bot played
Panache, because the live importer refused it. Java `PanachePower.amount` is
the cards-left countdown and the damage is a private `damage` field, which the
producer did not send. The engine also differed: a new Panache started its
countdown at 0, so it dealt damage on the next card, and the countdown never
went back to 5, so it dealt damage on every later card that turn. The
producer now sends `panacheDamage`, the importer maps it, and
`STS_PANACHE_FIX` (default on, `=0` restores) makes the engine count from 5,
reset after damage, and let a second copy add damage only.

For localizing a divergence against the pinned game bytecode, see the
[STS1 Java reference audit](../behavior/java-reference-audit.md).

Knowledge impact: documents the native replay connection, opt-in comparison
state, and separation between capture/replay plumbing and gameplay parity.
