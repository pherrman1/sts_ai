# Live model inspector

Last verified: 2026-09-19. This page describes the private integration
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
available. The `silver_first_turn_v1` evaluator imports an Ironclad first-turn
Silver root, verifies converted-state parity and legal actions, and runs the
fixed 1,000-simulation Silver decision configuration. It returns the selected
action plus root action summaries containing edge visits and selection Q values.
Unsupported encounter, relic, information, or schema states remain explicit
`UNSUPPORTED` results; this is a diagnostic ranking display, not a gameplay
controller or a qualification of Silver policy quality. `STALE` responses
reject a second observation with an equal or older sequence in the same
session. A new process starts a new session state.

The Java frontend is under `mods/sts-model-inspector/`. It uses BaseMod
post-update/render subscribers and captures detached Ironclad-compatible
summary fields for card rewards, rest sites, and ordinary player turns. Combat
observations include only player-visible decision state: turn, energy, player
block, cards played this turn, hand/draw/discard/exhaust card instances,
potions, relics, and living-monster HP, max HP, block, next move, intent, and
intent damage. The Silver root reuses this combat snapshot and adds the
versioned first-decision envelope. Under Runic Dome, intent and intent damage
are omitted from both the payload and fingerprint because they are not
player-visible. The combat boundary requires the installed runtime's
waiting-for-user phase, no current action, empty action/card/monster queues,
and an unended turn. The combat fingerprint includes that payload, so
successive decisions are not collapsed into one observation. A battle-start
hook can precede encounter population, so combat-entry and Silver-root
identity are captured lazily at the first actionable decision. A stable-
boundary loss clears the displayed observation and fences late responses from
the prior decision. Advisor writes use one bounded latest-observation slot;
intermediate captures are replaceable rather than queued without limit. It
launches the advisor with a direct `ProcessBuilder` call. The F8 panel remains
diagnostic and read-only. Workshop and game/dependency JARs remain outside
Git.

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

The next implementation must add the native importer for the expanded public
deck/candidate snapshot and parity tests against the existing OOC contract.
The Java process must own bounded background I/O and treat the endpoint as
advisory only. Silver support remains intentionally narrow: Ironclad first-turn
combat with the importer-supported cards, monsters, relics, potions, and
information state. CTM and Silver results remain separate evaluators, and
neither path controls gameplay or establishes policy-quality evidence.

Knowledge impact: this page records the protocol/lifecycle boundary, the
player-visible combat gate, the Runic Dome redaction, the narrow Silver
first-turn evaluator contract, and its diagnostic-only limitation.
