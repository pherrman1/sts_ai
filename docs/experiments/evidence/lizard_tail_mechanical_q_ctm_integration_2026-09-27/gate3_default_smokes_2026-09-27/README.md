# Gate 3 default-plumbing smokes

## Frozen smoke plan

This packet is reserved for the two requested Gate 3 plumbing checks. The
implementation must be committed and its source SHA and executable SHA-256
recorded before either gameplay smoke starts. No Gate 3 smoke has been run at
the time this plan is written.

| Case | Seed | Forced relic |
| --- | ---: | --- |
| Ordinary stack | 991016 | none |
| Active-Lizard stack | 991017 | `LIZARD_TAIL` |

Both use Ascension 0, Act-3 horizon, project-fair native Silver with 10,000
real-combat simulations, and 2,048 OOC MCTS simulations. Each invocation must
go through `tools/seed_guard.sh`, use a fresh result/sidecar/trace/log path,
and run under a clean environment matching the Gate 2 follow-up configuration
except for these required Gate 3 changes:

- `STS_OOC_MCTS_COMBAT_MODEL` and `STS_OOC_MCTS_BREW_FALLBACK_MODEL` are unset.
- `STS_OOC_MCTS_ACTIVE_LIZARD` is unset so the promoted stack's default is
  exercised.
- `STS_FORCE_RELIC=LIZARD_TAIL` is set only for seed `991017`.
- `STS_EXECUTABLE_GIT_SHA` identifies the committed implementation used for
  both invocations.

No replacement seeds or additional gameplay runs are authorized by this
smoke plan. A passing run must complete normally and its process log and
metadata must show the promoted DeepSets artifact, automatic standard
Attention Brew fallback, and `active_lizard_correction=1`. The ordinary run
checks default startup without a forced relic; the second run checks that the
default correction is active with a forced active Tail. These checks establish
plumbing only, not gameplay quality.

## Results

Both frozen cases used implementation commit
`529c214562fd7eda4842f4386c05303c4d3d3d47`, executable SHA-256
`ebe2dcc09b0ca76867a12332f583e7529a58991033afeb7b7a00fb065a5e10fe`, and
clean environments with the three model/active-Lizard override variables
unset. Guard-only preflight passed for both before gameplay. The promoted CTM
artifact was SHA-256
`abb2a9ead6efd6b97ee64192e0459eb08ceff7fd93f2b5f4b87a0bf379e571ab`, its
tensor-payload SHA-256 was
`429f9dc018a6b9de231657df4aba787bddc2de2e4cecb2e7989e167c37813139`, and the
automatic standard Attention fallback was SHA-256
`e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`.

| Case | Seed | Outcome | Lizard preparations / samples | Support result |
| --- | ---: | --- | ---: | --- |
| Ordinary (no forced relic) | 991016 | Win, floor 51, 40 HP | 1 / 1 | No support aborts |
| Forced active Tail | 991017 | Win, floor 51, 10 HP | 17,610 / 17,608 | Two existing `smoke_bomb` exclusions; no fast/fallback support failures |

Both startup logs selected the promoted DeepSets artifact, the standard
Attention Brew fallback, and `active_lizard_correction=1`; the combat telemetry
reported `activeLizardEnabled=true` in both runs. The forced-Tail case exercised
the Lizard path and produced no support reason other than the model's existing
`unsupported:smoke_bomb` exclusion. These smoke outcomes are plumbing evidence,
not gameplay-quality evidence.

Two logging limitations are preserved rather than inferred away. The ordinary
case produced its complete CSV, sidecar, traces, and normal final `BEST`
summary, but the post-run validator raised on the malformed auxiliary
`[ooc-mcts-config]` JSON before saving the child process exit code; seed 991016
was not repeated. That same auxiliary line is malformed in both logs because
its `dispatchRule` string lacks a closing quote. The separate `[live OOC MCTS
ON ...]` startup line and `[ooc-combat-transition]` telemetry are intact and
verify the effective stack. Fixing that pre-existing config-line formatting
and recapturing an ordinary-case exit status would require a new frozen smoke
implementation; this packet does not claim either result.

The frozen manifest SHA-256 is
`e3778296788e8550f450d85df8dbf897e4886f009542061d5debcb028b67cf93`; the
machine-readable result SHA-256 is recorded in
`gate3_results.json.sha256`. Raw logs, CSVs, sidecars, traces, status, and both
guard-only checks are included alongside the manifest.
