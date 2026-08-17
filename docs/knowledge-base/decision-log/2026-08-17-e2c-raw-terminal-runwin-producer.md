# 2026-08-17 — E2c exact raw/post combat-terminal run-win producer

## Decision

Add an opt-in `one_combat e2cgen` producer that records matched RAW and POST
snapshots for every survived ordinary/elite/act-1-2-boss combat, plus an offline
analyzer (`tools/analyze_postcombat_raw_terminal.py`). This is measurement
infrastructure only; no deployment, Searcher3, V_combat, or policy change.

## Capture boundaries (verified)

- **RAW** fires inside `BattleContext::exitBattle` immediately after the
  persistent-transfer block (HP/maxHP, potions, relic counters, deck, RNG
  streams, stolen gold) and before `g.regainControl()`, so no reward generation
  has run.
- **POST** fires at the `REWARDS` screen after all non-card rewards
  (gold/relic/potion/key) are drained and immediately before the first card
  pick/skip.
- Pair key is `(seed, fight_index)`; each pair shares the same eventual `won`
  label.

## Live-only scoping

The thread-local `BattleContext` hook `g_onBattleExitPersistent` is null by
default. `runFullRunOOC(..., e2cCapture=true)` arms it only immediately around
the one real `bc.exitBattle(gc)` call and disarms it immediately after. All
copied/counterfactual/replay calls to `exitBattle` see the hook unset, so they
cannot produce E2c rows. `testE2cObserverScope` pins this: an unarmed
non-live `exitBattle` never invokes the observer, and an armed victory exit
invokes it exactly once.

## Act-horizon labels

Rows receive the same effective label as `runFullRunOOC`'s `RunResult`
(`clearedStopActBoss || gc.outcome == PLAYER_VICTORY`), so an intentionally
completed `STS_STOP_AFTER_ACT` run is labelled by its horizon. The shared
training-integrity predicate is unchanged: unresolved (not won, `UNDECIDED`)
runs and any simulator-health failure are still quarantined.

## Relic representation

E2c emits explicit `relic_has_<id>` (0/1) and `relic_data_<id>` (exact signed
`RelicInstance::data`) blocks, distinct from the legacy `r*` encoding. This
makes relic ownership and persistent counter/data separable for the counter
diagnostic without altering the deployed RICH interface.

## Schema / provenance

Versioned `e2c-v1` long format:
`seed,fight_index,boundary,room_type,encounter_id,<richState>,relic_has_*,
relic_data_*,won,finalFloor,endHp`. `richStateHeader()` already carries
`act,floor,ascension`; the prefix keeps only `room_type`/`encounter_id` (not in
the rich state) to avoid duplicate column names. The producer writes
`<out>.provenance.json` via the shared `writeTrainingProvenance` and enforces
the 128-seed cap through `tools/seed_guard.sh` (`e2cgen` registered, nSeeds=argv2).

## Status

Production source is untouched: with `e2cCapture=false` every E2c branch and
the hook are inert, so normal `bestbench` behavior is byte-identical. Smoke
(8 seeds, seeds 0-7, 30 sims) produced 130 matched pairs with zero quarantines
and clean RAW-to-POST deltas (gold rises, potionChance/cardRarityFactor change
only after RAW). No scientific verdict is recorded — E2c support/partial/negative
is determined only from the human-controlled production dataset.

## Corrected human production launcher

Do not run from a local checkout. The designated launcher supplies
`STS_GCP_RESEARCH_CONTEXT=sts-test` and wraps the remote command in
`tools/seed_guard.sh --gcp-research`:

```bash
python3 tools/agent/gcp_benchmark.py run -- \
  env STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 \
  STS_S3_PARTICLES=64 STS_S3_LIVE_VALID=1 \
  STS_VNET=models/v_combat_7k_tuned.txt STS_VNET_ALPHA=0.3 \
  STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
  STS_OOC_STRATEGIC_MARGIN=1.0 STS_OOC_STRATEGIC_REST=1 \
  STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
  STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 \
  STS_COLLECT_KEYS=0 STS_STOP_AFTER_ACT=3 \
  build/one_combat e2cgen 2000 1000 0 \
  build/e2c_raw_terminal_2000.csv 2000000
```

This was not launched during the implementation or correction sessions.
