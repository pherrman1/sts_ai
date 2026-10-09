# Counterfactual learning inventory and next discriminating probe

Inventory against campaign base `a4b3df35d170abba7860e8e854cc24cfd3579075`, 2026-10-08. Initial inventory used read-only source/artifact inspection and new prepared exports. Subsequent authorized source replay/selection is documented in `targeted_rest_preflight_631f_parity.json` and the targeted selection receipts. No model training or protected TEST numerical row access has occurred.

## Reusable assets and limits

| Asset | Observed identity/state | Admissible use |
|---|---|---|
| #434 GEN=2 producer | `apps/one_combat/combat_datasets.cpp`, `oocCounterfactualPilotGen`; current CLI inspected | Fresh canary after reviewed fair continuation freeze |
| Existing GEN=2 data | No `*.labels.csv` found by filename inventory in `Documents/sts`, `sts_sweep`, `/tmp`, `.codex/worktrees`, or `.claude` | No local reusable corpus established; remote locations were not contacted |
| #334 mixed corpus | `/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/a2a-scale-1024-extra512-8175c9dc-20261002/corpus-mixed-1024.json`; SHA256 `ae56f9633ce8da8a72e341978d707c9f145c1f1b6479afa438067af5570dfa00`; 1024 sources `13001000..13002023`, TRAIN/VALIDATION/TEST 696/155/173 | Historical TRAIN/VALIDATION discovery only; TEST stays closed. Producers `1e93bd66...` and `06657471...`, different mechanics/teacher from campaign |
| E1 P0/F1/F2 | Nine checkpoints under `/home/philippherrmann/Documents/sts/artifacts/vwin-refresh-334/e1-focal-20261007-36b5b14f/`; all nine loaded and produced finite predictions on 64 TRAIN rows | Public-queue-free inference candidates; historical training continuation may itself consume hidden queues, so not a current fair teacher or qualification |
| E1 report | SHA256 `1f9e5bcb37332f37369806e53772f941fc031584140c2dba12efa6192fe9e524`; historical `E1_INCONCLUSIVE` | Do not repeat the same focal retrain as tonight's main experiment; reuse checkpoints |
| #418 Path B corpus | `/home/philippherrmann/Documents/sts/wt-ctm-pathb/build/ctm-pathb-corpus/index-full.json`; SHA256 `d8747979f4d4a839c498bf44f59d595f463cdc46f973dad67b8f11f4a4acd8d8`; producer `1e1bdc097116ed6999e498f1645fb27326e52c1d`, binary `4f8587ac0efd0d808a1b783020f99a4a4232828c472e201f047005184bb1d47a` | Existing collection: 700 units, 575925 rows across ordinary/forced scopes; no duplicate full retrain warranted |
| #418 jobs/outputs | No active `one_combat`, counterfactual, CTM or Python training process observed in process snapshot; preserved near-full-gate PID files 221542/220764 had no live process. No new retrained checkpoint located in inspected Path B `selfplay/models`, build outputs or standard runs tree | This is local observation, not proof remote owners have no jobs. Preserved near-full-input comparison receipts exist; no retrain qualification inferred |

CTM Path B row counts from metadata: ordinary 534638, Ritual/Writhing 8769, high-maxHP 2593, Lizard/Fairy 15007, Lizard/Brew 14918. The index records seven stalled ordinary source seeds; `quarantined_seeds=0` does not erase these. No CTM numerical corpus rows or TEST-state files were opened. Existing comparison metadata were inspected only for input-generation status.

Known source ranges: #334 `13001000..13002023`; #418 ordinary `51000000..51024999`; forced scopes `52000000..52000399`, `52001000..52001099`, `52002000..52002599`, `52003000..52003599`; historical OOC pilot plan `54000000..54000031`. They do not overlap campaign reserved `610080000..610085999`. This is an explicit identified-artifact check, not a claim every unlocated historical run is catalogued.

## Existing model exports prepared

Run `export_public_models.py` using campaign `.venv`. It checks the frozen #334 index, hashes the selected TRAIN component/table, uses its first 64 rich rows, loads every E1 checkpoint, checks its 457-name order and absence of `nextEliteId,nextFight0,nextFight1,nextFight2`, and exports fixed seed-zero candidates. No validation selection, training, or TEST row access occurs.

Ignored output directory: `build/overnight_20261008/learning/public-e1-export/`.

