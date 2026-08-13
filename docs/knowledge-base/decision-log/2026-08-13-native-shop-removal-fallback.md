# 2026-08-13 — Native shop-removal fallback

Date: 2026-08-13
Session/task: Diagnose and fix the native `bestbench` stall with no value server.

## Decision

Use the deployed native floor model to rank card-removal candidates on the
shop `CARD_SELECT/REMOVE` follow-up, and bound localhost value-server connects
to one second.

## Rationale

The live backtrace showed native `bestbench` blocked in `connect()` through
`vTransact` → `removeSelectVPolicy` → `runFullRunOOC`. Native shop planning
already scored the removal candidate with the same floor tree, but the
follow-up selector unconditionally sent an `X;` request to `v_server.py`.
That contradicted the native-OOC serverless baseline and made a missing server
look like a search hang.

## Alternatives considered

- Disable shop removals — rejected because it changes the deployed shop policy.
- Start `v_server.py` for every benchmark — rejected because native OOC is
  intended to be serverless and the native model already supports this choice.
- Leave blocking connects unchanged — rejected because explicit legacy/server
  modes must fail fast when their dependency is absent.

## Evidence

- `apps/one_combat.cpp::nativeShopPlan` already scores removal candidates with
  `models/v_rich_trees.txt`.
- `apps/one_combat.cpp::vQueryRemove` now uses that native scoring when
  `g_nativeOoc && !g_shopWin && g_floorNet.ok`.
- `apps/one_combat.cpp::vConnect` now uses nonblocking connect + `select` with
  a one-second timeout.
- `bestbench 100 1 0` with `OMP_NUM_THREADS=1`, no server, completed with
  `cpu_sec/run=0.11` and `wall=0.1s` after the fix.

## Status and follow-up

- Implemented and verified. Search behavior and model artifacts were not
  otherwise changed.
