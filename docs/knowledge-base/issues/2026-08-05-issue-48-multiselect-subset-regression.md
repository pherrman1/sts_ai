# 2026-08-05-issue-48 — Multi-select full-subset enumeration "regresses" win rate (closed: control battle-skip exploit)

**Tier:** High (resolved)
**Status:** closed (2026-08-05)
**Source pages:** [combat-search](../architecture/combat-search.md),
historical evidence

## Symptom (as first reported)

After the issue-47 fix, enumerating every subset of the hand for
EXHAUST_MANY/GAMBLE (up to 1023 actions at a 10-card Gambler's Brew state)
appeared to regress full-run win rate at fixed simulation budgets: full
candidate **39.5% vs 56.6% control** on 256 paired seeds @1k/256p (paired
−17.2pp, SE 3.1); S3-only bisect 43.8% vs 56.3% control on 64 seeds. Control
reproduces the §111 reference bit-identically.

## Resolution

**The "regression" was not a search-quality loss — the control S3 enumerator
was skip-winning battles.** Control S3's `enumerateActionsForNode` default
branch emitted `SINGLE_CARD_SELECT 0..pickCount-1`; `WarcryAction` and
`GambleAction` never set `pickCount` (stays 0), so at WARCRY and GAMBLE
CARD_SELECT states it emitted **zero valid edges**. The root pick found no
action (`have=false`), the battle loop `break`ed with **UNDECIDED** outcome,
and `BattleContext::exitBattle` treated non-loss as victory — rewards + floor
advance, and a skipped act-3 boss fight recorded `PLAYER_VICTORY`.

- Instrumented counter (`STS_DEBUG_BATTLE_BREAKS`): 41 breaks / 8 seeds on
  control S3 (27 GAMBLE, 13 WARCRY); 164 / 256 seeds.
- Decisive A/B (same control binary, 8 seeds @1k): silent skip = **62.5%**
  win; break→LOSS = **0.0%** / floor 30.0.
- S2 control has no skip (its GAMBLE case emitted a valid empty
  `MULTI_CARD_SELECT 0`): 0 breaks on 16 seeds — the exploit is S3-specific.
- The fixed canonical enumerator produces **0 breaks** on 256 seeds @1k and
  @3k (EXPERIMENTS.md §113).

## Fixes deployed

1. Committed canonical enumerator (issue 47) — complete valid enumeration.
2. `BattleContext::exitBattle` now treats an UNDECIDED outcome as
   PLAYER_LOSS instead of granting rewards (a future enumerator gap costs a
   loss, never a free win).

## Status

- Honest re-baseline (256 seeds, V4 gate stack, canonical + fix): **36.3%
  @1k, 42.6% @3k** vs honest control S3 **9.0% @1k** — the parity fix is
  worth +27.3pp over honest control.
- `STS_MULTISELECT_MODE=single/none` with a pickCount-capped single-select
  pool (experimental) measured 31.6%/30.5% @1k — **negative vs canonical
  `all` (36.3%)**, so the full validity contract stays the deployment
  default and the knob remains an opt-in search-scale lever.
- Closed: there is no multi-select regression. Note for readers: §107
  (60.2%), §111 (56.6%), §112 (56.3%) and the S3 arms of §99–§105 are
  invalidated as honest baselines by the skip exploit; §99's Searcher2
  headline (45.3%) survives.
