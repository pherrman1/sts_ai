# STS Model Inspector

Private, read-only Milestone 1 mod for Slay the Spire. It observes stable
card-reward, rest-site, and normal-combat boundaries and sends the detached
summary through the repository's `sts_model_inspector_v1` NDJSON protocol.

The mod never selects cards, plays cards, ends turns, advances RNG, or writes
save data. Advisor I/O, response parsing, and stderr draining run off the game
thread. If the advisor is absent or exits, the panel reports the failure and
the game remains usable.

## Configuration

Copy `config.properties.example` to:

```text
~/.sts-model-inspector.properties
```

Set `advisor` to the absolute path of `one_combat_advisor`. Explicit environment
values take precedence over properties: `STS_MODEL_INSPECTOR_ADVISOR` overrides
`advisor`, `STS_CTM_MODEL` overrides `ctmModel`, and `STS_LIVE_OOC_MODEL`
overrides the future-facing `oocModel` property. `STS_MODEL_INSPECTOR_CONFIG`
selects a properties file instead of `~/.sts-model-inspector.properties`. F8
toggles the panel.

Event/Neow, map, rest, card selector, and shop recommendations attach to the
actual choices instead of a separate upper-left list. Reward cards keep their
score badges, with an extra badge beside Skip. Smith and Living Wall Upgrade
also preview the next card using the separate V4 selector score. Remove and
transform target scoring is not supported by the current V4 provider.
Persistent potion columns below the inventory distinguish use, discard and target;
actions without model coverage are explicitly unscored. All rankings require
the current session/sequence/hash, and the inspector remains read-only.

Set `ctmModel` to the tracked `combat_transition_near_full_except_smoke_v2.native`
artifact. The advisor loads it once at startup and reports an unavailable or
schema-mismatched artifact without affecting the game.

## Latest machine-readable observation

While a stable observation exists, the mod asynchronously publishes the
latest detached observation and matching advisor result to:

```text
~/.cache/sts-model-inspector/latest.json
```

The file is atomically replaced and has protocol `sts_model_inspector_latest_v1`
with `protocolVersion: 1`, top-level `session`, `sequence`,
`observationHash`, `observation`, and `response` fields. `response.ready` is
true only when the advisor response has the same session, sequence, and
observation hash. A ready response stores the validated advisor JSON verbatim
under `response.advisor`, preserving all evaluator fields without a second
Java evaluator serializer; otherwise `response.advisor` is `null` and the
response contains no stale advisor result. The file is removed when the game
no longer has a stable observation and is synchronously removed on normal
shutdown. Export failures are diagnostic-only and do not affect gameplay.

## Build

The repository does not include game or workshop dependencies. Keep those
locally supplied JARs outside Git. From the repository root:

```text
mods/sts-model-inspector/build.sh \
  /path/to/ModTheSpire.jar \
  /path/to/BaseMod.jar \
  /path/to/desktop-1.0.jar
```

The script requires a Java 8 `javac`. It writes only the local mod JAR under
`mods/sts-model-inspector/build/` and fails with a diagnostic if no compiler is
available. The current Steam installation's bundled runtime is Java 8 but does
not include `javac`.

Install the resulting JAR only into the local ModTheSpire `mods` directory.
This project does not publish to Workshop or modify saves.

## Live OOC observation version 1

Actionable noncombat screens publish `boundary: "ooc"` with `ooc.schemaVersion: 1`.
`LiveOocCapture` runs on the game thread and emits detached JSON values only.
It invokes MCPTheSpire's read-only screen/choice converter methods through
reflection so `mcpState` and ordered physical choice occurrences match the
mutator's current enumeration. The inspector never invokes MCP execution
methods. Deliberately unrepresentable states produce an explicit
`unsupportedReason`; fading and non-command-ready frames publish no snapshot.
Unexpected capture failures, including missing read-only APIs, invalid map
edges, missing choice occurrences, and inconsistent action ordering, produce
`captureError`. The importer treats that field as an integrity error before
considering any unsupported reason, so the driver cannot fall back and mutate
the game after malformed capture.

