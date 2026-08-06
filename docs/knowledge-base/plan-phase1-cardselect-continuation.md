# Session continuation plan — Phase 1 (CARD_SELECT parity) completion

Date: 2026-08-05. Status: **COMPLETE (T1–T5 executed 2026-08-05; §113)** —
the plan's tasks ran as written, the issue-48 hypothesis was **falsified**,
and the follow-up bisect found the true cause: **the control S3 enumerator
skip-won battles at WARCRY/GAMBLE CARD_SELECT states**. The parity fix is
correct and is the new recommended baseline. Historical record of the
execution and the finding below; current instruction now lives in
`EXPERIMENTS.md` §113 and `evaluation/current-baselines.md`.

## 0. Execution summary (2026-08-05, §113)

- **T1** sync + parity PASS (local + GCP); model hashes verified; smoke OK.
- **T2** mode A/B (64 seeds @1k): `all` 43.8%, `single` 42.2%, `none` 42.2%
  vs control 56.3% — **no mode within ±2pp of control; the plan's promote
  rule had no winner**.
- **T3** S2-only bisect: **56.2% ≈ control — S2 change neutral** (control S2
  already enumerated the common Ironclad pools; its GAMBLE case emitted a
  valid empty subset, so it has no skip path).
- **Falsification:** a pickCount-capped single-select extension (experimental)
  recovered only to 46.9% (`single`)/43.8% (`none`) — the pool-widening story
  did not explain the gap.
- **Root cause (§113):** control S3's `enumerateActionsForNode` default branch
  emitted `SINGLE_CARD_SELECT 0..pickCount-1`; WarcryAction/GambleAction never
  set `pickCount`, so WARCRY/GAMBLE states produced **zero valid edges** →
  `have=false` → battle `break` with UNDECIDED outcome →
  `BattleContext::exitBattle` treated non-loss as victory (rewards + advance;
  a skipped act-3 boss recorded `PLAYER_VICTORY`). Instrumented
  (`STS_DEBUG_BATTLE_BREAKS`): 41 breaks/8 seeds; 164/256 seeds. Decisive A/B
  on the same control binary (8 seeds @1k): silent skip = **62.5%** win vs
  break→LOSS = **0.0%**.
- **Deployed:** canonical enumerator (issue 47, 0 breaks on 256 seeds @1k and
  @3k) + `BattleContext::exitBattle` UNDECIDED→PLAYER_LOSS guard.
- **Honest re-baseline (256 seeds, V4 gate stack):** honest control S3 =
  9.0% @1k; **canonical+fix = 36.3% @1k, 42.6% @3k** — the parity fix is
  +27.3pp over honest control; the §107/§111/§112 S3 numbers (60.2%/56.6%/
  56.3%) and all S3 arms of §99–§105 are **invalidated** (S2-based §99
  45.3% survives).
- Issues 47 + 48 closed; docs updated (decision log, EXPERIMENTS.md §113,
  combat-search.md, current-baselines.md); GCP tree re-synced.

## 1. Handoff state (verified at commit b48cb40)

- The exhaustive `cardselect_parity` test (all 20 `CardSelectTask` values × 3
  variants + 3 PLAYER_NORMAL states, ground truth = `isValidAction`) passes;
  deterministic. `apps/test.cpp::testCardSelectParity`.
- The canonical enumerator `search::Action::enumerateCardSelectActions`
  (`src/sim/search/Action.cpp`) now implements the full validity contract;
  Searcher2 and Searcher3 delegate to it. `STS_MULTISELECT_MODE=all|single|none`
  (default `all`) prunes the multi-select action space; pruned modes emit only
  valid actions (verified: zero "extra" mismatches).
- **Resolved (issue 48, closed):** the §112 "−17.2pp regression" was the
  control S3 battle-skip exploit (see §0); the canonical `all` enumerator is
  the deployment default and `single`/`none` are opt-in scale knobs.

## 2. Environment quickstart

- Repo on Windows: `C:\Users\pherrman\projects\sts_ai`; build inside WSL
  (Ubuntu) against the mounted path:
  `wsl bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai/build && cmake --build . -j 16"`
  (fresh clone: `git submodule update --init`, then `cmake -S . -B build`).
