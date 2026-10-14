# ADR-0037: The live advisor uses the ADR-0036 escape penalty

Date: 2026-10-14
Status: accepted

Supersedes the live-advisor part of [ADR-0036](0036-silver-escape-penalty-default.md), which kept the live-game
advisor at escape scored as a win.

## Context

ADR-0036 made native Silver charge a Smoke Bomb escape 12 (normal) and 35 (elite-trigger) by default. The live-game
advisor (`apps/one_combat/native_silver_advisor.cpp`) builds its own `SilverSearcher` from the wire context and kept
the struct default 0, so live play scored escapes differently from simulator runs. The Silver synthetic-prior
generator already copies the backend's weights and needed no change. On 2026-10-14 (21:30Z, thread "Flag audit"),
asked about these two paths, Philipp wrote: "merge 549. change those two things pls."

## Decision

- The live advisor sets `escapePenalty = 12` and `eliteEscapePenalty = 35` (`kDefaultEscapePenalty`,
  `kDefaultEliteEscapePenalty` in `SilverSearcher.h`, shared with `NativeSilverBackend`). Like the ADR-0035 leaf
  terms, the live path reads no environment, so `STS_SILVER_ESCAPE_PENALTY` does not reach it.
- The wire carries no room, so `searchContextFromWire` marks a fight elite-trigger by its encounter: the act 1–3
  elite encounters, `SHIELD_AND_SPEAR`, `COLOSSEUM_EVENT_NOBS` and `LAGAVULIN_EVENT` (only Dead Adventurer uses
  it; its other two fights are the elite `THREE_SENTRIES` and `GREMLIN_NOB`).
- `SilverEvalWeights` struct defaults stay 0, so unit tests and the wire replay tools are unchanged.

## Consequences

- Live play and native simulator runs now score escapes the same way, up to the room-versus-encounter elite test.
  `GameContext::isEliteTriggerCombat` is true for elite rooms, Dead Adventurer and the Colosseum Nobs; the engine
  fills elite rooms from the act elite lists (`SHIELD_AND_SPEAR` in act 4). One difference: an act 1–3 elite
  encounter met outside an elite room or Dead Adventurer would count as elite on the wire only (**Inference:** no
  such path was found).
- `searchContextFromWire` sets `eliteRewards` for elite encounters in every caller; it only changes a score when a
  penalty is non-zero.
- **Unverified:** a live playing-strength effect; no live game was played.

## Evidence

ADR-0036 and ledger-06 §473; `test silver_escape_penalty` (now also checks the wire elite flag);
`architecture/combat-search.md`.
