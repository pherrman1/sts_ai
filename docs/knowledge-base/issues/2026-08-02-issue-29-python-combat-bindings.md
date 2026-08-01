# Issue 29: Python cannot issue card-by-card combat actions

- **Status:** open
- **Tier:** Low
- **Last verified:** 2026-08-02
- **Source:** [`architecture/out-of-combat.md`](../architecture/out-of-combat.md), "Known limitations"; [`architecture/overview.md`](../architecture/overview.md)

## Symptom

The Python bindings expose run-level `GameContext` and agents but not
`BattleContext` or combat `search::Action`, so Python cannot issue card-by-card
combat actions. Combat control remains C++-only unless the binding surface is
deliberately extended.

## Evidence

- `bindings/slaythespire.cpp::PYBIND11_MODULE`: run-level surface only.
- `overview.md` "Open questions": whether the Python API should ever expose
  combat state/actions.

## Why it matters

It limits experimentation tooling (e.g., scripted combat probes) but is a
deliberate boundary; this entry exists to make the limitation trackable if the
boundary is ever reconsidered.

## Candidate fix direction

Open question; no change without an explicit design decision to extend the
binding surface.

## Relevant code

- `bindings/slaythespire.cpp::PYBIND11_MODULE`
- `include/combat/BattleContext.h`, `include/sim/search/Action.h`

## Resolution (2026-08-02)

Deliberate binding boundary (run-level Python API only); no change without an explicit design decision.

## Closed by

*Fixed in the 2026-08-02 working tree. No change; remains open.*
