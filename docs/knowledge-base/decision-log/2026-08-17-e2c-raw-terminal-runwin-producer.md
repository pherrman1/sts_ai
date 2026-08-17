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
  STS_S3_PARTICLES=64 STS_LIVE_VALID=1 \
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

## Current-main integration and missingness correction

- Merged current `origin/main` at `280a7845ccad854d209268b03c76c7c8fa278c07`
  into the E2c branch with a normal merge (`3f8dd57`). The Phase-1b
  `particle_leaf_probe` and `particle_posterior_probe` changes are preserved;
  `tools/seed_guard.sh` retains both registrations plus `e2cgen`.
- Deterministic replay of the three RAW-only elite cases from the earlier smoke:
  - seed 0, fight 4, encounter 16, Act 1 floor 10: reward relic
    `BOTTLED_FLAME` (enum 94);
  - seed 1, fight 16, encounter 34, Act 2 floor 32: reward relic
    `BOTTLED_LIGHTNING` (enum 95);
  - seed 3, fight 13, encounter 36, Act 2 floor 30: reward relic
    `BOTTLED_LIGHTNING` (enum 95).
  In every case the reward screen had one relic and one pending combat card
  reward. Obtaining the bottled relic opened `CARD_SELECT` for bottling; the
  subsequent control transition left the reward flow while `cardRewardCount`
  remained one. POST therefore could not be captured. This is reward-dependent
  missingness, not a key-policy failure.
- E2c now uses the fallback contract and bumps the analyzer schema to `e2c-v2`:
  every valid survived RAW row is retained for primary RAW arms; matched
  `B2-raw-paired`/`T-raw-paired` and `B2-post`/`T-post` arms use complete pairs
  only. Retention and reward-information gap use the same complete pair set.
  Pair completeness is reported overall, by room type, and by eventual outcome.
- Accounting is accumulated only after `trainingRunValid()` accepts the run;
  invalid runs cannot inflate dataset counts. Incomplete valid-run pairs remain
  explicit `raw_only`/`post_only` accounting and are not silently treated as
  complete.
- Production documentation uses `STS_LIVE_VALID=1` (not the stale
  `STS_S3_LIVE_VALID`) and does not add a separate strategic-card flag.
- No scientific verdict is recorded.

## Final merged-v2 smoke facts (no scientific verdict)

On merged current-main branch `3f8dd57036968711bee84de2728620ce8390f814`,
corrected smoke (`e2c_v2_smoke.csv`, 8 seeds 0-7, 30 sims) produced valid-run
accounting:

```text
MONSTER eligible=98 raw=98 post=98 pairs=98 raw_only=0 post_only=0
ELITE   eligible=30 raw=30 post=27 pairs=27 raw_only=3 post_only=0
BOSS    eligible=9  raw=9  post=9  pairs=9  raw_only=0 post_only=0
```

The three incomplete valid-run pairs are the bottled-relic cases documented
above. The v2 analyzer retained 137 valid RAW rows and 134 complete pairs;
pair completeness was 97.81% overall, MONSTER 100%, ELITE 90%, BOSS 100%;
loss rows were 97.30% complete and win rows 100% complete. Primary RAW arms
use all valid RAW rows; paired arms use complete pairs only. No scientific
verdict is inferred from this smoke.

## Analyzer correction (commit after current-main merge)

The analyzer now uses all valid RAW rows for the primary E2c checks:
`T-raw` vs `B2-raw` direction, ECE, AUC/Brier, and the seed-bootstrap
log-loss CI. Matched retention remains complete-case only:
`B2-raw-paired`/`T-raw-paired` versus `B2-post`/`T-post`. Both
`all_raw_gain` and `paired_raw_gain` are reported.

Calibration uses each arm's own aligned labels. Validation artifacts are split
into `validation_predictions_raw.npz` and `validation_predictions_paired.npz`,
each with internally matching seed/fight IDs, labels, contiguous run IDs, and
prediction arrays. POST-only rows are rejected as a producer-contract violation.
The counter diagnostic uses the all-RAW T model's relic-data feature gain and
all-RAW bootstrap CI. Validation reporting separates raw rows/seeds from paired
rows/seeds. No scientific verdict is recorded.
