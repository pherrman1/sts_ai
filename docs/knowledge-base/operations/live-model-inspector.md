# Live model inspector

Last verified: 2026-09-18. This page describes the private integration
boundary currently present in the repository; it is not a claim that a game
mod or live evaluator importer is complete.

## Current boundary

`one_combat_advisor` is a small, read-only newline-delimited JSON process.
Its stdout contains protocol responses only; malformed input and failures are
returned as structured errors. It validates the protocol name, request kind,
session, monotonic observation sequence, observation hash, and the required
observation boundary. It never receives RNG state or controls the simulator.

The current endpoint deliberately returns `UNSUPPORTED` for every validated
observation. No Java-game importer exists in this checkout, so returning a
native score here would be fabricated and could silently violate the
player-information boundary. `STALE` responses reject a second observation
with an equal or older sequence in the same session. A new process starts a
new session state.

The Java frontend is under `mods/sts-model-inspector/`. It uses BaseMod
post-update/render subscribers, captures detached Ironclad-compatible summary
fields for card rewards, rest sites, and ordinary player turns, and now exports
the visible deck instances plus card-reward candidates and upgradeable rest
targets. It launches the advisor with a direct `ProcessBuilder` call. Its F8
panel remains diagnostic until a native importer proves parity. Workshop and
game/dependency JARs remain outside Git.

For `card_reward` and `rest`, the native endpoint now validates the detached
deck and candidate card-instance arrays (internal ID, upgrade flag, and misc
value). Valid observations still fail closed because validation is not yet a
native `GameContext` import.

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
advisory only. Until the importer proves the required public-state parity, the
endpoint must remain fail-closed and must not be described as a live
evaluator. CTM and Silver remain separate later integrations.

Knowledge impact: this page records the new protocol/lifecycle boundary and
the explicit unsupported state; evaluator semantics and game-hook timing
remain open questions.