| Candidate | Source checkpoint SHA256 | Compact export SHA256 | XGBoost versus Python compact max absolute error |
|---|---|---|---|
| P0-s0 | `ed8d95dcb93469cd4383d072c29ab5c21d268193f70e0348ab2f2a7c8f1d9de5` | `3189c51ae352740e02a3f15cb691ca6e80324d88a6583c094ca81bae91c59ab0` | 1.2080e-7 |
| F2-s0 | `271166525f945e8834844a91e1bb17e4502deb6c7867934ba07137f159a7bd1e` | `8955d513fbd152c40d112604bb30c7da16ac0ff7b3dd1bf72717d2308bd83935` | 1.0508e-7 |

Native binary equivalence **passed** under reviewed source736d on the same 64 TRAIN rows: P0 maximum absolute error `1.2124e-7`, F2 `1.0470e-7`; tolerance `1e-5`. See `native_export_parity_receipt.json`. A first read-only fixture attempt encountered the native CSV parser's CRLF header limitation; its failed log was preserved and LF fixtures succeeded in a fresh `native-e1-parity-736d-v2` directory. `STS_WIN_NET=PATH` is already supported; native floor loading is hardcoded to `models/v_rich_trees.txt`. Replacing only win does not repair the card/shop/remove floor fallback. Both exports predict probability, not floor units, so a floor substitution also changes the objective/scale and invalidates inherited floor margins. The 457-feature E1 contract still retains potion/rarity counters; removing four queue features is not blanket proof of every information-boundary property.

## GEN=2 contract observations

- Hidden futures redraw **before** forced actions; sibling future identity hashes `(sourceSeed, decisionIdx, k)` and excludes option identity. The producer asserts preserved published screen and rich features except four hidden queue fields.
- `sampleNoncombatFuture` canonicalizes hidden pool order, redraws all RNG streams, rebuilds unseen encounter queues conditional on consumed prefixes, and preserves the visible current map/boss. This is appropriate machinery for hypothetical public rollouts, not permission to expose a realized hidden future.
- Option cap deduplicates identical card occurrences, keeps the chosen option plus skip/leave, and hashes remaining classes up to six. The manifest lacks the full uncapped option count, so exhaustive legal-action coverage is not established by a label file alone.
- `finalWon` is absolute run outcome. First-post-screen MAP features are per future, and first-boss outcomes/HP are diagnostics.
- `valid` currently requires a later MAP row. A terminal branch without MAP has `error=no_map_after_branch`; retain/count it and fail training eligibility rather than silently dropping terminal actions.
- The ordinary producer enforces V4 strategic gates at margin 1.0, rest-win off, fixed token hash, native floor/win loaded, no MCTS or experimental action gates. Fresh fair-baseline policy serialization must bind the new information treatment; historical runner scripts do not yet do so.

## Ranked hypotheses

| Rank/ID | Question and competing explanation | Smallest intervention/check | Cost and decision |
|---|---|---|---|
| 1 L1 | Do fair real continuations rank boss-relic/card choices differently from V4, or are apparent gains finite-K noise? | GEN=2 canary with disjoint selection/evaluation future halves; then 32 sources K8 only if cost fits | At most 192 branch runs first; contract/cost pass only, no quality claim. See `GEN2_PROTOCOL.md` |
| 2 L2 | Do historical public F2/P0 already separate useful actions, or did historical teacher/mechanics drift remove that signal? | Zero-training score probe on fresh GEN2 rows, average sampled post-action maps, judge independent futures | Seconds of CPU after labels exist; requires consistent source-level gain before full-run restricted gate |
| 3 L3 | Is public future marginalization itself the necessary baseline correction, and how much does it change choices? | Preserve existing floor units and average lawful hypothetical queues with deterministic public seeds | Coordinator-owned fair-baseline work; correctness and current-source win rate separate |
| 4 L4 | Is absolute-value training dominated by baseline survival rather than sibling discrimination? | One source-balanced within-decision XGBoost ranker on newly qualified labels, compared with absolute model | Do not train on four canary sources; after a useful tranche, estimated minutes at 4 threads, no GPU needed |
| 5 L5 | Does post-MAP variance, especially new boss-relic maps, swamp action signal? | Hold source/option fixed; contrast observed K variance and before/after MAP feature dispersion; average lawful maps | Analysis only after complete labels; increase futures only by a new frozen development rule |
| 6 L6 | Does a public small neural head beat the tree representation when action/context interactions dominate? | Small fixed MLP only if trees fail a named independently supported action class and prepared inputs exist | Deferred: no fresh corpus; GPU occupancy is not sufficient rationale; no duplicate CTM retrain |

The best next canary is L1, after the current baseline information boundary is repaired and independently reviewed. New data should use that fair continuation. Historical public checkpoints are useful prepared alternatives but cannot certify the fairness or strength of their original teacher.

Knowledge impact: campaign evidence only at this stage. No new gameplay result or maintained model qualification has been established.
