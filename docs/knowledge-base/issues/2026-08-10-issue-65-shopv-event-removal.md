# Issue 65: Shop-V intercepts event/Neow removals

- **Status:** closed (2026-08-10)
- **Tier:** Medium
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `apps/one_combat.cpp:2785`

## Symptom

`runFullRunOOC`'s `shopV && inRemoveSelect → removeSelectVPolicy` branch
is not shop-scoped. `CardSelectScreenType::REMOVE` is used by shop removal,
Neow removals, EMPTY_CAGE, and many events (Purifier, Ancient Writing, etc.).
With `shopV=1` (always in bestbench/cpsictr/reprobench), all remove-selects
are routed to the shop-removal V-policy, even for Neow/event/relic removals.

## Evidence

- `one_combat.cpp:2785`: `inRemoveSelect` branch inside `shopV` guard.
- `Shop.cpp:166`: shop removal uses REMOVE screen.
- `GameContext.cpp:2288,2343,1363,2501,3171`: Neow, EMPTY_CAGE, event REMOVE users.
- Event branches only match `EVENT_SCREEN`, never see CARD_SELECT sub-screen.

## Why it matters

Silent coupling of a shop flag to event/Neow removal policy. The choice of
which card to remove differs between the shop-V model and the default heuristic.

## Candidate fix directions

Scope `inRemoveSelect` to shop room namespace only, or add a room-type check,
or document the coupling explicitly.

## Relevant code

- `apps/one_combat.cpp:2785`
