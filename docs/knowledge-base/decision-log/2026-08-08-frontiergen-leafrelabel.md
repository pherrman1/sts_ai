# 2026-08-08 — Frontier-leaf corpus + empirical relabeling (frontiergen/leafrelabel): restorable BattleContext snapshots at all three S3 frontier sites

Date: 2026-08-08
Session/task: Implement phases 2-3-4 of the plan "Combat-value targets"
(`.ai/20260808-120025/plan.json`): capture Searcher3 frontier-leaf states with
restorable binary `BattleContext` snapshots (`frontiergen`), relabel them with
empirical terminal-outcome distributions from fresh high-budget searches
(`leafrelabel`), and add the phase-4 sibling-ranking analysis scaffold
(`tools/leaf_ranking.py --frontier`).

## Decision

1. **Visible-state-only binary serializer** — `include/combat/BattleContextBinary.h`
   (`sts::serializeBattleContext` / `deserializeBattleContext`): versioned
   (magic `STSBC` + version 1 + total size, little-endian field groups), covers
   the 6 RNG streams, Player (incl. statusMap/relicBits/counters), Monsters
   (per-monster statuses + `moveHistory` + MonsterGroup bits), Cards
   (hand/piles/stasis + counters; `limbo` skipped), Potions, and Misc
   (ascension/outcome/inputState/cardSelectInfo/turn/floorNum/encounter/seed).
   It DELIBERATELY skips the transient execution state (ActionQueue, CardQueue,
   curCardQueueItem, endTurnQueued, turnHasEnded, skipMonsterTurn,
   monsterTurnIdx, haveUsedDiscoveryAction, undefinedBehaviorEvoked, loopCount,
   energyWasted, cardsDrawn, miscBits). The round-trip contract is
   `combatExtractFeatures(original) == combatExtractFeatures(restored)` plus
   RNG-stream equality, pinned by the new `battlecontext_roundtrip` unit-test
   subcommand (registered in CTest).
2. **Hook at all three frontier sites, gated to frontiergen** — the
   leaf-expansion blend site (frontierType 0) always fires when
   `search::g_onS3LeafQuery` is set; the fair illegal-stored-edge rollout
   fallback (frontierType 1) and the depth-cap direct eval (frontierType 2,
   `rolloutSteps=0`) fire ONLY under the new `search::g_s3LeafQueryAllSites`
   flag (default false), which only `frontiergen` sets. `S3LeafDiagnostic`
   gained `rolloutSteps` + `frontierType`. Consequence: leafdiag/leafref/
   rollouttrace keep their historical single-site corpus byte-identical
   (review fix: the earlier three-site version silently changed the leafdiag
   reservoir composition).
3. **`one_combat frontiergen NSEEDS SIMS ASC OUTFILE_CSV [SEEDOFFSET] [STAMP]`**
   forces the deployed fair-S3 regime (`STS_FAIR=1 STS_SEARCHER3=1
   STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_LIVE_VALID=1`), writes
   `OUTFILE_CSV[_STAMP].csv` + `.bin` (flat 4-byte-LEN + blob concatenation),
   samples via 11 per-stratum reservoirs (10 leafdiag strata + 1 boss-only
   stratum; capacity `STS_FRONTIERGEN_PER_STRATUM` default 200), dedups by
   obsHash per seed at capture time (first kept, duplicateCount incremented)
   AND corpus-wide at flush time under the critical section (a visible state
   already written by an earlier-flushed seed is dropped without
   re-serialization and counted in the run summary — the corpus holds each
   visible state at most once; parent marker rows are NOT deduped because
   each decision needs its own parent for the sibling pass), computes root
   policy entropy at search-complete, and ALSO serializes each search's ROOT
   state (parent marker rows, frontierType=-1) for the sibling pass.
   `binaryOffset` points at the blob DATA (after the 4-byte length prefix).
4. **`one_combat leafrelabel`** — `evaluateTerminal` made virtual;
   `TerminalRecordingSearcher` records (won, endHp) per terminal eval
   (rollout ends + terminal-in-tree + terminal direct evals). The CSV
   self-documents the denominator: `totalTerminals` counts ONLY terminal
   evals and a `nonTerminal` column (= budget − totalTerminals, clamped at 0)
   reports sims that ended without a terminal eval (prune-as-dead
   backpropagations, non-terminal depth-cap/rollout-cap evals) — so
   totalTerminals need not equal the sim budget. Sibling pass enumerates the
   searcher's OWN action contract (`search::enumerateActionsForNode`, which
   INCLUDES potion actions; the app-level `legalActions` helper omits potions
   and would under-cover the phase-4 ranking set), uses ONE Belief + CRN
   particle set built from the parent visible state (`installSharedParticles`,
   partial CRN like leafref) at a separate sibling budget; children deduped
   by visibleHash; terminal children labeled directly. Output order is
   deterministic (per-leaf-index buffering), so two runs on identical inputs
   are byte-identical (verified).
5. **`tools/leaf_ranking.py --frontier`** — groups sibling rows by
   (seed, fightIdx, decIdx, leafObsHash) and ranks the deployed leaf model's
   `modelPred` column (PVNet `leafValue` if loaded, else vnet prediction)
   against the teacher pWin: pairwise accuracy / top-1 / Spearman / regret,
   stratified, deterministic bootstrap CIs. Brier/ECE only with a
   probability-scale `--prob-col` (the raw model values are on the endHp /
   50+HP scale, so Brier/ECE are not meaningful without a calibrated
   probability column).