`publicState` contains the character, ascension, act, floor, HP, gold, keys,
ordered deck instances (save ID, upgraded, misc, bottle binding, UUID), ordered
relic counters, five potion slots, visible boss and map DAG, and ten path visit
counts. Searing Blow's native `misc` is its upgrade count, matching native
`Card::getUpgraded`; other cards retain vanilla misc. The two exact vanilla
counters `AbstractRoom.blizzardPotionMod` and
`AbstractDungeon.cardBlizzRandomizer` are **debug integration state, not
fair-play evaluation evidence**. No RNG state, encounter queue, or unrevealed
future reward is captured.

Path counts come from vanilla's persisted run-lifetime `metricData.path_taken`.
Vanilla appends the original map symbol when the player selects a node, before
resolving an event room; these are the same visible node identities counted by
native `PathHistory`. Saves preserve this list as `metric_path_taken`. Missing
or incomplete history produces `PATH_HISTORY_UNAVAILABLE`. Boss nodes outside
the ordinary 15-row map do not increment the native path counters.

Screen-specific `details` contains card/reward groups, fixed shop slots and
prices, selector deck indices, event identity/phase, or boss relic offers.
`liveChoices` binds each exact native candidate descriptor to one current MCP
command. The live driver opens an unopened combat card-reward icon as a
reversible navigation step before asking OOC to score the visible card group.
Direct inspector captures of an unopened icon still produce `CARD_GROUP_NOT_REVEALED`:
its already-generated Java `RewardItem.cards` contents are never serialized.
The driver therefore scores the card choice on the next card-reward
observation. Smith similarly opens the selector before its target is scored. Display strings in `mcpState` and
`mcpLabel` detect stale observations only; lowering uses occurrence indices and
physical card/node identities.

The capture covers map, rewards, card rewards, rest, upgrade selectors, shops,
chests, boss relics, four-offer Neow choices, and qualified initial event phases.
Native policy support may be narrower. Explicit unsupported boundaries include
merchant-entry/proceed-only screens, reward sets without a native supported
card decision, removal/other selectors and confirmation-only phases, Neow
dialogue/two-offer variants, unqualified event phases, and unavailable key actions. Shops whose original physical slot history cannot
be recovered stop with a capture integrity error. Repeated shop buys retain
slot identity; Courier replacements must occupy a known slot.
The native importer independently validates the complete legal action set
before any advisor `OK` response.

The public relic payload preserves `liveCounter` and `usedUp` alongside the
native `data` value. Maw Bank maps its public spent flag to native active=1 /
spent=0, matching `GameContext::obtainRelic` and shop spending. Known native
persistent counters (Happy Flower, Incense Burner, Ink Bottle, Inserter,
Nunchaku, Pen Nib, Sundial, Neow's Lament, Omamori, Girya, and Tiny Chest) copy
exactly. Nonpositive counters retain the identical V4 clamped token value.
Active Lizard Tail, Matryoshka, and N'loth's Hungry Face are explicit
`RELIC_NATIVE_STATE_UNREPRESENTABLE` boundaries because native fresh-run
initialization differs from vanilla. Wing Boots' public charge counter is
copied and its next-row non-edge map moves consume one native charge. Other unqualified positive counters
produce `RELIC_NATIVE_COUNTER_UNQUALIFIED`, preserving their actual values.
Act 4's map shape is explicitly unsupported by the current detached map
contract. The inspector does not invent padding for missing visible nodes.

`response.latencyMicros` records elapsed monotonic time from capture to receipt
of the matching advisor response. Pending responses expose `null`; timing is
outside the observation/hash and remains tied to that snapshot identity.

Run the pure Java projection checks with the same three dependency paths:

```text
mods/sts-model-inspector/test.sh /path/to/ModTheSpire.jar /path/to/BaseMod.jar /path/to/desktop-1.0.jar
```

Vanilla's terminal map edge is visually `(row 14) -> (x 3, row 16)`;
its detached native representation retains the connection as row 14's child
`3`, matching `Map::createPathsIteration`. Only this source-verified terminal
exception is accepted; other nonadjacent edges are capture integrity errors.
Canonical screen and public core values are captured before optional projection
details so capture failures remain tied to the current MCP state.

Snapshot readiness uses the actual `isFadingIn` / `isFadingOut` animation flags
and MCP command readiness. Vanilla's `waitingOnFadeOut` field is excluded:
`nextRoomTransitionStart` latches it true and only dungeon construction resets
it, so using it would suppress snapshots after an ordinary room transition.
