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
available. The `silver_player_decision_v2` evaluator imports any stable public
decision in a supported starter-deck combat, verifies converted-state parity
and legal actions, and runs the fixed 1,000-simulation Silver configuration.
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
value, plus the player turn, in-turn decision number, and reroot diagnostics.
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
version-3 phase-independent decision envelope, stable card UUIDs, the public
last-card state, the two latest public monster moves, public combat counters,
and power IDs with amounts. A minimal observer-side tracker retains only public
facts needed for exact reconstruction, including damage since the prior
decision and whether player Vulnerable previously appeared. Under Runic Dome,
intent and intent damage are omitted from both the payload and fingerprint
because they are not player-visible. The combat boundary requires the installed runtime's
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
Git. Silver live support is fail-closed to ordinary Act-1 Ironclad Cultist and
Jaw Worm combats plus non-burning Act-1 Gremlin Nob, Burning Blood only, empty
potion slots, the exact 5 Strike / 4 Defend / 1 Bash unupgraded starter deck,
and every public move of those three monsters. Strike, Defend, Bash, End Turn,
multiple cards per turn, later turns, reshuffles, Cultist Ritual/Strength, Jaw
Worm Strength/block, Gremlin Nob Enrage/Strength, and player/monster Vulnerable
are mapped. Unknown powers, burning elites, Runic Dome, Frozen Eye, missing
state, non-empty potions, and live RNG fields are rejected. A single
deterministic search seed derived from `combatEntryHash` is retained for the
whole combat. A missing retained branch starts a fresh root rather than making
an otherwise exact public state unsupported. A new protocol session, a new
combat, or a genuinely unsupported state discards the prior Silver session.

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
advisory only. Future work must not broaden this milestone's encounter or deck
support without a new contract and parity fixtures.
CTM and Silver results remain separate evaluators, and neither path controls
gameplay or establishes policy-quality evidence.

Knowledge impact: this page records the protocol/lifecycle boundary, the
player-visible combat gate, the Runic Dome redaction, the complete supported
starter-combat Silver evaluator contract, and its diagnostic-only limitation.
