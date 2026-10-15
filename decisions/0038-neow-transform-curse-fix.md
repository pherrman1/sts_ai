# ADR-0038: Neow "transform two cards" adds a curse only with the CURSE drawback

Date: 2026-10-15
Status: accepted

## Context

Neow's second-tier bonus "transform two cards" always comes with a drawback.
Our engine (`GameContext::chooseNeowOption`, `src/game/GameContext.cpp`) also
added a random curse whenever that bonus was picked, whatever the drawback.
It then reset `regainControlAction` to `returnToMapAction`, which dropped the
CURSE drawback's own pending curse. So every transform pick got exactly one
curse, rolled before the transforms.

daniel-ziegler/sts_lightspeed @84ab3ea (silverbot, MIT) removed that curse and
keeps the drawback's `regainControlAction`. The heart1 adapter's cross-engine
parity check (PR #552) found the difference: our deck had one extra curse after
"transform two cards" with a non-curse drawback (for example seed 74071651,
Neow option 2, REGRET). The independent review of #552 confirmed it as an
engine bug.

On 2026-10-15 Philipp chose to fix it with the fix on by default ("Fix the bug,
but on by default").

## Decision

- With `STS_NEOW_TRANSFORM_CURSE_FIX` unset, "transform two cards" adds no curse
  of its own. The CURSE drawback adds its curse after the two transforms; any
  other drawback adds none.
- `STS_NEOW_TRANSFORM_CURSE_FIX=0` restores the legacy behavior exactly. `1` is
  accepted and equals the default. Any other value is fatal.
- No other Neow option, and no other part of the engine, changes.

## Consequences

- Runs whose Neow pick is "transform two cards" can play differently from
  before, in every driver, mode and ascension. Runs with any other pick are
  unchanged.
- Earlier results need `STS_NEOW_TRANSFORM_CURSE_FIX=0` to reproduce. Comparisons
  against controls run on an older binary must either set it to `0` in the new
  arm or rerun the controls.
- The flag is not part of the OOC policy identity: it is engine behavior, like
  the other engine corrections.
- **Unverified:** the playing-strength effect. The default was chosen because it
  is a correctness fix, not because a game test passed.

## Evidence

`tests/neow_transform_curse_test.cpp` (ctest `neow_transform_curse`). On fixed
seeds it covers transform options with and without the CURSE drawback, under the
default, `=1` and `=0`.
