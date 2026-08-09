# 2026-08-09 — V4 feature-leak audit: 8 genuine leaks, bossId is legit

Date: 2026-08-09
Session/task: Investigate which of the 9 features removed from the V4 tok-net
glob block are genuine hidden-information leaks vs player-observable. Build
an honest V4 model and gate it.

## Decision

**8 of the 9 features are genuine leaks. bossId is NOT a leak** — the act boss
is visible on the map in Slay the Spire. The repo's own convention confirms
this (`resampleRemainingActEncounters` deliberately preserves bossId with the
comment "visible to the player").

### Classification

| Feature (original glob idx) | Verdict | Evidence |
|---|---|---|
| bossId (14) | **LEGIT** | Visible on act map. Repo convention: `termWinArmForBattle` deliberately keeps it. |
| nextEliteId (15) | **LEAK** | Exact elite identity from hidden pre-rolled queue. Player sees only "elite node." |
| nextFight0/1/2 (16-18) | **LEAK** | Exact fight IDs from hidden pre-rolled queue. Player sees only "monster node." |
| remElites (19) | **LEAK** | Hidden queue size. Player sees map nodes but queue may differ. |
| remFights (20) | **LEAK** | Hidden queue size. |
| monOffset (21) | **LEAK** | Internal queue position. No player-visible analog. |
| eliteOffset (22) | **LEAK** | Internal queue position. No player-visible analog. |

**Forward-map (fm*) features, pv* features, and threshold features are all legit** — derived from either the deterministic visible map graph or player-own-game-state.

### Honest V4 model

A retrain on the 4,650-seed tierb corpus removed all 9 features (including bossId
— over-removed). Constants: NGLB=41, FUSIN=97, NFILE=473. Model trains and loads
correctly; the old `ooc_strategic_tok_final.native` (NGLOB=50) is properly rejected
by the dims check.

**Offline metrics** (40 epochs, eager, best epoch val_pol_ce):
- val_pol_ce: 0.491 (vs deployed leaky 0.486)
- policy_top1: 0.790 (vs 0.793)
- q_top1: 0.285 (vs 0.290)
- q_mae: 16.71 (vs 16.22)

**128-seed gate** (fair S2, @1k, full gate stack m1.0, block 126700–126827):
- **22.7%** win, floor 39.0, HP 18.0
- Baseline (no gates): 21.1% (§68)
- Deployed leaky V4: 41.4% (§81)

The gate benefit collapsed from ~+20pp (leaky) to ~+1.6pp (honest). Offline
metrics were nearly identical but online transfer failed — consistent with the
§62/§75/§100/§108 pattern.

### Correction needed

bossId should be added back. Correct constants: NRAW=36, NGLOB=42, FUSIN=98.
The 8 genuine leaks stay removed.

## Rationale

- The hidden-info audit (2026-08-02) explicitly left bossId as an open question,
  noting the repo convention treats it as public but §A.14 lists exact encounter
  identity as hidden. Investigation confirms: in Slay the Spire, the boss icon
  IS shown on the act map. The repo's own `resampleRemainingActEncounters` code
  deliberately preserves bossId.
- The 8 other features access `monsterList`/`eliteMonsterList` queues which are
  pre-rolled at act start from RNG and contain exact encounter identities. The
  player sees only node types on the map, never exact identities.
- The forward-map (fm*) features are computed by `forwardMapFeatures()` which
  is a pure reachability sweep over the deterministic Map graph — confirmed by
  code comment at one_combat.cpp:475-478.

## Alternatives considered

- Remove only the 5 identity leaks (nextFight0-2, nextEliteId, bossId) and keep
  the queue-structure features (remElites, remFights, monOffset, eliteOffset) —
  rejected: the queue counters are also hidden information; they're partially
  redundant with map-visible fm* features, so removing them should not hurt.
- Keep all 9 removed and accept the gate drop — rejected: bossId is legit player
  information and removing it is an unnecessary handicap.

## Evidence

- `apps/one_combat.cpp`: `richRow` (3360-3396) and `buildTokState` (3447-3535)
  populate leak features from `gc.monsterList`, `gc.eliteMonsterList`, offsets.
- `src/game/GameContext.cpp`: `monsterList`/`eliteMonsterList` populated at act
  start (lines 570-625, 690); `boss` set from `s.boss_list[0]` (line 152).
- `include/game/Map.h`: Map stores only `Room` types, no encounter identities.
- `docs/knowledge-base/decision-log/2026-08-02-hidden-info-audit.md`: finding
  2b confirms `buildTokState` feeds exact next encounters.
- `selfplay/models/ooc_strategic_tok_honest.native`: sha256
  `fabbcb938a45939e6260f2d986a0e38e786c76e97787ca54d100d2f911544dd0`
- `build/tok_honest_128.csv`: 128-seed gate results.
- `build/tok_honest.pt_metrics.json`: training metrics.

## Status and follow-up

- Audit done; honest model trained and gated (code + model exist in working tree).
- **Code correction done** (2026-08-09): bossId re-added to `buildTokState`, `tokCheckGlobParity`,
  `tok_net.h` (NGLB=42, FUSIN=98), `strategic_tok_net.py` (NGLOB=42, NRAW=36),
  `train_strategic_tok.py` (NFILE=474, col 14 → bossId slot). Build + ctest 9/9 pass.
  Old NGLOB=41 model correctly rejected.
- **Corrected model trained** (2026-08-09, 40 epochs, no early stop): val_pol_ce=0.488,
  policy_top1=0.793, q_top1=0.295, q_mae=16.60 — offline slightly better than the
  NGLOB=41 honest model. Exported `selfplay/models/ooc_strategic_tok_honest_v2.native`
  (799,176 bytes, 32 parity checks pass).
- **192-seed gate** (S2 fair @1k, margin 1.0, seeds 126700–126891): **15.6% win**
  (baseline 21.1%, old honest 22.7%). Offline→online inversion persists — offline
  metrics improved but online got worse. Gate benefit collapsed.
- **Open:** q_top1 checkpoint selection was never applied (§139 +1.7pp lever).