## Rationale

- **Inference** — a full-state serializer is unnecessary: the frontier sites
  fire only at PLAYER_NORMAL / CARD_SELECT decision states where the
  ActionQueue/CardQueue are empty and the transient flags are consumed
  (`monsterTurnIdx >= monsterCount` at decision points, so its default of 6 on
  restore is behaviorally correct). The visible state + RNG streams are all
  that a fresh high-budget search needs, and they are exactly what
  `combatExtractFeatures` (the round-trip contract) reads.
- **Inference** — `evaluateTerminal` virtual dispatch is the least invasive
  way to record per-sim terminal outcomes: `step()` and `evaluateLeaf` already
  funnel every terminal evaluation through it, and the override delegates to
  the base so the search is behavior-identical.
- **Inference** — writing parent-state blobs into the same .bin (indexed by
  marker CSV rows, frontierType=-1) keeps the frontiergen artifact self-
  contained: leafrelabel needs exactly the two files the verification passes.
- **Inference** — per-seed buffering of CSV rows (written at seed end) is
  required because duplicateCount for an obsHash can be incremented by a
  later decision; blob offsets are final at write time, so the .bin is written
  incrementally under the critical section while the CSV is finalized per seed.
- The regime forcing (S3 −belief −chain + live-valid) matches the deployed
  §123 recommendation and is printed in the banner; if the recommendation
  changes, frontiergen/leafrelabel must be updated to match (documented in the
  KB).

## Alternatives considered

- Serializing the full `BattleContext` including ActionQueue/CardQueue —
  rejected: std::function-based actions are not serializable, and the queues
  are empty at every frontier site.
- Firing the hook at all three sites unconditionally — rejected after review:
  it silently changed the leafdiag reservoir composition (illegal-fallback
  and depth-cap leaves mixed into every stratum with no discriminator
  column); gated behind `search::g_s3LeafQueryAllSites` (frontiergen-only)
  instead, restoring leafdiag/leafref/rollouttrace to the historical
  single-site corpus.
- Per-seed-only obsHash dedup — rejected after review: identical visible
  states reached in different seeds were re-serialized and over-represented
  common early-game states; corpus-wide dedup at flush time (under the
  critical section) keeps each visible state at most once per run.
- App-level `legalActions()` for the sibling pass — rejected after review:
  it omits potion actions while the searcher's own `enumerateActionsForNode`
  includes them; the sibling set now matches the searcher contract so the
  phase-4 ranking covers the full action set.
- A separate parent-state bin file — rejected: the verification contract
  passes exactly one CSV + one bin to leafrelabel; marker rows keep the
  artifact self-contained.
- Making `evaluateTerminal` virtual vs adding a terminal-outcome hook —
  chosen virtual: the recording subclass is entirely app-side
  (`apps/one_combat.cpp`), no searcher instrumentation beyond the virtual.
- Per-particle outcome breakdown (`STS_LEAFRELABEL_PARTICLE_BREAKDOWN`) —
  deferred: the particle id is internal to `step()`; the plan marks the
  column optional.
- Stratum scheme — the plan's "extra boss-only stratum" is implemented as an
  11th reservoir that boss leaves may fill in addition to their natural
  hpFrac x difficulty stratum (boss rooms are difficulty 2 in the 3x3 grid),
  documented in the KB; the CSV has no stratum column (strata are sampling
  controls only).

## Evidence

- Round trip: `./build/test battlecontext_roundtrip` PASS; `ctest --test-dir
  build --output-on-failure` 9/9 PASS.
- Smoke: `frontiergen 8 300 0 build/frontier_smoke.csv 0 smoke` → 963 CSV
  rows (828 leaf rows + 135 parent rows), 99 rows with duplicateCount>0, all
  11 strata filled, 0 cross-seed duplicates dropped (8 fresh seeds at 300
  sims rarely reach identical visible states); `leafrelabel ... 5000 5 16` →
  5 leaf rows (totalTerminals == 5000, nonTerminal 0) + 15 sibling rows
  (totalTerminals == 3000, nonTerminal 0), byte-identical across two runs.
- `tools/leaf_ranking.py --self-test` PASS; `--frontier` smoke runs
  (pairwiseAcc 0.667 / top1 0.000 / Spearman 0.5 / regret 0.001, illustrative
  on 5 groups).
- leafdiag/leafref unchanged after the gating fix: `leafdiag 4 300 0` → 1710
  rows with the unchanged schema; `leafref ... 3000 4 0 300` re-captured
  1710/1710 recorded leaves (no re-capture WARNING).
- Artifacts: `build/frontier_smoke_smoke.{csv,bin}`, `build/leaf_smoke*.csv`,
  `build/sibling_smoke*.csv`, `build/ld_smoke.csv`, `build/ld_ref*.csv`
  (disposable local smokes).

## Status

Implemented, locally smoke-verified. The full phase-3 batch (500-1000 leaves
@10k sims, GCP-parallel) and the phase-4 pre-registered verdict gate (top-1 ≥
80% + Spearman ≥ 0.7) await the batch corpus. KB:
`docs/knowledge-base/architecture/combat-search.md` ("Frontier-leaf corpus
(frontiergen / leafrelabel, 2026-08-08)"). EXPERIMENTS.md §136.
