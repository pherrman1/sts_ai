# StS AI — Experiment Ledger

The experiment ledger is **chronological evidence**. It records every tried
modification, configuration, and measured result — positive, null, negative,
invalidated, and superseded.

Historical statements such as "best," "current," "deployed," or "running"
describe the state at that point in time unless later evidence says otherwise.

The 2026-08-22 Phase-1b Search-Age preregistration is recorded below in the
chronological ledger.

## Where to find current truth

- **Current baselines** — qualified executable configurations and benchmark
  numbers: [`docs/knowledge-base/evaluation/current-baselines.md`](docs/knowledge-base/evaluation/current-baselines.md)
- **Current research status** — active, parked, and closed research lines:
  [`docs/knowledge-base/evaluation/current-research.md`](docs/knowledge-base/evaluation/current-research.md)
- **Current research understanding** — topic-oriented maintained synthesis:
  [`docs/knowledge-base/research/README.md`](docs/knowledge-base/research/README.md)
- **Current architecture** — implementation contracts:
  [`docs/knowledge-base/architecture/`](docs/knowledge-base/architecture/)
- **Session history** — historical session narratives are retained only in Git history when needed for provenance.

## Reading rules

1. **Project-fair and known-RNG results are separate regimes** and must never
   be compared as one progression.
2. **Experiment identifiers (§N)** are historical. Do not renumber them.
   Locate a section by searching the appropriate ledger shard.
3. **Missing flags, hashes, or artifacts remain unknown.** Do not reconstruct
   them from incomplete provenance.
4. **The `fairgen` mode does not set `STS_FAIR` or `STS_SEARCHER3`**; a
   historical entry that omits either flag does not establish the intended
   project-fair Searcher3 generation path.

## Ledger shards

Historical experiment content is stored in contiguous chronological shards
under [`docs/experiments/`](docs/experiments/). Each shard is a frozen slice
(except the current append target). The original order is unchanged.

