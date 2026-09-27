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

Pending execution after the implementation SHA is frozen.