- Local checks: `./build/test cardselect_parity` (must PASS), plus the
  existing dispatcher smokes (`happy_flower`, `belief`, `drawpile`,
  `obs_identity`, `prune`, `seed_contract`).
- Benchmarks run on GCP `sts-test` (c4-highcpu-24, preemptible,
  europe-west3-c). `gcloud.cmd` lives at
  `C:\Program Files (x86)\Google\Cloud SDK\google-cloud-sdk\bin\gcloud.cmd`.
  Start it if terminated: `gcloud compute instances start sts-test
  --zone=europe-west3-c`. Working tree `/home/philippherrmann/sts_sweep` is a
  non-git rsync copy.
- **GCP tree is currently stale:** it has the CONTROL (original) S2/S3 and a
  canonical without the mode gate. Re-sync before any benchmark:
  `src/sim/search/Action.cpp`, `src/sim/search/BattleScumSearcher3.cpp`,
  `src/sim/search/BattleScumSearcher2.cpp`, `apps/test.cpp`.
- **PowerShell traps:** escape `$` for remote bash with `` `$ `` (or use
  single quotes); launch benchmarks detached (`setsid nohup ... < /dev/null &
  echo GO`) and poll separately — a foreground `&` job hangs the SSH channel.
- Model files must be hash-verified after every sync
  (`sha256sum build/v_rich_trees.txt build/v_win_trees.txt
  build/policy_trees_c.txt` vs the identities in
  `evaluation/current-baselines.md`: `3a3420…`, `fc52c1…`, `24793b…`,
  `05d809…`). Load messages in the log must show `native V_win`, `policy
  PUCT ON`, `fair-play`, `Searcher3 engine ON`, `S3 particles = 256`.

## 3. Task list (in order; each step → verify)

**Status: ALL COMPLETE (2026-08-05).** T1–T3 ran as written; T2's promote
rule had no winner because the "control" was skip-inflated; T4/T5 were
re-scoped by the §113 finding (see §0): the canonical `all` enumerator is
the deployment default (no mode change needed), the exitBattle guard is the
run-level fix, and the honest re-baseline replaced the §111/§107 pairing
references. Command blocks below are retained as historical execution
instructions.

### T1 — Sync and verify on GCP
1. Sync the four files above to `sts_sweep/tmp_sync/`, `cp` into the tree,
   rebuild `one_combat` (+ `unit-test`).
2. Run `./build/test cardselect_parity` on GCP → PASS.
3. Verify model hashes + a 4-seed smoke run (`bestbench 1000 4 0 126700`) that
   the log shows the expected load messages.

### T2 — Multi-select mode A/B (the regression fix decision)
Run three arms on seeds 126700–126763 (64), 1k sims/256 particles, §111 config
(from `EXPERIMENTS.md` §111/§112 setup; run from `/home/philippherrmann/sts_sweep`,
CWD matters for the relative model paths):

```
STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=256 \
STS_OOC_STRATEGIC_TOK_NN=/home/philippherrmann/sts_sweep/selfplay/models/ooc_strategic_tok_final.native \
STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
OMP_NUM_THREADS=24 setsid nohup ./build/one_combat bestbench 1000 64 0 126700 \
build/ms_single_1k_64.csv > build/ms_single_1k_64.log 2>&1 < /dev/null &
```
(three arms: `STS_MULTISELECT_MODE=all` (expected ≈ cand 28/64), `=single`,
`=none`).

Decision rule (pair against `build/control_1k_256.csv` rows 126700–126763,
36/64 = 56.3%): promote the best mode that is within ~±2pp of control, with
`single` preferred over `none` (it keeps real gambling/exhaust options
searchable). `single` = empty + each single card + whole hand (≤ n+2 actions).

### T3 — S2-only bisect (default binary impact)
Install `Action_new` + `S2_new` + CONTROL `BattleScumSearcher3.cpp`; rebuild;
run the same 64-seed @1k block. This measures whether the default (S2) binary
is regressed by the delegation (its GAMBLE/EXHAUST_MANY went from 1 bogus
action to full subsets). If it regresses too, the mode knob must also gate the
deployed default.

### T4 — Promote and re-gate
1. Set the promoted mode as the DEFAULT in `pushMultiSelectActions` (no env
   needed) — or keep `all` if the A/B says so, and record why.
2. 256-seed @1k run, pair against `build/gate_2026-08-05_margin_base1k.csv`
   (§111 reference, 56.6% — currently the only available @1k pairing file;
   `pt2_p64_s1k_both_256.csv` from the docs does not exist locally or on GCP).
3. 256-seed @3k run (~2–3 h) paired against
   `build/gate_2026-08-05_termlookahead_base.csv` (60.2%).
4. Success = within noise of control on both (win-rate deltas < ~5pp, and the
   recommended stack's headline is not degraded); the point of the fix is
   correctness for later phases, not a win-rate jump at A0.

### T5 — Close out
- Close issue 48 with the measured verdict; record §113 in `EXPERIMENTS.md`
  (full provenance: flags, hashes, seeds, CSVs, pairing); append a decision-log
  entry; update `architecture/combat-search.md` (remove "under A/B").
- Commit code + docs together (artifacts CSVs stay ignored, copy them to
  `build/` and reference paths).

## 4. Wider roadmap (later phases; benchmarks on GCP, GPU training deferred)

1. **Phase 2 — observation-keyed search + belief fix — EXECUTED 2026-08-05
   (§114, decision log `2026-08-05-phase2-observation-search.md`):**
   `CombatObservation` identity expanded (inputState + card-select context)
   — **neutral** on 256 seeds @1k (+1.2pp, noise), kept as a correctness
   fix; `Edge{action → child[obsHash]}` obs-keyed descent — **falsified**
   (tree grows linearly under particle determinization; floor 11 vs 33 at
   fixed budget; reverted); `belief.update` removed from `step()`, live
   updates only at the agent boundary (non-fair path, `g_s3Belief`-gated).
   Recommended stack unchanged. Next phase: Phase 3 below.
2. **Phase 3 — post-combat run utility — Stage 2 EXECUTED 2026-08-05
   (§116):** controlled paired benchmark of the TERM_WIN terminal-leaf
   bonus (forced Happy Flower both arms, stall telemetry, win-tree
   evaluator) — **null** on win rate (37.9% vs 37.5%) and stall behavior,
   **3.1x cost**; the bonus stays opt-in/off and is not promoted. Stage 3
   (counterfactual terminal-value model) **deferred**: the deployed win
   tree is counter-insensitive (§110), so no counter-aware leaf model
    exists to justify training. Issue 49 (TERM_WIN multithread crash,
    pre-existing) **fixed 2026-08-06** (lazy-init race; opt-in arm only). Next: Phase 4 below.
3. **Phase 4 — exact current-turn solver** (replace dead rough
   `isGuaranteedLethal`; `STS_EXACT_TURN=1`).
4. **Phase 5 — observation-fair strategic retrain** = **deferred (GPU
   training)**: remove `nextFight*`/`nextEliteId`/`bossId` features,
   resample hidden futures in counterfactuals, P(win) labels.
5. **Phase 6 — learned rollout policy** = deferred (needs Phases 1-2 and
   training).
6. **Phase 7 — matchup/route optionality**: research with falsification gates;
   all prior map work (M1/C1/M2, V6) was negative.
7. **Phase 8 — pro-disagreement suite**: design-only now; execution deferred.

Measurement discipline: paired seeds only; separate fair-A0 / oracle /
combat-only leaderboards; ≥2,000 seeds for near-100% claims; a 256-seed
paired gate costs ~2 min @1k and ~2–3 h @3k on `sts-test`.

## 5. Exit criteria for this session

T1–T5 complete: a mode decision recorded with paired evidence, S2 bisect
recorded, issue 48 closed, docs current, tree clean, GCP tree re-synced to the
new commit. The recommended configuration headline (60.2% @3k, 56.6% @1k
references) must be reproduced or its change measured and recorded before any
new claim.