| Shard | Coverage | Status |
| --- | --- | --- |
| [`ledger-01.md`](docs/experiments/ledger-01.md) | Current findings summary (2026-08-08) through §27 rich fair value net (2026-07-15) | FROZEN |
| [`ledger-02.md`](docs/experiments/ledger-02.md) | §28 Fair-play FULL-RUN validation through §66 Checkpointed combat-strength policy | FROZEN |
| [`ledger-03.md`](docs/experiments/ledger-03.md) | §67 Checkpoint-oracle distilled OOC action NN through §96 Wave A1/B sweep Q_win | FROZEN |
| [`ledger-04.md`](docs/experiments/ledger-04.md) | §97 Combat value net under the gate stack through §116 Phase 3 Stage 2 TERM_WIN | FROZEN |
| [`ledger-05.md`](docs/experiments/ledger-05.md) | §117 Searcher2 rollout-usage diagnostic through §135 Leaf-state diagnostic infrastructure | FROZEN |
| [`ledger-06.md`](docs/experiments/ledger-06.md) | §135a Leaf-state diagnostics gate-matching through 2026-10-08 §397, including §397 synthetic Silver corpus gates (learned leaf fails, root prior bonus passes offline), §396 E3 counterfactual OOC tranche (card-reward criterion negative, boss relics priced), §394 E1 focal retrain of the #334 X2 family (card-reward selection gain inconclusive), §393 #347 uniform-prior OOC MCTS with chest and relic rules (18/32, descriptive), §392 #347 prior cost on the R seeds (uniform prior 22/32 vs 9/32, root-by-Q no change; inconclusive), §391 OOC MCTS boss-rollout leaf pilot (negative, 9/32), §388 #347 boss-preparation R-match (flat10k vs MCTS boss entries under fixed 10k Silver: PREPARATION_HEADROOM_SIGNAL), §390 #347 chest-rule and campfire-fallback counterfactual (inconclusive; MCTS still leaves chest relics), §389 #347 OOC divergence on the #428 R seeds (OOC MCTS skips treasure chests and rests instead of smithing, prior-driven), §384 live OOC MCTS on vs off pilot (MCTS_WORSE, −21.9 pp on 128 pairs), §387 #347 boss-entry 10k vs 40k rescue on #417 sources (inconclusive, mixed), §381 frozen minimal active Lizard CTM qualification (inconclusive, rare-event floor; 2026-09-25 run), §380 OOC leaf `v_win` preparation profile (state copy removed; 2026-09-26 run), §379 frozen X2-B native win model deployment qualification (default off), §378 #397 MLP follow-up (no family adopted; relic history worth re-testing), §§375–376 #397 rule-derived public probabilities (none adopted), §374 #397 public-history families (no family adopted), §373 #397 reachable rich card domain (no model-input change), §371 #397 `v_win` information-boundary audit (hidden-future ablation inconclusive), §377 learned Silver stopping v3 live promotion run (PROMOTE_learned on 1,024 pairs; boss variants no better), §372 learned Silver stopping v2 (fresh confirmation pass against #199 with a lock-only arm, default off), §370 learned Silver stopping (replay A/B pass against #199, default off), §369 #400 Silver search-parameter screen (adaptive constants not justified), §367 OOC MCTS equivalent-outcome merging (inconclusive 128-seed A/B), §365 invalid active-Lizard DeepSets/Brew integration canary, §361 OOC MCTS reroot-opportunity measurement, §362 contextual V4 prototype parity and runtime rejection, §363 mechanical-q Lizard archived screen and current-main transfer, §364 fresh native Stage-C qualification, §360 native Silver hot-path profile and live-only action-queue copy, §359 Silver root selection and useless-block census, §358 OOC branching and floor-runtime profile, §357 native Silver endpoint/tree-depth descriptive profile, §355 native equivalent-copy reroot and §356 retrained contextual semantic-prior qualification, §354 native Silver one-action-root bypass, §353 `v_win` terminal-pricing audit and post-review descriptive additions, §§351–352 post-correction singleton reroot replay and updated current-main hard64 comparison, §350 native Silver rollout-profile rejection, §349 Silver rollout-cost A/B screen, §348 native Silver 128-seed gate, §§343–347 active Lizard Tail CTM/rescue and B1 support-domain evidence, §340 Silver handoff timing and adaptive 128-seed baseline, §§341–342 V4 policy-prior cost screen and DeepSets CTM with Entropic Brew fallback, §338 potion specialist, §339 potion-pooled-blind DeepSets screen, plus OOC CTM final-token optimization, §336 forced DeepSets timing smoke, §337 PR 295 DeepSets encoder reuse, Silver prior v1 LOCKED_TEST confirmation, frozen learned-prior root-PUCT replay screen, and pre-review online integration smoke | **CURRENT** — append here |

## Appending new experiments

New experimental results append to the **CURRENT** shard
([`ledger-06.md`](docs/experiments/ledger-06.md)).

When it becomes too large:
1. Mark it FROZEN in this index.
2. Create `ledger-07.md`.
3. Update the index table and mark the new shard CURRENT.

## Lossless guarantee

The historical content of the old monolithic `EXPERIMENTS.md` is preserved
byte-identically across the six ledger shards. Concatenating `ledger-01.md`
through `ledger-06.md` reproduces the original historical content from line 30
onward exactly.

## Previous conventions (historical)

**Fixed setup unless noted:** Ironclad, ascension 0, seeds `0..N-1`, 8 threads
(OpenMP). Combat is MCTS via the built-in `BattleScumSearcher2` (a
*known-RNG* solver — rollouts see the real upcoming draws, so numbers are an
optimistic upper bound, not fair-play). Out-of-combat decisions use
`ScumSearchAgent2`'s heuristic policies unless the experiment replaces one.
All harness code is in `apps/one_combat.cpp`.

Metrics: **win%** (normally reached and beat the Act 3 boss; all-key runs can
continue to Act 4), **avg_floor** (how deep it got), **avg_hp_end**, and
compute. Despite its label, `bestBench` **cpu_sec/run** is mean per-run
steady-clock elapsed time; **wall** is the outer benchmark wall time.
