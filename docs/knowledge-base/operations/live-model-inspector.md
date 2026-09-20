# Live model inspector

Last verified: 2026-09-20. This page describes the private integration
boundary currently present in the repository; it is not a claim that every
game boundary has a qualified live evaluator.

## Current boundary

`one_combat_advisor` is a small, read-only newline-delimited JSON process.
Its stdout contains protocol responses only; malformed input and failures are
returned as structured errors. It validates the protocol name, request kind,
session, monotonic observation sequence, observation hash, and the required
observation boundary. It never receives RNG state or controls the simulator.

Combat observations now have two separate fail-closed evaluator paths. The
existing CTM evaluator uses the public combat-entry importer when its model is
available. The `silver_player_decision_v2` evaluator imports an Ironclad
decision-0 or decision-1 Silver root, verifies converted-state parity and legal
actions, and runs the fixed 1,000-simulation Silver decision configuration.
One advisor-owned Silver session is retained for the active protocol session
and `combatEntryHash`; a matching observed successor can therefore report an
exact reroot with inherited visits. If the human plays a different physical
copy of the same ordinary card, the immediate retained successor is narrowly
rebased to that copy and also preserves inherited visits. Matching considers
every explored action listed at the retained root, not only Silver's selected
recommendation, so choosing another supported listed action also inherits its
branch visits. An observation with no retained successor safely reports a
fresh `candidate_missing` fallback.
It returns the selected action, root action summaries containing
edge visits, `visitShare`, and selection Q only when that edge has a valid Q
value, plus the decision ordinal and reroot diagnostics.
Unsupported encounter, relic, information, or schema states remain explicit
`UNSUPPORTED` results; this is a diagnostic ranking display, not a gameplay
controller or a qualification of Silver policy quality. `STALE` responses
reject a second observation with an equal or older sequence in the same
session. A new process starts a new session state.

The Java frontend is under `mods/sts-model-inspector/`. It uses BaseMod
post-update/render subscribers and captures detached Ironclad-compatible
summary fields for card rewards, rest sites, and ordinary player turns. The
combat producer now emits protocol-v4 Silver roots with physical card UUIDs,
upgraded/misc/cost/retain/free-play fields, battle-lifetime stable monster
slots, dead/half-dead/escaping state, relics, potion slots, the combat entry
identity, and a centralized native mapping
boundary for runtime IDs. Monster move-history bytes are emitted in Java's
oldest-to-newest order and translated by the native importer through the
per-monster mapping; they are never copied as native enum values. Ordinary
draw order is sorted before emission; the actual runtime order is retained
when Frozen Eye is present. Under Runic Dome, the observer omits `nextMove`,
`moveHistory`, `intent`, and `intentDamage`; the root remains rejected because
the public producer does not expose enough pre-roll state for a fair import.
Sensitive player and monster powers carry the runtime `justApplied` bit when
the bounded reflection helper can read it and are rejected when it cannot.
Special bookkeeping for Combust, Echo Form, Panache, Deva Form, Orange
Pellets, used-up relics, and Necronomicon is serialized when its runtime field
is accessible; otherwise the importer rejects that state. Monster `miscInfo`
is similarly serialized from known runtime trackers or omitted so the importer
fails closed. Bronze Orb Stasis uses the runtime `StasisPower.card` object to
preserve the exact physical card UUID and state, rejecting only the active-
Stasis snapshot when that field is unavailable.
The observer's post-`AbstractPlayer.damage()` patch records finalized damage
once per public damage call, preserving multi-hit event counts and the final
individual unblocked hit. The v4 importer rejects observations unless the
producer asserts this exact tracking; the old per-turn combat-damage total is
not an accepted approximation. The resolved `CardQueueItem` is captured by a
prefix on `AbstractPlayer.useCard(...)`, after vanilla resolves random
targeting and before `GameActionManager` removes the queue entry; post-update
observation is too late to retain that public item. Boolean monster powers are
presence states at the importer boundary, so a negative or sentinel Java amount
still sets the status bit before numeric amount validation. The stable slot
registry keeps ordinary Large Slime split children at native slots 0/1; the
separate Slime Boss layout uses 0/2. Move bytes are likewise fail-closed, with all
simulator-supported vanilla class constants independently qualified against the
installed `desktop-1.0.jar`. The native construction, public-render, import,
exact search-state parity, and one-simulation Silver-decision sweep covers all
63 reachable `MonsterEncounter` values; the focused test additionally covers
producer-shaped dynamic transitions for Large Slime split, Reptomancer summon,
Darkling Regrow, Bronze Orb Stasis, and Awakened One stage 2. The only manifest
exclusion is the `INVALID` sentinel.
The combat boundary still requires the installed runtime's waiting-for-user
phase, no current action, empty action/card/monster queues, and an unended turn.
The combat fingerprint includes the payload, so successive decisions are not
collapsed into one observation. A battle-start hook can precede encounter
population, so combat-entry and Silver-root identity are captured lazily at the
first actionable decision. A stable-boundary loss clears the displayed
observation and fences late responses from the prior decision. Advisor writes
use one bounded latest-observation slot; intermediate captures are replaceable
rather than queued without limit. It launches the advisor with a direct
`ProcessBuilder` call. The F8 panel remains diagnostic and read-only. Workshop
and game/dependency JARs remain outside Git. The native v4 importer is
fail-closed for unknown mappings, resolving snapshots, unsupported selection
tasks or option capacities, and native mechanics absent from the pinned
simulator. Its maintained capability census is
`docs/knowledge-base/behavior/live-silver-capability-census.md`. A single
isolated search seed derived from `combatEntryHash` is retained across an
active protocol session and combat; the UUID registry is reset when either
identity changes.

