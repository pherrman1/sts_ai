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
upgraded/misc/cost/retain/free-play fields, dead monster slots, relics,
potion slots, the combat entry identity, and a centralized native mapping
boundary for runtime IDs. Monster move-history bytes are emitted in Java's
oldest-to-newest order and translated by the native importer through the
per-monster mapping; they are never copied as native enum values. Ordinary
draw order is sorted before emission; the actual runtime order is retained
when Frozen Eye is present. Runic Dome roots are rejected because the public
producer does not expose enough hidden-intent state. The installed game API
does not expose a public `justApplied` power bit; sensitive player and monster
powers therefore require an explicit serialized bit and are rejected when it
is unavailable rather than receiving a fabricated default. Special bookkeeping
for Combust, Echo Form, Panache, Deva Form, Orange Pellets, used-up relics,
and Necronomicon is serialized when its runtime field is accessible; otherwise
the importer rejects that state. Monster `miscInfo` is similarly serialized
from known runtime trackers or omitted so the importer fails closed.
The observer's post-`AbstractPlayer.damage()` patch records finalized damage
once per public damage call, preserving multi-hit event counts and the final
individual unblocked hit. The v4 importer rejects observations unless the
producer asserts this exact tracking; the old per-turn combat-damage total is
not an accepted approximation. Move bytes are likewise fail-closed: only the
runtime-qualified Cultist, Jaw Worm, and Gremlin Nob mappings currently cross
the live boundary until additional Java encounter constants are independently
qualified.
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
live monsters. Potion candidates are emitted only when MCP advertises the
corresponding `can_use` or `can_discard` capability. The post-action identity
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

## Required next work

The Java process owns bounded background I/O and treats the endpoint as
advisory only. Common Grid and Hand card-selection screens are now mapped to
the native selection tasks for Exhaust, Armaments, Dual Wield, Headbutt,
Gambler's Brew, and Hologram. The mapping is deliberately bounded: an
unrecognized selection prompt, an unavailable runtime tracker, or an option
list larger than the native representation is rejected. The ordinary player
limbo pile is serialized; Bronze Orb roots are rejected because its stasis
card is not publicly trackable. Other unsupported queue metadata remains
outside the supported boundary. CTM and Silver results remain separate
evaluators, and neither path controls gameplay or establishes policy-quality
evidence. Any expansion of the producer must add a native parity fixture and
an explicit public-information contract before promotion.

Knowledge impact: this page records the protocol/lifecycle boundary, the
player-visible combat gate, protocol-v4 producer/importer contract, explicit
fail-closed state handling, selection coverage, and the producer coverage
boundary.
