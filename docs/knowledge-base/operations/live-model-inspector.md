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
upgraded/misc/cost/retain/free-play fields, powers with amount and
`justApplied`, dead monster slots, relics, potion slots, the combat entry
identity, and a centralized native mapping boundary for runtime IDs. Ordinary
draw order is sorted before emission; the actual runtime order is retained when
Frozen Eye is present. Runic Dome move bytes are redacted and the importer
rejects that root until a complete public hidden-intent tracker is available.
The installed game API has no public `justApplied` power bit, so that schema
field is emitted conservatively as `false` at stable user boundaries.
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
advisory only. The current producer does not yet serialize every native
runtime tracker (notably live card-selection screens and all queue/limbo/
stasis metadata), so those roots must not be treated as fully supported merely
because the native wire can represent them. CTM and Silver results remain
separate evaluators, and neither path controls gameplay or establishes
policy-quality evidence. Any expansion of the producer must add a fixture and
an explicit public-information contract before promotion.

Knowledge impact: this page records the protocol/lifecycle boundary, the
player-visible combat gate, protocol-v4 producer/importer contract, the Runic
Dome redaction, and the explicit producer coverage boundary.