## Direct live-game driver

### Start and discover the live control boundary

The canonical local live-test setup is provided by
`tools/live_game_start.sh`. It validates the installed artifacts and advisor
configuration, reuses an already-running modded game, otherwise starts
ModTheSpire in its own background session, waits for MCP port `8080`, and
prints the driver command. Use:

```bash
tools/live_game_start.sh --probe
```

`--probe` performs a read-only driver dry-run after the game reaches a
command-ready screen. Use `--check` to validate without starting anything and
`--foreground` when the Codex terminal should retain the ModTheSpire process
directly. `--allow-missing-advisor` is only for MCP-only control; normal Silver
testing should keep the advisor check enabled. Background launch output is
written to `~/.cache/sts-live-driver/modthespire.log`. The installed artifacts
are:

```text
game directory: /home/philippherrmann/.local/share/Steam/steamapps/common/SlayTheSpire
ModTheSpire:   /home/philippherrmann/.local/share/Steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar
MCPTheSpire:   <game directory>/mods/MCPTheSpire.jar
inspector:     <game directory>/mods/sts-model-inspector.jar
```

Start the modded game with the MCP and inspector mods enabled:

```bash
# Equivalent manual launch when the helper is unavailable.
cd /home/philippherrmann/.local/share/Steam/steamapps/common/SlayTheSpire
/usr/bin/java -jar \
  /home/philippherrmann/.local/share/Steam/steamapps/workshop/content/646570/1605060445/ModTheSpire.jar \
  --skip-launcher --mods basemod,MCPTheSpire,stsmodelinspector
```

MCPTheSpire starts a Streamable HTTP server at
`http://127.0.0.1:8080/mcp`. It is the live game's control boundary; use its
MCP tools rather than GUI automation. The driver discovers the available
surface at startup and requires `get_screen_state`,
`get_available_commands`, and at least one supported action tool. A quick
endpoint check is:

```bash
uv run --extra live-driver python tools/live_game_driver.py \
  --dry-run --max-steps 1
```

The asynchronous inspector snapshot is written to
`~/.cache/sts-model-inspector/latest.json`. Before using an advisor response,
verify that `response.ready` is true and that `response.session`,
`response.sequence`, and `response.observationHash` match the observation (and
then correlate that observation with `get_screen_state`/`get_game_state`).
The endpoint and snapshot paths can be overridden with `STS_MCP_URL` and
`STS_INSPECTOR_PATH` when an isolated game instance is required.

The inspector launches the advisor configured in
`~/.sts-model-inspector.properties`; keep both paths aligned with the checkout
being tested. For this repository the relevant entries are:

```properties
advisor=<repository root>/build/linux-gcc-debug/one_combat_advisor
ctmModel=<repository root>/selfplay/models/combat_transition_near_full_except_smoke_v2.native
```

If `latest.json` remains `WAITING` after a combat observation, check these
paths first and restart the game after changing them. A ready response can
still be `UNSUPPORTED` for an encounter or state outside the maintained live
capability boundary; that is an advisor result, not an MCP connectivity
failure.

`tools/live_game_driver.py` is the repository-local integration/debug harness
for advancing a currently running game without a Codex or Luna turn between
actions. It connects directly to MCPTheSpire over Streamable HTTP, reads the
current screen and advertised commands, and materializes concrete MCP calls
before selecting through Silver or its deterministic fallback policy. The
optional dependencies are isolated in the `live-driver` extra:

```text
uv run --extra live-driver python tools/live_game_driver.py
```

