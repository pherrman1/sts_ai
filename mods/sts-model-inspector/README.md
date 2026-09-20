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
