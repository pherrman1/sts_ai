# 2026-08-24 — E3a direct eventual-run reference infrastructure

## Decision

Add `one_combat runwinrank` as a separate default-off diagnostic mode.  It
does not alter `runwinshadow`'s E2c RAW-critic meaning and never returns a
diagnostic value to Searcher3, OOC policy, or live game state.

For each source run it captures a deterministic bottom-k reservoir of exact
source leaves per source decision, retains only rankable roots (at least three
sampled leaves), and selects the two lowest root hashes after the live source
run completes.  Both hashes are functions only of source/root or source/leaf
identity, respectively; neither incorporates an E2c score, survival, or
eventual-run outcome.  The source callback copies state and uses no live search
RNG.

The selected source leaves reuse the existing R-replicate `runwinshadow`
terminal-continuation/E2c-RAW estimator.  Separately, every direct reference
future uses a diagnostic-combat seed keyed by source seed, fight index,
decision index, root identity, and future index — explicitly not leaf
identity, so sibling leaves have common random numbers.  A combat loss is
exactly zero.  A victory transfers its copied `BattleContext` through
`BattleContext::exitBattle` into a detached copy of the exact battle-entry
`GameContext`, then calls `finishOocCounterfactual(..., maxFights=-1,
bootstrap=false)` with an independently root/future-keyed downstream agent
seed.  Thus the direct label is a policy-conditional actual copied-run outcome
and does not evaluate the E2c critic.

## Artifacts and analysis

`runwinrank` writes an existing-schema E2c shadow CSV plus `.reference.csv`
(one row per exact source leaf and future), `.roots.csv`, `.runs.csv`, and a
provenance JSON.  The reference records combat and downstream seeds,
combat-survival, actual run win, validity, terminal floor/HP, and health
status.

### SAME-WORLD CRN reference semantics

The M direct-reference futures are **SAME-WORLD CRN continuations**. For a
source root, the detached battle-entry `GameContext` retains environment and
hidden-future RNG state across sibling leaves and all M futures. Future index
changes only the explicitly root/future-keyed diagnostic combat-policy RNG and
downstream agent RNG, neither of which contains leaf identity. `V_direct` is
therefore a policy-conditional, paired realized-world reference; it is not an
M-sample marginalization over newly sampled maps, rewards, or encounters.
Independent source runs/seeds provide environment-world variation, and the
outer bootstrap resamples source seeds. This is a design contract, not an E3a
scientific result.

`tools/analyze_runwin_rank.py` validates the E2c source-leaf identity and
collapse contract, requires exact direct future coverage, excludes invalid
complete references, reports root-equally-weighted ranking metrics, seed-level
bootstrap uncertainty, and even/odd split-half reference reliability.  Its
primary default is `M=8`; the low-cost smoke explicitly uses `M=2` and must be
analyzed with `--futures 2`.

## Scope

This records implementation semantics only.  It is not an E3a scientific
result and does not authorize the designated 16-seed collection before an
independent review/frozen implementation SHA.