Combat reads the matching `~/.cache/sts-model-inspector/latest.json` response
and uses Silver only when the snapshot is ready, identity-matched, and
correlated with the MCP-visible state. A Silver `OK` response must include a
structured `selectedLiveAction` lowered from the imported physical identity
and map to exactly one current candidate; zero or multiple matches stop the
driver. Only an explicit Silver `UNSUPPORTED` result may use the deterministic
fallback policy, and `--strict-silver` turns that boundary into a stop.
Non-combat screens use deterministic priorities over the generated legal
candidates, so no policy can invent an MCP tool name or arguments. The driver
waits for `ready_for_command` before selecting and after execution, while
readiness-only changes are ignored for state identity.

Inspector correlation uses the full `get_game_state` monster records when
available because the lightweight screen uses names and filters dead slots.
Dead or escaped inspector slots are excluded before comparing the remaining
live monsters. Silver target slots are compacted through that same ordered
public monster observation before becoming MCP's 1-based living-monster index;
dead or missing targets fail closed. Potion candidates are emitted only when
MCP explicitly advertises the corresponding `can_use` or `can_discard`
capability; absent sparse fields mean unavailable. The post-action identity
includes the full game-state payload when that read tool is available, so
successful potion effects that do not change the lightweight screen still
advance correctly. Silver card-selection actions remain explicitly
unsupported until their mapping to MCPTheSpire's choice surface is qualified;
they therefore use the deterministic fallback boundary.

The default MCP endpoint can be overridden with `STS_MCP_URL` or `--mcp-url`.
Each decision is written as redacted JSONL under
`~/.cache/sts-live-driver/` (override with `--trace`). `--dry-run` performs the
read, candidate, and decision path without a mutating MCP call, while
`--max-steps N` bounds a smoke test. The driver intentionally stops on
unavailable MCP, malformed or stale inspector data, unsupported candidate
enumeration, absent or ambiguous structured Silver lowering, readiness or
transition timeout, and unexpected advisor errors.

Live current energy comes from `EnergyPanel.totalCount`; the player's
`EnergyManager.energy` field is the per-turn recharge amount and does not
decrease when a card is played.

Equivalent-copy rebasing is deliberately local to the immediate live reroot.
It proves the candidate by swapping only the retained and observed card UIDs,
then requiring the ordinary-card equivalence and full search-state checks to
match. It does not relax `equalForSearch()`, merge UID-distinct states in the
global dedup table, or make chance-node identity less strict.

Rest observations are emitted only while the installed campfire UI exists, is
visible, and has not selected an option. Selecting a campfire option therefore
clears the old rest observation while the option resolves.

For `card_reward` and `rest`, the native endpoint now validates the detached
deck and candidate card-instance arrays (canonical save-file card ID, upgrade
flag, and misc value). Valid observations still fail closed because validation
is not yet a native `GameContext` import. Importer and post-identity validation
errors carry the observation session, sequence, and hash; malformed or
pre-identity envelopes remain uncorrelated because their identity cannot be
trusted.

Run the endpoint after building:

```text
build/linux-gcc-debug/one_combat_advisor
```

Use `tools/mod/doctor.sh` to locate the standard Steam installation and
workshop dependencies. Build the local JAR with
`mods/sts-model-inspector/build.sh MODTHESPIRE.jar BASEMOD.jar desktop-1.0.jar`.
The bundled Steam runtime is sufficient to launch the game but does not ship a
Java compiler, so a Java 8 JDK is needed for the build; the helper does not
install one or alter system defaults.

For a handshake:

```json
{"protocol":"sts_model_inspector_v1","kind":"hello"}
```

An observation must include `session`, `sequence`, `observationHash`, and an
object containing a string `boundary`. The response echoes the identity fields
so a future game UI can discard responses after a reload or newer capture.

## Remaining bounded boundary

The Java process owns bounded background I/O and treats the endpoint as
advisory only. Common Grid and Hand card-selection screens are mapped to the
native selection tasks for Exhaust, Armaments, Dual Wield, Headbutt, Exhume,
Warcry, Gambler's Brew, Liquid Memories, and Hologram. The mapping remains
deliberately bounded: an unrecognized selection prompt, an unavailable runtime
tracker, or an option list larger than the native representation is rejected.
The ordinary player limbo pile is serialized. The remaining common combat
exclusion is live Runic Dome because exact public pre-roll reconstruction has
not been proven. Other unsupported queue metadata remains outside the
supported boundary. CTM and Silver results remain separate evaluators, and
neither path controls gameplay or establishes policy-quality evidence. Any
future public-state expansion must add a native parity fixture and an explicit
public-information contract before promotion.

Knowledge impact: this page records the protocol/lifecycle boundary, the
player-visible combat gate, protocol-v4 producer/importer contract, explicit
fail-closed state handling, selection coverage, and the producer coverage
boundary.
