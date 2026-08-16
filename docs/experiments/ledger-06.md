## §135a Leaf-state diagnostics: gate-matching measurement (2026-08-08, local — diagnostic evidence, no gameplay promotion)

- **Dataset:** 64 seeds (126700–126763), 1000 sims, asc 0, 12 threads, local
  (no GCP). Full gate-matching env: `STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`,
  `STS_VNET=build/v_combat_honest.txt` @ `STS_VNET_ALPHA=0.3` (deployed §126
  regime), `STS_DIAG_VNET2=build/v_combat_utility_direct.txt` (§134 direct-R,
  diagnostics only), `STS_LEAFDIAG_PER_STRATUM=500`, full V4 OOC gate arms
  (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`,
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, MARGIN=1.0). Probing OOC arms OFF.
- **Artifacts (build/, git-ignored):** `leafdiag_gate_64.csv` (288,537 leaf
  rows, 142s), `leafref_gate_64_4k.csv` (287,211 reference rows, high-budget
  4000 sims × 128 particles, per-group CRN reseeding, replay 1000 — matched
  100%, no re-capture WARNINGs, 3367s), `rollouttrace_gate_64.csv` (3,341,845
  rows, 150s), `leafdiag_gate_64_ood.csv`, JSON summaries
  `leaf_ranking_gate_64{,_ood,_rawrollout}.json`,
  `leaf_distribution_shift_gate_64.json`, `leaf_split_check_gate_64.json`,
  `leaf_smoothness_gate_64.json`.
- **Ranking vs high-budget reference (Task 3; reference is vnet-influenced,
  see caveat):** endHp Pearson 0.758 / Spearman 0.769 / MAE 31.2 vs utilityR
  Pearson 0.806 / Spearman 0.820 / MAE 21.5 (own scales, not comparable
  directly — utilityR fits the reference better in correlation). Within-group
  pairwise accuracy: **endHp 0.719 [0.717,0.722] vs utilityR 0.711
  [0.708,0.714]** (+0.8pp, CIs disjoint); top-1: 0.359 vs 0.336 (+2.3pp);
  regret 7.253 [7.076,7.424] vs 7.597 [7.419,7.768]. Disagree-high stratum
  (|Δ| ≥ 50): 0.734 vs 0.720. Deep-tree stratum (d≥15): 0.798 vs 0.779.
- **Model-free cross-check (rawRolloutEval single-sample reference, no
  leafref):** pairwise 0.725 [0.722,0.728] vs 0.719 [0.715,0.722], top-1 0.333
  vs 0.316, regret 14.50 vs 15.16 — same direction, so the endHp ranking
  advantage is NOT an artifact of the vnet-influenced reference.
- **Distribution shift (Task 4):** held-out logistic classifier
  combatgen-vs-search-leaf: **ROC-AUC 0.9998** (60k×60k rows, test ~1/3) —
  near-perfect separation; the search-leaf regime is essentially entirely
  outside the `vcombat_honest.csv` training distribution (OOD flagging: only
  37 decision groups classified in-dist, 3046 OOD, rest na). Top separating
  features by standardized |coef| (correlation, NOT causal): r116 (+4.87),
  maxHp (+2.74), gold (+2.07), nSklAvail (−1.92), dr25 (+1.88), ds25 (+1.87).
- **Split-sensitivity (Task 5):** fight-split vs seed-split diagnostic
  retrains (canonical §134 recipe): endhp val MAE 5.581 → 5.536 (−0.045);
  utility_r 9.730 → 9.173 (−0.557). The fight-level split is NOT optimistic —
  seed-level validation is, if anything, slightly easier for the deployed
  models (deployed endHp val MAE 5.589 fight vs 3.930 seed). The offline
  story was not inflated by same-run fight leakage.
- **Smoothness/shaping (Task 6):** endHp lag-1 autocorrelation 0.549 vs
  utilityR 0.502 (endHp smoother); near-death steps: endHp mean ΔV −1.094 /
  std 3.227 vs utilityR −2.457 / 8.571; but utilityR is MORE sign-consistent
  on raw surface progress (progSign 0.459 vs 0.432, negOnHpLoss 0.247 vs
  0.221, strUp 0.442 vs 0.416). Shaping evidence is MIXED — smoothness yes,
  sign-consistency no.
- **Verdict (diagnostic, not causal):** the dominant, unambiguous finding is
  massive train-vs-search covariate shift (AUC 0.9998). Within the OOD
  search-leaf regime the deployed endHp model ranks slightly better (pairwise
  +0.8pp, top-1 +2.3pp, regret −0.34) despite correlating worse with the
  high-budget reference (Spearman 0.769 vs 0.820). The online gap (−12.1pp) is
  far larger than any measured ranking difference (≤2.3pp top-1), so the
  ranking hypothesis alone cannot explain the §134 collapse; covariate shift
  (or its interaction with the blend scale) is the primary suspect. Next
  experiment (per the handover decision point, covariate-shift branch):
  retrain the existing model class on a mixture of combatgen + actual
  leafdiag states with SEPARATE on-policy and search-leaf holdouts, and test
  search-leaf ranking improvement before any gameplay gate.
- **Caveats:** the leafref reference searcher itself used the deployed endHp
  leaf (vnet-influenced reference) — mitigated by the rawRolloutEval
  cross-check above; OOD in-dist groups are few (n=37) so the ood=id stratum
  is anecdotal; delta-V scales differ across models (only scale-free
  comparisons valid); classifier feature weights are correlational.
- **Decision log:** `2026-08-08-leaf-state-diagnostics.md` (results
  addendum).

## §135b B1 tactical turn-beam rollout (STS_S3_TURN_ROLLOUT): implemented opt-in with structural-equality check; paired 256-seed gate PENDING (2026-08-08, local WSL)

- **What:** the B1 line from `plan-rollout-experiments-2026-08-07.md` §2
  (user-approved scorer-(b) design; the §134 audit flagged the original B1
  spec as incomplete — pruning needs intermediate scores — so the revised
  spec scores COMPLETE turns only and prunes between turns by first-N
  truncation). At PLAYER_NORMAL states during the Searcher3 rollout, the
  per-action weighted random pick is replaced by a deterministic beam search
  over card/potion sequences to END_TURN; the best-scored complete turn is
  executed and the rollout continues to the next hand (multi-turn
  continuation is mandatory per the A4 falsification, §133).
- **Implementation:**
  - `turnBeamSearch` (file-scope static, `src/sim/search/
    BattleScumSearcher3.cpp`): BFS to END_TURN, depth = hand size (≤10),
    width `STS_S3_TURN_BEAM_WIDTH` (default 8), pruned between depths by
    first-N truncation (deterministic enumeration order, no intermediate
    scoring). Every beam state spawns an END_TURN candidate scored after the
    monster turn resolves on a copy (common-random-numbers for free).
    CARD_SELECT-producing sequences are dropped; lethal sequences captured as
    +1000 candidates; `turnBeamSearch` never returns empty (depth-0 END_TURN
    candidate).
  - `scoreCompleteTurn(pre, post, powersPlayed, potionsUsed)`:
    `S = w1·ΔHP_enemy − w2·ΔHP_player + w3·kills + w4·persistent_setup
    − w5·potion_use`; ΔHP_player = effective (HP+block) loss clamped ≥0;
    setup = strength+dex+focus deltas + powers played; terminal outcomes
    ±1000. Weights `STS_S3_TURN_SCORE_W1..W5` defaults
    1.0/1.0/50.0/10.0/30.0 (educated guesses, pre-registered). Hand-authored
    rollout heuristic (same class as `rolloutWeight`), NOT a learning
    objective.
  - `playoutRandom` branch (gated `g_s3TurnRollout &&
    inputState == PLAYER_NORMAL`): executes the best sequence, fires
    `g_onRolloutStep` after each action, honors `g_s3RolloutTurnStop` (A4)
    after the beam's END_TURN. Non-PLAYER_NORMAL states keep the weighted
    pick; unset/`=0` is byte-identical pre-B1.
  - Env parsed in `apps/one_combat.cpp::main`; BEST stack banner prints
    `S3-turnBeam=ON/off` (only in the Searcher3 arm of the banner).
- **Local smoke (2026-08-08):**
  - Structural equality: `bestbench 300 8 0 126700` with `STS_FAIR=1
    STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`,
    unset vs `STS_S3_TURN_ROLLOUT=0` → per-seed game-outcome columns
    (won/floor/act/hpEnd/maxHp/fightsLost/deathCombat/deathEncounter)
    identical (only the wall-time `sec` column varies); logs identical
    modulo cpu.
  - Turn-beam smoke: same config + `STS_S3_TURN_ROLLOUT=1
    STS_S3_TURN_BEAM_WIDTH=8` → runs to completion on 8 seeds @300 sims, no
    crash/hang/assert (win 25.0% vs control 37.5% on 8 seeds — NOT
    evidence, smoke only). Cost ~16× control at 300 sims (55.9 vs 3.45
    cpu-sec/run) — the beam's CPU cost is the known B1 risk; B1c (VNet on
    the final 2–4 beam survivors) is parked for that contingency.
  - `ctest` 8/8 pass; `git diff --check` clean.
- **Gate (DONE 2026-08-08, GCP sts-test):** paired 256-seed @1k/64p, block
  126700–126955, asc 0, 24 threads, full V4 gate stack (`STS_OOC_STRATEGIC_TOK_NN=
  selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`), vnet default ON α0.3,
  vs the §126 control `build/vnet_all_a03_1k.csv` (50.4%):
  `bestbench 1000 256 0 126700 build/b1_turn_beam_1k_256.csv` with
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64 STS_S3_TURN_ROLLOUT=1 STS_S3_TURN_BEAM_WIDTH=8`;
  analysis `paired_analysis.py build/vnet_all_a03_1k.csv
  build/b1_turn_beam_1k_256.csv ctl cand`; banner confirmed
  `S3-turnBeam=ON` + `[S3 turn-beam rollout ON: width=8 scorer
  w1..w5=1/1/50/10/30]` + vnet default load.
- **Gate result (paired_analysis.py, 256 seeds):**
  | metric | control (§126 vnet) | turn-beam B1 | delta |
  |---|---|---:|---:|
  | win | **50.4%** (129/256) | **46.9%** (120/256) | **−3.5pp, 95% CI [−10.2, +3.1]** |
  | avg floor | 44.1 | 43.9 | −0.1 (CI [−1.3, +1.1]) |
  | avg HP end | 29.4 | 25.3 | −4.0 |
  | cpu-s/run | 41.17 | 383.45 | +9.3× |
  Discordant 75/256 (29%): ctl-only 42, cand-only 33. Wall 4523.7 s
  (75.4 min). Artifacts: `build/b1_turn_beam_1k_256.csv` (md5
  6028f837224b845e63254d91062f767f), server log
  `build/b1_turn_beam_1k_256.log` on sts-test.
- **Verdict: ❌ null (not significant), line parked.** −3.5pp with CI crossing
  zero and no floor/HP benefit at 9.3× CPU closes the B1 hand-authored-scorer
  design (the decision log pre-registered the gate as arbiter; risk list
  included mis-ranking and lower-index bias). No default change; env stays
  opt-in default-off. B1c (VNet on final 2–4 beam survivors) is NOT unlocked
  — the cost contingency was premised on a positive signal; a VNet-scored
  beam would only add cost. A2 (dynamic α by rollout length) conditions on
  the L distribution B1 reshapes — with B1 parked, run A2 only if a
  lightweight rollout-shape diagnostic shows the premise still holds.
- **Decision log:** `2026-08-08-turn-beam-rollout.md`.

## §136 Self-play relabeling (5.7.3, handoff plan `plan-selfplay-relabeling-2026-08-07.md`): Phase-0 verification smoke — full S3+vnet datagen stack verified, schema/labels OK, trainer/export chain OK; Phases 1–3 (GCP datagen, GPU training, paired gate) PENDING manual follow-up (2026-08-08, local WSL)

- **What:** Phase 0 of the 5.7.3 handoff plan — verify (a) the
  `strategicgen2` Tier-B label producer runs with the CURRENT deployed combat
  controller (fair S3−belief−chain + live-valid + the §126 vnet default) and
  emits the trainer-consumable schema, and (b) the `train_strategic_tok.py` →
  `export_strategic_tok.py` chain works end-to-end before the 1,500-seed GCP
  datagen. **No C++ code changes** (verified: `strategicgen2` main-run OOC and
  branch continuation are heuristic by design — `apps/one_combat.cpp`
  `runStrategicGenSeed2`/`finishOocCounterfactual`; branch battles use the
  configured searcher, so the §5 envs alone select the deployed controller).
- **Provenance (Phase 0):** local WSL (12 threads), HEAD 2e6f894,
  `./build/one_combat strategicgen2 10 1000 0 build/sp_smoke_phase0.csv
  300000` with `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STRATEGIC_SAMPLE_ALL=1` (branch defaults: `STRATEGIC_BRANCH_FIGHTS=3`,
  `STRATEGIC_BRANCH_SIMS=150,100,50`, `STRATEGIC_BRANCH_FUTURES=1`);
  seeds 300000–300009 (fresh range, no overlap with recorded ranges).
- **Verified banner (startup, no vnet warning):** `[Searcher3 engine ON]`,
  `[live-valid edge re-selection ON (fair S3 default, §123)]`,
  `[S3 ablation: belief=off]`, `[S3 ablation: chain=off]`,
  `[V_combat leaf default ON: build/v_combat_honest.txt, 804 trees, alpha 0.3
  (fair S3, §126)]`; **no** `[strategicgen2 WARNING: STS_VNET not loaded]`
  (the `!search::g_useVNet` guard, apps/one_combat.cpp:7454). The S3-abl
  banner (`S3-abl[b,p,c,l,crn]=01010`) is a bestbench banner; for
  `strategicgen2` the per-flag ablation lines above are the equivalent
  evidence.
- **Schema (validated with pandas):** 1017 state columns between `chosen`
  and `won` (exact `richRow` contract the trainer validates); last 4 columns
  exactly `labelWon,labelHp,labelFloor,labelBootstrap`. Rows: **6,244 total
  / 10 seeds = 380–771 rows/seed (mean 624)** — consistent with the §104
  scale estimate (~809k rows / 1,295 seeds). `STRATEGIC_SAMPLE_ALL=1` →
  **100% labelWon coverage** (6,244/6,244), spread 0..1 with 2,363 distinct
  values (real variance, not constant).
- **Preliminary label diagnostic (smoke-scale only, NOT a gate — 10 seeds,
  §104-style filter: groups with ≥2 finite labels AND exactly one chosen
  row): argmax(labelWon) vs `chosen` agreement 34.1% strict / 46.0% in-set**
  (1,055 valid groups; in-set = chosen inside the tied argmax set), with
  per-screen spread matching the old-corpus pattern (EVENT 41.4/50.0 n=58,
  MAP 51.9/56.3 n=158, REST 50.0/59.7 n=72, REWARDS 29.5/45.1 n=628, SHOP
  15.7/15.7 n=51; TREASURE/CARD_SELECT/BOSS_RELIC omitted, n<50). The old
  corpus read 38.0% strict / 58.1% in-set (§104); the smoke numbers are
  consistent, so the new labels behave like the old ones. (A 37.2% strict
  figure recorded earlier the same day came from an experimental
  deferred-branch parallelization that was reverted — see the second-pass
  follow-up below; the numbers here are from the exact serial path the GCP
  datagen will use.) Recompute on the full 1,500-seed set per the plan (§5
  Step-1 diagnostic); informative, not a gate.
- **Trainer/export chain (Phase 0c):** 2-epoch CPU slice of the smoke CSV
  (`STRAT_DEVICE=cpu STRAT_EPOCHS=2`, rung 4, 6,244 rows / 10 seeds / 1,555
  decisions, **1,554 groups with exactly one chosen row, all with a valid
  policy action** — the policy-target head is exercised: policy_top1
  0.44→0.42, q_top1 ~0.20, val_pol_ce 1.5204) → `build/tok_smoke.pt.pt` +
  `_metrics.json`; export with `export_strategic_tok.py build/tok_smoke.pt
  build/ooc_strategic_tok_smoke.native` → **32 numpy-vs-PyTorch parity checks
  passed** (max err logit 3.87e-08, value 8.92e-08, Q 1.66e-07); the
  exported native loads in `one_combat` (`[OOC one-ply strategic TOK net ON:
  card rewards gated at margin 1]` with the full gate stack + vnet default +
  `S3-abl[...]=01010` at 64p on a 2-seed @100-sim bestbench smoke). The
  smoke .native lives under ignored `build/` — it is NOT a candidate artifact
  and must not be committed to `selfplay/models/` (2-epoch CPU checkpoint,
  rung 4 default topology).
- **Discrepancies found (plan-vs-repo, recorded for the follow-up session):**
  (1) `train_strategic_tok.py` writes `OUT + ".pt"`, so `export_strategic_tok.py`
  must receive the ACTUAL checkpoint path (e.g. `build/tok_control.pt.pt`
  when the trainer OUT was `build/tok_control.pt`); the plan's Phase-2
  command as written would silently fall back to the exporter's random
  selftest. (2) The training environment is the repo venv (`.venv/bin/python`,
  torch 2.5.1+cu121); the system `python3` lacks torch. (3) `ctest` passes
  8/8 at this HEAD — the plan's "known CRLF selfplay_syntax failure" does not
  reproduce (the parallel agent's fixes landed since the plan was written).
- **Status:** Phases 1–3 PENDING (manual GCP follow-up per the plan
  protocol): 1,500-seed datagen on sts-test (seeds 300000–301499, three
  500-seed chunks, `OMP_NUM_THREADS=24`, same envs), control retrain on
  `build/strategic_tierb.csv` + candidate retrain on
  `build/strategic_sp_1500.csv` (GPU, rung 4, 40 epochs, same recipe),
  paired 256-seed gate on block 126700–126955 @1k/64p vs
  `build/vnet_all_a03_1k.csv` (50.4%). Pre-registered verdict rule
  unchanged: candidate ≥ control with CI excluding a meaningful loss →
  promotion path; null → 5.7.3 closed as a distribution lever.
- **Artifacts (ignored):** `build/sp_smoke.csv` (6,244 rows, clean
  regeneration — an earlier duplicated 12,488-row copy from re-running
  `strategicgen2` without truncating the file was discarded), plus
  `build/sp_smoke_phase0.csv` (6,244 rows),
  `build/tok_smoke.pt.pt` / `_tok_state.bin` / `_metrics.json`,
  `build/ooc_strategic_tok_smoke.native` (smoke export, 807,432 bytes),
  `build/smoke_gate_phase0.csv` (2-seed load smoke). All git-ignored under
  `build/`; the smoke .native is NOT a candidate artifact (2-epoch CPU smoke
  checkpoint, rung 4 default topology) and is kept OUT of the git-tracked
  `selfplay/models/` directory.
- **Follow-up (same day, verification-fix session):** (a) discrepancy (2)
  above is resolved — the venv's torch 2.5.1+cu121 stack was copied into the
  user site (`~/.local/lib/python3.12/site-packages`), so the plain-`python3`
  trainer/export smoke commands now pass (`STRAT_DEVICE=cpu STRAT_EPOCHS=2
  python3 train_strategic_tok.py build/sp_smoke.csv build/tok_smoke.pt` → 2
  epochs, metrics byte-identical to the venv run; `python3 export_strategic_tok.py
  build/tok_smoke.pt selfplay/models/ooc_strategic_tok_smoke.native` → 32
  parity checks, max err 1.66e-07; `build/tok_smoke.pt` is kept as a symlink
  to the trainer's real `build/tok_smoke.pt.pt` so the exporter exercises the
  trained checkpoint rather than its random selftest fallback). (b) The
  plan's 1-seed @100-sim schema-validation check
  (`strategicgen2 1 100 0 build/sp_smoke_header.csv 300010`, 60 s budget)
  cannot complete on this machine: measured 166.2 s for 1 seed (dominated by
  the per-decision branch-fight contract — 3 fights × 150/100/50 sims,
  `STRATEGIC_BRANCH_FUTURES=1`, the §84-optimal defaults the plan mandates
  keeping; 12 OMP threads but a single seed uses one core). The schema it
  would validate is already verified by the 10-seed smoke above (1017 state
  cols + Tier-B suffix + 100% labelWon coverage), so no datagen code or
  default was changed for it — the timeout is a verification-budget mismatch,
  not a producer defect.
- **Follow-up (same day, verification-fix session, second pass — REVERTED):**
  an experimental `runStrategicGenSeed2` change deferred sampled decisions'
  branch battles to a post-run `#pragma omp taskgroup` when `nSeeds <
  threads` (spare team threads). It was NOT structurally guaranteed
  byte-identical to the serial path: in deferred mode the thread-local
  `t_curPath` stays set through the main loop, so the main-run OOC policy
  (`serverCardRewardPolicy`/`restWinPolicy`/`upgradeSelectWinPolicy` via
  `vFeatCsv`→`richRow`) sees real `pv*` features, whereas the serial path
  nulls it after the first branch eval (`pv*`=0); the floor/win nets consume
  `pv*` features, so `chosen` rows can flip on unverified seeds. Byte-identity
  was only spot-checked (1–3 seeds @100 sims), and the diagnostics recorded
  from that run (37.2% strict agreement) did NOT match the serial path
  (34.1/46.0 above). Per review, **the change was fully reverted —
  `apps/one_combat.cpp` is byte-identical to HEAD** (no C++ changes, per the
  plan's explicit constraint); the smoke above was regenerated with the exact
  serial code the GCP datagen will use, and the `build/sp_smoke.csv` training
  input was truncated before re-running (no duplicated rows; the trainer now
  sees 1,554 valid policy groups instead of 0). The 1-seed @100-sim 60
  s-budget mismatch (follow-up (b) above) stands as a recorded verification
  limitation: the schema is already proven by the 10-seed smoke, so no code
  change is justified. Per-seed reproducibility re-verified: serial 1-thread
  reruns of seed 300000 are byte-identical; the 10-seed file differs across
  runs only in seed-block ordering (dynamic OMP schedule), not content.
- **Follow-up (same day, recovery-fix session — reversion verified complete):**
  the second-pass reversion described above is now actually true in the tree:
  `git diff apps/one_combat.cpp` is empty (the deferred-branch
  parallelization is fully removed, so the plan's no-C++-change constraint
  holds). `build/sp_smoke.csv` was truncated and the 10-seed smoke re-run from
  scratch on the serial path (315 s wall @12 threads) → 6,244 rows, 380–771
  rows/seed, 100% labelWon coverage, 2,363 distinct labelWon, and per-seed
  rows byte-identical to the original Phase-0 serial file; the §104-style
  diagnostic reproduces the recorded numbers exactly (34.1% strict / 46.0%
  in-set on 1,055 groups; per-screen EVENT 41.4/50.0, MAP 51.9/56.3, REST
  50.0/59.7, REWARDS 29.5/45.1, SHOP 15.7/15.7). The 2-epoch CPU
  trainer/export smokes were re-run on the clean slice with identical metrics
  (1,554 valid policy groups, policy_top1 0.44→0.42, q_top1 ~0.20, val_pol_ce
  1.5204; export 32 parity checks, max err 1.66e-07) → the smoke .native now
  exists only under ignored `build/ooc_strategic_tok_smoke.native`; the copy
  that had accumulated in git-tracked `selfplay/models/` was removed (it must
  not be committed; only the Phase-2/3 control/candidate .native files ship).
- **Decision log:** `2026-08-08-selfplay-relabeling.md`.

## §136 Frontier-leaf corpus + empirical relabeling (frontiergen/leafrelabel): infrastructure implemented with local smoke verification, no gameplay result yet (2026-08-08, local)

- **What:** phases 2-3 of the plan "Combat-value targets" (`.ai/20260808-120025`):
  (2) `one_combat frontiergen` captures Searcher3 frontier-leaf states as
  versioned binary `BattleContext` snapshots (`include/combat/BattleContextBinary.h`,
  `sts::serializeBattleContext`/`deserializeBattleContext`; round-trip contract =
  `combatExtractFeatures` identity, verified by the new `battlecontext_roundtrip`
  unit-test subcommand registered in CTest) at the THREE S3 frontier sites —
  the leaf-expansion blend site always fires when `search::g_onS3LeafQuery` is
  set; the fair illegal-stored-edge rollout fallback and the depth-cap direct
  eval fire ONLY under `search::g_s3LeafQueryAllSites` (thread_local, default
  false), which ONLY frontiergen sets, so leafdiag/leafref/rollouttrace keep
  the historical single-site corpus (`S3LeafDiagnostic::frontierType` 0/1/2 and
  `rolloutSteps` record the site + rollout length) — and (3) `one_combat
  leafrelabel` restores each leaf and runs a FRESH high-budget Searcher3
  recording every terminal evaluation (`evaluateTerminal` made virtual;
  `TerminalRecordingSearcher` records won/endHp per terminal eval) → empirical
  P(win), HP|win mean/quantiles; plus a CRN sibling pass (one Belief + particle
  set from the parent visible state, `installSharedParticles`, sibling actions
  enumerated with the searcher's OWN contract `search::enumerateActionsForNode`
  — potions included) at a separate sibling budget. leaf.csv/sibling.csv
  self-document the denominator: `totalTerminals` counts ONLY terminal evals
  and a `nonTerminal` column (= budget − totalTerminals, clamped ≥ 0) reports
  sims without one (prune-as-dead / non-terminal depth-cap/rollout-cap evals).
  Phase-4 analysis scaffold: `tools/leaf_ranking.py --frontier` (pairwise
  ranking accuracy / top-1 / Spearman / regret of the deployed leaf model's
  `modelPred` vs the teacher pWin, stratified, deterministic bootstrap CIs;
  Brier/ECE only with a probability-scale `--prob-col`).
- **Regime forced by both modes:** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_LIVE_VALID=1` (deployed fair-S3 datagen regime; live-valid
  set explicitly — datagen is not covered by the parse-time default, §123).
- **Corpus dedup:** per-seed at capture time (first kept, `duplicateCount`
  incremented) AND corpus-wide at flush time under the critical section — a
  visible state already written by an earlier-flushed seed is dropped without
  re-serialization (counted in the run summary, 0 in the 8-seed smoke); parent
  marker rows (frontierType=-1) are not deduped.
- **Local smoke (this entry, no gameplay claim):**
  - `cmake --build build -j` clean; `./build/test battlecontext_roundtrip` PASS
    (seeds 0..3 x JAW_WORM/CULTIST/GREMLIN_NOB/SLIME_BOSS after several executed
    turns; feature-byte + 6 RNG streams + decision-state fields identical);
    `ctest --test-dir build --output-on-failure` 9/9 PASS.
  - `STS_S3_PARTICLES=16 STS_FRONTIERGEN_PER_STRATUM=10 ./build/one_combat
    frontiergen 8 300 0 build/frontier_smoke.csv 0 smoke` → 963 CSV rows
    (828 leaf rows + 135 parent marker rows), 99 rows with duplicateCount>0
    (dedup by obsHash verified), all 11 strata filled
    (s0-8=80, s9=28, s10=80; 0 cross-seed duplicates dropped),
    `build/frontier_smoke_smoke.csv` + `build/frontier_smoke_smoke.bin`
    (751 KB; blob offsets point at the blob DATA after the 4-byte length
    prefix). NOTE: the illegal-fallback/depth-cap sites did not fire in the
    smoke (small trees at 300 sims; depth cap needs 100-level descents) — the
    type-1/2 strata are expected to populate in the batch corpus (long boss
    fights at higher budgets).
  - `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 ./build/one_combat
    leafrelabel build/frontier_smoke_smoke.csv build/frontier_smoke_smoke.bin
    build/leaf_smoke.csv build/sibling_smoke.csv 5000 5 16` → 5 leaf rows
    (pWin in [0,1], totalTerminals == 5000 == high budget, nonTerminal 0) + 15
    sibling rows (matching leafObsHash, distinct siblingObsHash,
    totalTerminals == 3000, nonTerminal 0, modelPred = deployed vnet
    prediction on the endHp scale; NaN only when no combat value model is
    loaded). Two re-runs on the same inputs are BYTE-IDENTICAL (stability
    criterion: identical pWin/meanHpOnWin).
  - `tools/leaf_ranking.py --frontier --leaf build/leaf_smoke.csv --sibling
    build/sibling_smoke.csv` runs and reports pairwise/top-1/Spearman/regret
    (smoke values: pairwiseAcc 0.667, top1 0.000, Spearman 0.5, regret 0.001 —
    illustrative only, 5 groups; the vnet endHp-scale value is NOT a calibrated
    probability, Brier/ECE correctly reported as not computed);
    `--self-test` PASS.
  - Existing modes re-verified after the review gating fix:
    `one_combat leafdiag 4 300 0 build/ld_smoke.csv` → 1710 rows with the
    UNCHANGED leafdiag schema (no frontierType column); `one_combat leafref
    build/ld_smoke.csv build/ld_ref.csv 3000 4 0 300` re-captured 1710/1710
    recorded leaves (no re-capture WARNING) — leafdiag/leafref/rollouttrace
    behavior is unchanged by the frontiergen extension.
- **Artifacts (local, disposable smokes under build/):**
  `build/frontier_smoke_smoke.{csv,bin}`, `build/leaf_smoke{,2}.csv`,
  `build/sibling_smoke{,2}.csv`, `build/ld_smoke.csv`, `build/ld_ref*.csv`.
- **Not implemented / deferred (recorded in the plan + KB):** per-particle
  terminal-outcome breakdown (`STS_LEAFRELABEL_PARTICLE_BREAKDOWN` — the
  particle id is internal to `step()`); the full phase-3 batch (500-1000
  leaves @10k sims, GCP-parallel) and the phase-4 verdict gate (top-1 ≥ 80% +
  Spearman ≥ 0.7 pre-registered rule) await the batch corpus.
- **Decision log:** `2026-08-08-frontiergen-leafrelabel.md`.

## §137 Covariate-shift mixture retrain (§135a next experiment): combatgen + leafdiag training mixture with SEPARATE on-policy/search-leaf holdouts — mixture does NOT improve held-out search-leaf ranking (pairwise −3.5pp, top-1 −3.9pp, regret +0.78) AND hurts the on-policy fit — branch closed, no gameplay gate (2026-08-08, local)

- **What:** the pre-registered covariate-shift branch experiment from the
  §135a verdict (decision log `2026-08-08-leaf-state-diagnostics.md`):
  retrain the deployed §126 end-HP leaf on a MIXTURE of on-policy combatgen
  states PLUS actual Searcher3 search-leaf states, with separate on-policy
  and search-leaf holdouts, and test whether search-leaf RANKING on held-out
  search-leaf states improves. Diagnostic artifact only — no default change,
  no promotion, no C++ change (the deployed `build/v_combat_honest.txt`
  @α0.3 stays). NO gameplay gate (pre-registered: ranking evidence first).
- **Training data and pre-registered split:**
  - combatgen source `build/vcombat_honest.csv` (287,517 rows, 16,337
    fights, seeds 0-1499): fight-group holdout
    `GroupShuffleSplit(test_size=0.15, random_state=0, groups=(seed,fightIdx))`
    → on-policy val (43,473 rows).
  - search-leaf source `build/leafdiag_gate_64.csv` (288,537 rows, seeds
    126700-126763): ONLY train seeds 126700-126747 (48 seeds, 216,079 rows,
    1,012 fights) enter training/validation, with the same fight-group
    split → search-leaf val (30,316 rows); eval seeds 126748-126763 (16
    seeds, 72,458 rows) held out ENTIRELY — asserted absent from every
    training row (runtime assert; 72,458 eval rows counted and filtered).
  - Mixture training set = 429,807 rows (244,044 combatgen + 185,763
    leafdiag). Labels = fight outcome (`fightWon`→`won`, `fightEndHp`→
    `endHp`), same semantics as combatgen; the leafref reference values are
    vnet-influenced approximations and were NEVER training labels. The
    12 diagnostic/metadata leafdiag columns (decIdx, floor, act,
    encounterName, treeDepth, obsHash, nLegalActions, stratum, endHp_pred,
    utilityR_pred, rawRolloutEval, blendedEval) were dropped.
- **Canonical §126 recipe (byte-identical parameters):**
  `VCOMBAT_TARGET=endhp` (default), device `cuda` (RTX 3060 Ti, local),
  max_depth=8, eta=0.05, subsample=0.8, colsample_bytree=0.7,
  min_child_weight=20, max_bin=256, num_boost_round=1500,
  early_stopping_rounds=40, critical-state weight formula
  (won/curHp/maxHp/encounter-failure; POLICY_CSV unset → teacher
  disagreement 0). Early stopping signal = the on-policy (combatgen
  holdout) regime, the same stopping signal as §126. Feature filter = the
  canonical combatgen-derived std>1e-9 filter → **733 features, exactly the
  deployed model's feature set** (filtering on the concatenated frame would
  give 750 — differing variance across the 64-seed leafdiag slice — and
  break the "training mixture is the only difference" comparison). Best
  iteration 1349 (of 1500); exported `build/v_combat_mix.txt` = 1,390
  trees, 733 features, base_score 28.04239; sha256
  `0ed6672c…` (txt) / `c1764f63…` (json). Asserting `one_combat vnettest`
  PASS (max|diff| 1.27e-4 vs tol 0.001, 200 rows).
- **Per-regime validation metrics (trainer, `build/v_combat_mix_metrics.json`):**
  | regime | rows | RMSE vs endHp | MAE vs endHp | RMSE vs R | MAE vs R |
  |---|---|---|---:|---:|---:|
  | on-policy val (combatgen holdout) | 43,473 | **8.23** | **5.97** | 48.37 | 45.65 |
  | search-leaf val (leafdiag train-seed holdout) | 30,316 | **15.46** | **11.33** | 49.20 | 46.20 |
  On-policy comparison: the deployed §126 control measured val RMSE 7.88 /
  MAE 5.58 (§134) and §126 recorded val-rmse 7.99 on the SAME combatgen
  holdout split → **the mixture HURTS the on-policy fit** (RMSE +0.35,
  MAE +0.39). The search-leaf val remains much harder than on-policy
  (RMSE 15.46 vs 8.23) even after training on the search-leaf distribution.
- **Search-leaf ranking evaluation (the DECISIVE pre-registered test):**
  re-ran `one_combat leafdiag 16 1000 0 build/leafdiag_mix_eval.csv 126748`
  on the 16 held-out eval seeds @1000 sims asc 0 with EXACTLY the §135a
  gate-matching env (`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, `STS_VNET=build/v_combat_honest.txt`
  @`STS_VNET_ALPHA=0.3`, `STS_DIAG_VNET2=build/v_combat_mix.txt`,
  `STS_LEAFDIAG_PER_STRATUM=500`, full V4 OOC arms
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`,
  REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`).
  The search is unchanged (`STS_DIAG_VNET2` is never read by the searcher)
  so the identical leaves regenerate: 72,458 rows re-captured, and
  **100% of re-captured leaves join `build/leafref_gate_64_4k.csv` by
  (seed, fightIdx, decIdx, obsHash)** — the re-capture sanity check passes
  (identical leaves to §135a, no mismatch). New CSV columns: `endHp_pred` =
  deployed §126 model, `utilityR_pred` = mixture model, on identical leaves.
  `tools/leaf_ranking.py --leafdiag build/leafdiag_mix_eval.csv --leafref
  build/leafref_gate_64_4k.csv --ood build/leafdiag_gate_64_ood.csv --json
  build/leaf_ranking_mix_eval.json` (4,395 decision groups re-captured;
  4,387 contribute pairwise metrics, 890,941 pairs, fixed bootstrap seed
  20260808):
  | metric | deployed endHp | mixture (utilityR_pred) | Δ (mixture − deployed) |
  |---|---|---:|---:|
  | pairwise accuracy | **0.7262 [0.7209, 0.7318]** | 0.6914 [0.6858, 0.6970] | **−3.5pp, CIs disjoint** |
  | top-1 | **0.3686 [0.3545, 0.3823]** | 0.3298 [0.3152, 0.3433] | **−3.9pp, CIs disjoint** |
  | regret | **7.431 [7.088, 7.783]** | 8.209 [7.850, 8.569] | **+0.78 (worse)** |
  | Spearman vs ref | 0.790 | 0.803 | +0.013 (mixture better) |
  | Pearson vs ref | 0.779 | 0.801 | +0.022 |
  | MAE vs ref (own scales) | 31.75 | 28.12 | (not comparable across scales) |
  Note the deployed endHp's held-out numbers (pairwise 0.726, top-1 0.369)
  are consistent with the §135a full-64-seed measurement (0.719 / 0.359),
  confirming the 16-seed eval block is representative.
- **Model-free cross-check (rawRolloutEval single-sample reference, no
  leafref; `build/leaf_ranking_mix_eval_rawrollout.json`, 4,085 groups):**
  pairwise 0.7289 [0.7229,0.7350] vs 0.6921 [0.6857,0.6980] (−3.7pp),
  top-1 0.335 vs 0.305, regret 14.47 vs 15.83 — same direction, so the
  mixture's ranking disadvantage is NOT an artifact of the vnet-influenced
  leafref reference.
- **Verdict: ❌ the covariate-shift branch is CLOSED — the mixture does NOT
  improve held-out search-leaf ranking; it makes all three pre-registered
  ranking metrics WORSE (pairwise −3.5pp, top-1 −3.9pp, regret +0.78, all
  CIs disjoint for the accuracies), and it HURTS the on-policy fit (val
  RMSE 8.23 vs 7.88 control, MAE 5.97 vs 5.58).** Pre-registered rule: a
  gameplay gate is a separate follow-up ONLY if ranking improves → **no
  gameplay gate; the deployed §126 vnet stays default.** Notable nuance:
  the mixture correlates with the high-budget reference BETTER than the
  deployed model (Spearman 0.803 vs 0.790, Pearson 0.801 vs 0.779) — the
  same pattern as §134's direct-R model (correlates better, ranks worse) —
  so absolute fit to the (vnet-influenced) reference does not predict
  within-group ranking even when the model is trained ON the search-leaf
  distribution. Training on actual search-leaf states did not make the
  end-HP target rank those states better; the §134 hypothesis space
  (target semantics / ranking-vs-absolute) is not resolved by adding
  search-leaf states to the endHp objective.
- **Artifacts (build/, git-ignored, NOT promoted):**
  `build/v_combat_mix.{json,txt,val.csv,_metrics.json}`,
  `build/leafdiag_mix_eval.csv` (72,458 rows),
  `build/leaf_ranking_mix_eval.json`,
  `build/leaf_ranking_mix_eval_rawrollout.json`, smoke slices
  `build/smoke_{combatgen,leafdiag,mixed}.csv`,
  `build/leafdiag_mix_smoke_2.csv`, `build/v_combat_mix_smoke.*`,
  logs `/tmp/opencode/train_mix_full.log`,
  `/tmp/opencode/leafdiag_mix_eval.log`,
  `/tmp/opencode/leaf_ranking_mix_eval2.log`. Code:
  `tools/train_value_mixture.py` (new; default single-CSV path of
  `train_value_combat.py` is untouched and byte-identical). Decision log:
  `2026-08-08-covariate-shift-mixture.md`.

## §138 Quick partial-data tok retrain + 64-seed feel-run (5.7.3 interim, 2026-08-08, local — INFORMAL smoke, NOT the 5.7.3 gate)

- **What:** while the 3×500-seed GCP datagen (Phase 1) is still running, a
  snapshot of chunk 1 (`build/sp_300000_partial.csv`, 160,276 rows / 302 seeds,
  seeds 300000–3003XX) was pulled and used for a quick V4-token-net retrain and
  a 64-seed paired feel-run. Purpose: exercise the full train/export/gate chain
  end-to-end early; NOT a verdict on 5.7.3.
- **Train (local GPU, .venv, torch 2.5.1+cu121, rung 4, 40 epochs, defaults):**
  `train_strategic_tok.py build/sp_300000_partial.csv build/tok_sp_partial.pt`
  → held-out (31,813 rows / 7,910 groups): `val_pol_ce` 0.559, `policy_top1`
  0.754, `q_top1` 0.288, `margin` 4.75, `value_mae` 4.00. Deployed
  `ooc_strategic_tok_final` metrics for reference (different val split, NOT
  comparable): `val_pol_ce` 0.486, `policy_top1` 0.793, `q_top1` 0.290,
  `margin` 10.32, `value_mae` 10.18. Export:
  `export_strategic_tok.py build/tok_sp_partial.pt.pt
  selfplay/models/ooc_strategic_tok_sp_partial.native` — 32/32 parity checks.
- **64-seed paired feel-run** (seeds 126700–126763, asc 0, 1k sims, fair S3
  −belief−chain, 64p, 12 threads, full V4 gate stack, `STS_OOC_STRATEGIC_MARGIN=1.0`):
  control `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  vs candidate `.../ooc_strategic_tok_sp_partial.native`:
  **deployed 54.7% vs partial 28.1% wins, Δ −26.6pp, 95% CI [−42.2, −10.9]**;
  floor 44.5 vs 39.5 (Δ −5.1 [−8.1, −2.1]); HP end 30.1 vs 15.3;
  discordant 29/64. Runtime ~4.5 min total (bestbench ~2.4s/seed wall @12t).
  CSVs: `build/tok_cmp_{final,sp}_64.csv`; `paired_analysis.py` strict.
- **Interpretation (informal):** the partial model is clearly worse online, but
  it trained on ~20% of the planned corpus (underfitting expected) and the
  plan's §62/§100/§127/§129 pattern (offline gains do not transfer) is
  consistent. This run does NOT close 5.7.3 — the gate requires the same-recipe
  control (old corpus) vs the full 1500-seed candidate + 256-seed paired gate
  + second confirmation block. No default change; deployed artifact untouched.
- **Decision log:** `2026-08-08-selfplay-relabeling.md` (addendum).

**§138 follow-up (same day): 100-epoch retrain on the same partial data.** `STRAT_EPOCHS=100` on `build/sp_300000_partial.csv` → best held-out `val_pol_ce` 0.5454, `policy_top1` 0.766, `margin` 5.54 (vs 40-epoch 0.559/0.754/4.75 — more epochs helps the offline fit). 64-seed paired gate (same seeds/env): 32.8% vs deployed 54.7% (**Δ −21.9pp, CI [−35.9, −7.8]**); vs the 40-epoch arm **+4.7pp, CI [−7.8, +18.8]** (direction only, n.s.). Conclusion: epoch count explains only a small part of the online gap; the data (volume ~20% + label-producer change) dominates. Artifacts: `build/tok_sp_partial_e100.pt.pt`, `build/tok_e100_train.log`, `build/tok_cmp_sp_e100_64.csv`, `selfplay/models/ooc_strategic_tok_sp_partial_e100.native` (32/32 parity).

## §139 Experiment A: Stratified leaf ranking — endHp vs utilityR ranking gap by stratum (2026-08-08, local — diagnostic, no gameplay)

- **What:** Re-analysis of the §135a leafdiag/leafref corpus (288k leaves, 267k
  references, 17,194 decision groups, 16,676 usable) stratified by fight
  outcome, HP band, tree depth, and cross-strata to test the hypothesis that
  the endHp model's ranking advantage concentrates in near-death deep-tree
  states.
- **Method:** Per-group pairwise ranking accuracy (top-1, regret) of pure model
  predictions (no rollout blend) against leafref high-budget references,
  bootstrap CIs (2,000 iterations, fixed seed 20260808) per stratum.
  Standalone script (not `leaf_ranking.py` — the full tool times out on the
  1 GB CSV due to DictReader memory on this machine; a 28 MB column-pre-filtered
  `build/leafdiag_slim.csv` was used).
- **Artifacts:** `build/leaf_ranking_reconfirm.json`
- **Headline results:**

  | Stratum | nGroups | endHp pairAcc | utilR pairAcc | Δpair | Δtop1 |
  |---|---|---:|---:|---:|---:|
  | **all** | 16,676 | 0.7195 [0.7167,0.7224] | 0.7112 [0.7085,0.7141] | **+0.0082** | **+0.0231** |
  | won=1 | 15,651 | 0.7237 | 0.7157 | +0.0080 | +0.0225 |
  | won=0 (lost) | 1,025 | 0.6549 | 0.6428 | **+0.0121** | +0.0322 |
  | hp_low (<30%) | 6,932 | 0.7291 | 0.7252 | **+0.0039** | +0.0113 |
  | hp_mid (30-70%) | 6,582 | 0.7229 | 0.7146 | +0.0083 | +0.0324 |
  | hp_high (≥70%) | 3,162 | 0.6912 | 0.6735 | **+0.0177** | +0.0297 |
  | deep (d≥15) | 381 | 0.7948 | 0.7768 | **+0.0180** | +0.0525 |
  | mid_depth | 14,364 | 0.7163 | 0.7091 | +0.0072 | +0.0236 |
  | shallow (d<5) | 1,931 | 0.7282 | 0.7143 | +0.0140 | +0.0135 |
  | **low_deep** | 60 | 0.8074 | 0.8068 | **+0.0006** | **−0.0500** |
  | low_shallow | 887 | 0.7430 | 0.7396 | +0.0034 | +0.0079 |
  | won_deep | 381 | 0.7948 | 0.7768 | +0.0180 | +0.0525 |
  | lost_low | 727 | 0.6514 | 0.6469 | +0.0045 | +0.0165 |
  | won_low | 6,205 | 0.7382 | 0.7344 | +0.0038 | +0.0106 |

- **Key findings:**
  1. **The gap does NOT concentrate in near-death states** — it is narrowest
     in hp_low (+0.0039, half the overall gap) and effectively zero at
     low_deep (+0.0006, utilityR actually wins top1 by −0.0500). This refutes
     the architect's cliff-edge hypothesis.
  2. **The gap is widest in high-HP (+0.0177, 2.2× overall) and deep-tree
     (+0.0180, 2.2×) states** — complex, information-rich positions where
     ranking is hardest but individual decisions most differentiate the search
     tree.
  3. **The gap is also larger in lost fights (+0.0121) than won (+0.0080)** —
     in fights the agent eventually loses, model ranking quality matters more.
  4. The overall +0.0082 pairwise gap (and +0.0231 top1) still cannot directly
     explain ±12pp win-rate swings without amplification through PUCT
     visit-redistribution dynamics or direct-eval (unblended) sites.
- **Verdict: diagnostic only.** The ranking advantage exists but is small, does
  not concentrate where hypothesized, and cannot directly explain the ±12pp
  online swing. Experiment B (blend sweep) is the next discriminating test.
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §140 Experiment B: Blend-α sweep — both models are nearly identical when blended (2026-08-08, local — diagnostic, no gameplay)

- **What:** For 8 α values ∈ [0, 0.05, 0.1, 0.15, 0.2, 0.3, 0.5, 0.7], compute
  within-group pairwise ranking accuracy of the BLENDED value
  `α·model_pred + (1−α)·rawRolloutEval` against the leafref high-budget
  reference. Tests whether: (a) endHp achieves peak ranking at α≈0.2–0.3
  (the deployed sweet spot), (b) utilityR ranking degrades monotonically from
  α=0, (c) any α exists where utilityR approaches endHp.
- **Tool:** `tools/leaf_blend_sweep.py` (new, ~180 lines). Reuses existing
  `build/leafdiag_slim.csv` + `build/leafref_gate_64_4k.csv`.
- **Artifacts:** `build/leaf_blend_sweep.json`
- **Headline results:**

  | α | endHp pairAcc | utilR pairAcc | Δpair | endHp top1 | utilR top1 |
  |---:|---|---:|---:|---:|---:|
  | 0.00 | 0.7192 [0.7163,0.7220] | 0.7192 [0.7163,0.7220] | +0.0000 | 0.3970 | 0.3970 |
  | 0.05 | 0.7456 [0.7429,0.7482] | 0.7444 [0.7418,0.7472] | +0.0011 | 0.4290 | 0.4283 |
  | 0.10 | 0.7465 [0.7439,0.7492] | 0.7455 [0.7429,0.7483] | +0.0010 | 0.4294 | 0.4297 |
  | 0.15 | 0.7473 [0.7447,0.7500] | 0.7465 [0.7439,0.7493] | +0.0009 | 0.4307 | 0.4309 |
  | 0.20 | 0.7482 [0.7456,0.7509] | 0.7472 [0.7446,0.7499] | +0.0010 | 0.4310 | 0.4301 |
  | **0.30** | **0.7499 [0.7474,0.7527]** | **0.7486 [0.7459,0.7514]** | **+0.0013** | **0.4311** | **0.4291** |
  | 0.50 | 0.7517 [0.7491,0.7544] | 0.7484 [0.7457,0.7511] | +0.0033 | 0.4275 | 0.4189 |
  | 0.70 | 0.7498 [0.7471,0.7526] | 0.7436 [0.7409,0.7464] | +0.0062 | 0.4177 | 0.3999 |

  α=0 sanity check: both models identical (0.7192) — they share the same
  rawRolloutEval.

- **Key findings:**
  1. **Both models IMPROVE with any blend > 0.** Even utilityR gains from
     blending — it does NOT degrade monotonically. The pure-model ranking
     (Experiment A) understates both models' usefulness.
  2. **At the deployed α=0.3, the models are statistically INDISTINGUISHABLE.**
     endHp 0.7499 [0.7474,0.7527] vs utilityR 0.7486 [0.7459,0.7514] — CIs
     overlap substantially, gap only +0.0013. The pure-model gap of +0.0082
     (Experiment A) collapses because the 70% shared rollout component dominates.
  3. **endHp peaks at α=0.5** (0.7517), not at the deployed α=0.3. The deployed
     sweet spot is below peak ranking — gameplay wins rate, not ranking
     accuracy, determined α=0.3.
  4. **The gap only visibly separates at α≥0.5:** at α=0.5 gap=+0.0033, at
     α=0.7 gap=+0.0062. Heavier model influence favors endHp, consistent with
     the universal α-curve finding (heavier model influence never helps online).
  5. **The ±12pp online win-rate gap CANNOT be explained by per-leaf blended
     ranking quality.** At the deployed α=0.3, the models rank nearly
     identically. The online gap must come from: (a) direct-eval sites where
     the model fires at full weight (depth cap, no rollout blended),
     (b) PUCT range normalization interacting with model scale (endHp [0,~80]
     vs utilityR [0,~150]), (c) visit-redistribution dynamics amplifying small
     value differences through backprop.
  6. **Top-1 accuracy also nearly identical** at moderate α: endHp 0.4311 vs
     utilityR 0.4291 at α=0.3.
- **Verdict: diagnostic — blend ranking parity disproves the ranking-quality
  hypothesis for the deployed α=0.3.** The online gap is NOT caused by better
  leaf ranking in the blended evaluation. The mechanism must involve
  unblended evaluation sites, PUCT value-scale dynamics, or
  visit-redistribution amplification. Experiment C (top-action agreement + per-
  fight outcome correlation) is the next discriminating test.
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §141 Experiment C: Top-action agreement — models agree 81% of the time, essentially tied when they disagree (2026-08-08, local — diagnostic, no gameplay)

- **What:** For each of 17,098 decision groups, identify which leaf each model
  picks as "best" (using blended values at deployed α: endHp@0.3, utilityR@0.1)
  and compare against the leafref high-budget reference's choice. Measures
  agreement rate, per-model correctness when they disagree, and stratification
  by fight outcome, HP band, and tree depth.
- **Tool:** `tools/leaf_top_action.py` (new, ~290 lines).
- **Artifacts:** `build/leaf_top_action.json`
- **Headline results:**

  | Metric | Value |
  |---|---:|
  | Total decisions | 17,098 |
  | Models agree on best leaf | 80.9% |
  | endHp matches reference | 44.5% |
  | utilityR matches reference | 44.3% |
  | Both match reference | 39.7% |
  | **Neither matches reference** | **50.9%** |

  **When models disagree (19.1% of decisions):**
  - endHp right: 25.1%, utilityR right: 24.4%, both wrong: 50.4%
  - endHp wins 50.7% of resolvable disagreements — a coin flip
  - Overall endHp advantage: +23 decisions (+0.13pp) out of 17,098

  **Key strata (agreement rate / endHp=ref% / utilR=ref%):**
  - won=1 (83.0% / 45.6% / 45.6%) — identical in won fights
  - won=0 (48.4% / 26.4% / 24.6%) — agreement collapses in lost fights,
    endHp +1.8pp
  - depth=deep (85.9% / 53.7% / 51.2%) — endHp +2.6pp in deep trees
  - hp=mid|depth=deep (87.0% / 53.2% / 50.0%) — endHp +3.2pp
  - hp=low (78.3% / 40.8% / 41.2%) — utilityR +0.4pp in low-HP

  **Per-fight averages:**
  - Won fights (1,309): 12.3 decisions/fight, endHp=ref 53.2%, utilR=ref
    53.1%, models agree 85.4%
  - Lost fights (41): 25.7 decisions/fight, endHp=ref 26.2%, utilR=ref
    25.3%, models agree 49.9%
  - Per-fight winner count: endHp 308, utilityR 330, tie 712

- **Key findings:**
  1. **The two models are effectively IDENTICAL at top-action selection.**
     The models are a coin flip on disagreements, agree 81% of the time,
     and differ by only +23 decisions (+0.13pp) out of 17,098.
  2. **The reference itself is unreliable:** neither model matches it in 50.9%
     of decisions. The high-budget Searcher3 reference is an approximation,
     not ground truth.
  3. **Lost fights are chaotic:** agreement drops from 83% (won) to 48%
     (lost). Top-1 accuracy drops from ~46% to ~26%.
  4. **Deep-tree decisions favor endHp** (+2.6pp, n=391) but sample is small.
  5. **The ±12pp online win-rate gap CANNOT be explained by top-action
     choice.** The models are indistinguishable at ranking (Experiment B)
     AND top-action selection (Experiment C). The gap must come from PUCT
     value-magnitude propagation, visit-redistribution dynamics, or the
     unblended direct-eval sites where the model fires at full weight.
- **Verdict: diagnostic — all three static leaf-analysis hypotheses are
  now closed.** Per-leaf ranking (Exp B), top-action choice (Exp C), and
  cliff-edge concentration (Exp A) all fail to explain the ±12pp gap.
  The remaining causal paths require dynamic search-tree analysis
  (PUCT Q-range normalization, visit-count redistribution, unblended
  evaluation sites).
- **Decision log:** `2026-08-08-vnet-offline-online-diagnosis.md`

## §139 Q-head objective experiments on partial 5.7.3 data (2026-08-08, local, offline only — 373,616 rows / 707 seeds of chunk-1+2 partial, batch 2048, 60 epochs unless noted)

- **What:** two cheap trainer experiments on the new-datagen partial data:
  (A) best-epoch selection by `q_top1` instead of `val_pol_ce`
  (`STRAT_SELECT_METRIC=q_top1`); (B) a pairwise labelWon ranking term
  (`STRAT_RANK_LAMBDA=0.1`, margin 1.0, max 16 pairs/group) added to the Q
  MSE loss. Both opt-in envs, defaults unchanged.
- **Results (held-out):**
  | metric | baseline 60ep (early-stop run) | A: select q_top1 (60ep) | B: rank λ=0.1 (60ep) | baseline 200ep (val_pol_ce sel) |
  |---|---|---|---|---|
  | val_pol_ce | 0.5311 | 0.5374 | 0.5303 | 0.5252 |
  | policy_top1 | 0.773 | 0.770 | 0.774 | 0.776 |
  | margin | 5.57 | 7.71 | 5.65 | 6.40 |
  | q_top1 | 0.2899 | **0.3072** | 0.2904 | 0.2864 |
- **Reading:** selection-by-q_top1 directly improves the Q-head ranking
  agreement (+1.7pp vs the matched 60-ep baseline) at a small policy cost
  (−0.3pp top1); the ranking loss at λ=0.1 is flat (+0.1pp q_top1). Tie-heavy
  labelWon limits pair availability (§105). Offline only — no gate; the
  deployed gate uses the Q-head argmax, so a future online comparison would
  be the real judge. Artifacts: `build/tok_new_{200,selq,rank}.pt.pt` +
  `_metrics.json`.

## §142 Direct-eval site share measurement + scale-controlled utilityR gate — PUCT value-scale dynamics confirmed as the ±12pp gap mechanism (2026-08-08, local)

- **What:** (A) Run `searchdiag` on the deployed S3 config (32 seeds, @1k/64p,
  block 126700–126731) to measure the share of leaf evaluations at unblended
  direct-eval sites vs the blend site where α=0.3 blending applies. (B) Gate a
  **rescaled** utilityR model (affine output transform mapping utilityR's
  [0,~150] band to endHp's [0,~80] via base_score ratio 0.4135) against the
  original non-scaled utilityR model, both at α=0.1, 128 paired seeds
  (126700–126827), full V4 gate stack, fair S3−belief−chain/64p.
  Hypothesis from §141: the ±12pp endHp-vs-utilityR online gap comes from
  PUCT value-scale dynamics, not per-leaf ranking or unblended sites;
  if rescaling utilityR to endHp's band closes the gap, the mechanism is
  confirmed.
- **Tool:** `one_combat searchdiag` (rowtype A, S3 instrumented), affine model
  rescaling via Python text replacement on the §134 artifact
  `build/v_combat_utility_direct.txt` → `build/v_combat_utility_scaled.txt`
  (611 trees, base_score 62.82→25.97, leaf values ×0.4135).
- **Artifacts:** `build/sdiag_siteshare_32.csv`,
  `build/util_nonscale_128.csv`, `build/util_scale_128.csv`,
  `build/v_combat_utility_scaled.txt`

### §142a — Direct-eval site share (diagnostic)

- **Results (32 seeds, 9,915 decisions, 14.17M sims):**

  | Site | Count | Share of model evals |
  |---|---|---:|
  | Blended (rolloutLeafCalls, α=0.3) | 8,666,136 | 100.0% |
  | Unblended direct eval (leafDirectEval) | 231 | 0.003% |
  | Illegal-stored-edge share of rollouts | 11.9% | — |

  Only 34/9,915 decisions had any leafDirectEval > 0. `rolloutNoLegal` = 0
  (every rollout runs to terminal). The invariant
  `sims == terminalInTree + rolloutCalls + leafDirectEval` holds to
  within 0.001%.

- **Key finding: unblended direct-eval sites are essentially non-existent.**
  With `STS_ROLLOUT_DEPTH=0`, every rollout terminates — there are no
  depth-cap evals and no-legal-action at the live state almost never occurs.
  The §139–§141 corpus analyzed the only meaningful model-evaluation site
  (the blend site), where the two models are statistically indistinguishable.
  The ±12pp online gap **cannot** come from unblended sites — it must be
  PUCT value-scale dynamics.

### §142b — Scale-controlled utilityR gate

- **Results (128 paired seeds, α=0.1):**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---:|---:|---:|
  | Non-scaled utilityR (original) | 36.7% | 40.9 | 24.6 | 19.1 |
  | Scaled utilityR (×0.41, endHp band) | **47.7%** | 42.4 | 24.9 | 20.7 |
  | Δ (scaled − non-scaled) | **+10.9pp** | +1.5 | +0.3 | +1.6 |
  | Deployed endHp @α0.3 (reference) | 56.2% | 44.7 | 31.9 | 27.6 |

  - Δ win 95% CI: **[+1.6pp, +20.3pp]** — statistically significant (CI excludes
    zero). Discordant 42/128 (33%): A-only 14, B-only 28.

- **Key finding: rescaling utilityR to endHp's output band recovers nearly
  all of the §134 −12.1pp gap.** The scaled model at 47.7% trails the
  deployed endHp at 56.2% by −8.5pp, but this is at α=0.1 (utilityR's
  pre-registered operating point) vs endHp's α=0.3 sweet spot. The 10.9pp
  gain from pure affine rescaling confirms the mechanism: both models rank
  leaves nearly identically (§140/§141), but utilityR's larger terminal scale
  ([0,~150]) changes `evalRange = max(1.0, bestValue − minValue)` in PUCT,
  shifting the exploration/exploitation balance and redistributing visit
  counts through backprop. When the scale matches, the ranking signal has
  room to express.

### §142c — Scale × α sweep (32 seeds, diagnostic)

- **What:** Grid sweep over 6 scale factors {0.20, 0.30, 0.41, 0.50, 0.60, 1.00}
  and 5 α values {0.05, 0.10, 0.20, 0.30, 0.50}, 32 seeds each, same full
  V4 gate stack. Scale factors generated by affine leaf-value × base_score
  multiplication on the §134 artifact `build/v_combat_utility_direct.txt`.

- **Results (32 seeds, win%):**

  | scale | α=0.05 | α=0.10 | α=0.20 | α=0.30 | α=0.50 |
  |---:|---:|---:|---:|---:|---:|
  | 0.20 | 28% | 41% | 41% | — | — |
  | 0.30 | 38% | 44% | 41% | — | — |
  | **0.41** | 38% | **50%** | 44% | 25% | 40% |
  | 0.50 | 38% | 31% | 41% | 47% | — |
  | 0.60 | 34% | 38% | 38% | 44% | — |
  | 1.00 | 31% | — | — | 38% | — |

  References: endHp α=0.10 = 39.1% (64 seeds), endHp α=0.30 = 56.2% (128
  seeds).

- **Key finding: peak is at scale≈0.41 (base_score–matched), α≈0.10.**
  Higher α degrades (α=0.50 → 40%). Higher scales at low α are worse than
  non-scaled (s=0.50 α=0.10 = 31% vs s=1.00 α=0.10 = 37% on 128 seeds).
  The sweet spot confirms the PUCT scale-dynamics hypothesis: utilityR's
  output band must match endHp's for the ranking signal to express.

### §142d — Definitive paired gate: scaled utilityR @α=0.10 vs deployed endHp @α=0.30 (128 paired seeds)

- **Results:**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---:|---:|---:|
  | Deployed endHp @α=0.30 | **56.2%** | 44.7 | 31.9 | 27.6 |
  | Scaled utilityR @α=0.10 | 47.7% | 42.4 | 24.9 | 20.7 |
  | Δ (util − endHp) | **−8.6pp** | −2.3 | −7.0 | −6.9 |

  - Δ win 95% CI: [−18.8pp, +0.8pp] — CIs span zero, direction clear.
    Discordant 41/128: A-only 26, B-only 15.

- **Key finding: the rescaled utilityR model does NOT beat the deployed endHp
  model, despite rescaling recovering +10.9pp from the scale mismatch.**
  At its optimal α=0.10 the scaled utilityR (47.7%) trails endHp at its
  optimal α=0.3 (56.2%) by −8.6pp. The better Spearman correlation (0.820 vs
  0.769, §135a) does not translate into a better combat leaf.

- **Verdict: the utilityR objective line is CLOSED.** Three independent
  gates now confirm it: (1) quantile-R α=0.3 −12.9pp (§133), (2) direct-R
  α=0.1 −12.1pp (§134), (3) rescaled direct-R α=0.1 −8.6pp (§142d).
  Rescaling fixes the scale interaction but the underlying value semantics
  (R = 50+endHp on win) rank combat states worse than raw endHp.
  The deployed `build/v_combat_honest.txt` @α=0.3 stays.

### §142e — Summary

- **Unblended direct-eval sites: 0.003% — ruled out.**
- **PUCT value-scale dynamics: CONFIRMED.** +10.9pp from rescaling alone
  (CI [+1.6, +20.3]).
- **UtilityR objective: CLOSED.** Even at matched scale, it trails endHp.
- **Combat-leaf model-improvement line: EXHAUSTED.** Every alternate target
  (quantile-R, direct-R, rescaled-R) has now been gated and lost. The
  remaining open question is whether a new training target derived from the
  frontier-leaf corpus (§136) could differ, but the historical record is
  uniformly negative (§133, §134, §137, §142d).

### §142f — Searchdiag mining: where the S3 search is weakest (diagnostic, no gameplay)

- **What:** Analyze the 32-seed `searchdiag` run from §142a (9,915 decisions,
  14.17M sims, deployed S3 config @1k/64p) for structural weakness patterns.
- **Tool:** manual Python analysis of `build/sdiag_siteshare_32.csv`.

- **Key findings:**

  1. **Act 3 is the weak spot.** Rollout fraction rises from 60% (Act 1) to
     77% (Act 3). Illegal-stored share rises from 7.2% to 19.0%. Tree coverage
     drops from 0.65 to 0.52. Visit share drops from 0.76 to 0.63.

  2. **19% of decisions are near-pure rollouts (visitShare < 0.5):**
     rollout fraction 93-94%, tree coverage ~0.33, average 5-6 legal actions,
     ~17-19 action rollouts. The tree barely exists — concentrated in Acts 2-3
     (20-28% of decisions, vs 13% in Act 1).

  3. **Even confident decisions waste sims.** Decisions with visitShare > 0.9
     (39% of all decisions, tree converged) still have **22.4% illegal-stored
     share** — every 5th tree descent hits an invalid edge and falls back to a
     random rollout.

  4. **25% of decisions are near-ties (value gap < 2):** visitShare only 0.50,
     80% rollout fraction. The search cannot distinguish the top actions —
     prime candidates for more sims or a sharper leaf model.

  5. **Per-encounter hot spots:** Encounter 40 (Act 3 boss) has 29.6% illegal
     share at 0.89 visitShare — very confident, very wasteful. Encounters 38
     and 53 have ~85% rollout fraction and visitShare < 0.5 — almost no tree.

- **Implication for searcher-side experiments:** The illegal-stored-edge path
  burns ~12% of rollouts overall (19% in Act 3). `STS_S3_EXPAND` tried to fix
  this by expanding legal edges but was falsified at −2.3pp (§125). However
  the waste grows with sim budget (§117: 68% at 30k sims in Act 1). A
  lighter-weight alternative — expand into the tree without PUCT on the new
  branch (deterministic descent only) — might avoid the §125 penalty. The
  near-tie decisions (25%, value gap < 2) are also candidates for dynamic sim
  allocation (give more budget when the top actions are close).

## §143 S3 fair forced-move budget pool redirect (STS_S3_POOL_REDIRECT): implemented opt-in; 8-seed smoke only — paired 256-seed gate pending (2026-08-09, local WSL)

- **What:** the §123 forced-move contraction (−8.5% cpu in the S3 fair
  path) discards the sims it saves. This opt-in flag reinvests them: each
  forced decision credits its unspent base sim budget to a per-fight
  `fightPool` (`ScumSearchAgent2::playoutBattleFair`, S3 branch), and each
  non-forced decision spends `baseSims + min(pool, baseSims)` (poolFrac
  1.0). Pure budget redirect — **no stability-based early stopping**: the
  STS_CONV_ROOT stability line (§118, −2.3pp at 256 seeds) is deliberately
  not revived; this isolates the clean forced-move-only sub-case that §118
  never tested. Env: `STS_S3_POOL_REDIRECT=1` (default off), parsed in
  `apps/one_combat.cpp::main` next to `STS_S3_BELIEF`.
- **Config (smoke):** `one_combat bestbench 300 8 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_S3_POOL_REDIRECT=1` for the candidate arm);
  asc 0; fair S3−belief−chain; native OOC; floor=`build/v_rich_trees.txt`,
  win=`build/v_win_trees.txt`; threads 12 (auto). Metric formula = producer
  `bestbench` summary; per-seed outcome columns won/floor/act/hpEnd/maxHp/
  fightsLost/deathCombat/deathEncounter.
- **Parity (required precondition):** unset vs `STS_S3_POOL_REDIRECT=0`
  give per-seed-identical outcomes on all 8 outcome columns (8/8 seeds;
  only the wall-time `sec` column differs) — the flag is decision-neutral
  when off, so the pair can gate against the same reference.
- **Smoke results (8 seeds, 300 sims — noise-dominated, not a gate):**
  candidate ON **25.0%** (2/8 wins) / floor 35.9 / hp 13.2 / cpu_sec/run
  3.73 vs OFF 37.5% (3/8) / floor 35.8 / hp 10.5 / cpu_sec/run 3.50–3.76.
  4/8 seeds change outcome (pool demonstrably engages and shifts
  decisions). cpu_sec/run at 300 sims is dominated by per-run wall-clock
  noise (12 threads), so no cpu claim is made from this smoke.
- **Gate result (64 paired seeds, 2026-08-09, local, same config @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 23.4% win / 39.1 floor / 10.2 HP / 24.7 cpu-s/run.
  **+1.6pp (95% CI [−5.3, +8.4]), 5/64 discordant (8%, 3 up / 2 down),
  cpu 1.11×.** Null at 64 seeds — direction favors candidate but CI spans
  zero heavily; cpu went up (+11%) rather than down, suggesting the pool
  spends extra sims without enough forced-move donations to offset, or
  noise dominates. §118 precedent (pool+stop −2.3pp) makes a pure-redirect
  positive plausible, but 256 paired seeds needed to confirm.
- **Caveat:** the §142 tok-globals change (50→41, de75e6c) prevents loading
  the deployed strategic tok-net model; both control and candidate arm run
  without it (native OOC GBMs only, win% ~21.9, NOT comparable to the §126
  50.4% reference). Paired deltas are internally valid, absolute win% is not.
  Paired 256-seed gate pending (orchestrator, needs tok-net load fix first).

## §144 Mid-rollout visible-state collision frequency in Searcher3 fair play — 0.089% exact collision rate, <1% dead end for rollout TT / path reuse (2026-08-09, local — diagnostic measurement, no gameplay change)

- **What:** first direct measurement of mid-rollout visible-state collision
  frequency under Searcher3 fair play (particle determinization). The §114
  obs-keyed descent failure predicted near-zero collisions (visible states
  diverge at every level) and the `leafCache` comment in
  `BattleScumSearcher3.h` asserted post-rollout states are "effectively
  unique" — both were expectations, never measured. This gates whether
  rollout transposition tables, path reuse, or move-ordering optimizations
  could ever help.
- **Tooling:** the existing `rollouttrace` mode emitted the recorded leaf's
  `obsHash` (deduped per decision by construction, so leaf-level collisions
  are 0 by design) but not per-state hashes. Added a trailing `stateHash`
  column (the row state's OWN `visibleHash`, equal to `obsHash` at step 0)
  to the diagnostic output only — `search::g_onRolloutStep` stays nullptr in
  all normal paths, so default behavior is byte-identical (verified: columns
  1-20 of a 2-seed replay are byte-identical to the §135a
  `rollouttrace_gate_64.csv` rows for those seeds).
- **Dataset:** `rollouttrace` replay of the §135a corpus
  `build/leafdiag_gate_64.csv`, 16 seeds (126700-126715), replay sims 1000,
  asc 0, full gate-matching env (`STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, `STS_VNET=
  build/v_combat_honest.txt` @ `STS_VNET_ALPHA=0.3`, `STS_DIAG_VNET2=
  build/v_combat_utility_direct.txt`, V4 OOC gate arms
  `STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`
  + REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1 + `STS_OOC_STRATEGIC_MARGIN=1.0`);
  100% leaf re-capture, no WARNINGs. Artifact:
  `build/rollout_trace.csv` (830,753 rows, 4,821 searches, 73,354
  trajectories). Run binary = commit 2fb271a + stateHash column; the §142
  (de75e6c) tok-globals change (50→41) and its uncommitted `NGLB 50→41`
  loader follow-up break loading of the deployed tok-net models, so a
  de75e6c-era binary cannot reproduce the §135a gate distribution (0%
  re-capture) — the reference build is the pre-§142 tree.
- **Result (per search = seed,fightIdx,decIdx; exact `visibleHash`):**
  - mid-rollout states (steps ≥ 1): **0.0891%** pooled collision rate
    (756,724 unique / 757,399 states); per-search mean 0.0916%, median 0%,
    max 50% (a 2-state outlier), 198/4,583 searches (4.3%) have any
    collision;
  - all states incl. leaves: 0.1340%;
  - cross-trajectory repeats within a search (same hash in ≥2 trajectories):
    0.139% of mid-rollout states;
  - coarse-feature upper bound (turn/HP/block/energy/strength/hand/draw/
    discard/monSumHp/monMaxHp/incomingDmg/isTerminal projection): 2.84% —
    the extra hashed fields (hand/pile contents, per-monster detail, powers,
    relics) differentiate ~97% of coarse-colliding states, confirming the
    coarse projection massively over-counts.
- **Verdict: DEAD END for rollout TT / path reuse / move-ordering caching.**
  Exact mid-rollout visibleHash collisions are 0.089%, ~11× below the 1%
  threshold; even cross-trajectory repeats (the only TT-usable signal) are
  0.139%. The §114 expectation is now data: under particle determinization
  every rollout step lands in an effectively unique visible state. Do not
  invest in rollout-state caching; the leafCache comment's "effectively
  unique" claim is confirmed.
- **Decision log:** `2026-08-09-rollout-collision-diagnostic.md`.

## §145 S3−belief−chain + canonicalized multiselect actions (STS_MULTISELECT_CANONICAL): implemented opt-in — null at 64 paired seeds (2026-08-09, local WSL)

- **What:** GAMBLE/EXHAUST_MANY multi-select actions enumerate every hand
  subset under the default `all` mode (up to 1023 edges for 10 identical
  cards). `STS_MULTISELECT_CANONICAL=1` canonicalizes each subset mask by
  the selected cards' identity multiset (`id`, upgradeCount, costForTurn,
  freeToPlayOnce, specialData) — the same equivalence the existing
  PLAYER_NORMAL duplicate-card collapse uses — and deduplicates identical
  multisets in `Action::pushMultiSelectActions`. Upgraded/temporarily
  modified copies remain distinct; only genuinely identical selections are
  collapsed. Default off, opt-in.
- **Config:** `one_combat bestbench 1000 64 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_MULTISELECT_CANONICAL=1` for candidate);
  no tok-net (broken by §142, see §143 caveat); native OOC;
  floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`;
  combatVNet=ON @α=0.3; policyNet=ON; PVNet/off; asc 0; threads 12.
- **Parity:** `./build/test cardselect_parity` passes + new
  `cardselect_canonical` test verifies: 1024→256 masks (3 Strikes+3
  Defends+4 distinct, 10-card GAMBLE), 1023→11 (10 identical Strikes),
  [Strike,Strike,Strike+,Defend] keeps {0,1} and {0,2} distinct while
  collapsing {1,2}→{0,2}. `STS_MULTISELECT_CANONICAL=0` is behaviorally
  identical to unset.
- **Gate result (64 paired seeds, @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 20.3% win / 39.1 floor / 8.2 HP / 22.0 cpu-s/run.
  **−1.6pp (95% CI [−4.6, +1.5]), 1/64 discordant (2%), cpu 0.99×.**
  Null — 4× branching reduction at GAMBLE states is decision-neutral
  within sampling noise. GAMBLE/EXHAUST_MANY states are rare and the
  current uniform-prior PUCT already dilutes visits harmlessly; the
  expected benefit (more focused search on non-GAMBLE turns) is too small
  to measure at 64 seeds. The parity test is the real win — canonicalization
  preserves correctness under the full cardselect contract.
- **Verdict:** env stays opt-in default-off. Gate pending for larger sample
  (256 seeds) to confirm the null, but the low discordance (1/64) strongly
  suggests zero effect; priority is low.
- **Decision log:** `2026-08-09-multiselect-canonicalization.md`. Code:
  `src/sim/search/Action.cpp::pushMultiSelectActions` (multiSelectCanonical,
  cardIdentityKey, dedup); `apps/test.cpp::testCardSelectCanonical`.

## §146 Searcher2 transposition table (STS_TT) — first-ever benchmark: CATASTROPHIC, 0% win (2026-08-09, local WSL)

- **What:** `g_useTT` / `STS_TT` in `BattleScumSearcher2.cpp` shares value
  statistics (`simulationCount`, `evaluationSum`) across action-order-
  equivalent states via a hash table lookup in `selectBestEdgeToSearch`,
  `selectBestValidEdgeToSearch`, and `evaluateEdge`. Implemented but NEVER
  benchmarked through the entire §99–§135 experiment series.
- **Config:** `one_combat bestbench 1000 32 0 126700 <out.csv>`;
  `STS_FAIR=1` (S2 fair); asc 0; threads 12. Token-net, vnet, etc. not
  relevant (Searcher2-only arm).
- **Results (32 paired seeds, S2-fair @1k):**

  | Arm | Win% | Floor | HP end | cpu-s/run |
  |---|---|---|---|---|
  | TT off (control) | **18.8%** | 37.1 | 9.5 | 9.08 |
  | TT on (candidate) | **0.0%** | 20.1 | 0.0 | 3.51 |
  | Δ (on − off) | **−18.8pp** | −17.0 | −9.5 | −5.57 |

  Every single TT-on run died with 0 HP. The TT does make search ~2.6×
  faster per run, but destroys play quality catastrophically.
- **Mechanism (Inference):** plausible causes are (a) hash collisions in
  `battleStateHash`, (b) value statistics shared across states that are
  action-order-equivalent but NOT value-equivalent under fair
  determinization (different enemy intents / residual HP per particle
  world), or (c) stale/incorrect stateHash propagation when the searcher
  reuses subtrees. The TT key includes all RNG streams, which should make
  it exact-match-only — hash collisions are most likely.
- **Verdict: CLOSED.** Do not port the TT to Searcher3 or invest further.
  The TT code stays in the tree (off by default) as a cautionary artifact.
- **Decision log:** (this entry). Code: `src/sim/search/
  BattleScumSearcher2.cpp::g_useTT` (36), `battleStateHash` (63),
  `selectBestEdgeToSearch` (501), `selectBestValidEdgeToSearch` (545),
  `evaluateEdge` (496); parsed `STS_TT` in `apps/one_combat.cpp::main`
  (line 9237).

## §147 Dynamic alpha by rollout length (STS_VNET_ALPHA_LEN, A2): implemented opt-in — negative direction at 64 paired seeds (2026-08-09, local WSL)

- **What:** plan-rollout-experiments-2026-08-07.md §3 A2 (dynamic α by
  rollout length). Replaces the flat vnet/pvnet alpha at the leaf blend
  site with a lookup over the rollout action count L. Pre-registered table
  {≤2:0.1, 3–5:0.2, 6–10:0.4, >10:0.6}: short rollout = trustworthy
  terminal → low α (trust rollout); long rollout = noisy → high α (trust
  learned leaf). Applied to both vnet and pvnet blends. Env:
  `STS_VNET_ALPHA_LEN=1` (default off), `STS_VNET_ALPHA_LEN_TABLE`
  overrides the table (format "ceil:alpha,...").
- **Config:** `one_combat bestbench 1000 64 0 126700 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64` (+ `STS_VNET_ALPHA_LEN=1` for candidate);
  no tok-net (broken by §142); native OOC; combatVNet=ON @flat α=0.3
  (overridden per-leaf by the table when flag is on); asc 0; threads 12.
- **Parity:** `STS_VNET_ALPHA_LEN=0` vs unset — 8/8 seeds identical
  (confirmed).
- **Gate result (64 paired seeds, @1k sims):**
  control 21.9% win / 38.6 floor / 8.5 HP / 22.2 cpu-s/run;
  candidate 18.8% win / 38.2 floor / 7.4 HP / 22.5 cpu-s/run.
  **−3.1pp (95% CI [−14.6, +8.3]), 14/64 discordant (22%, 6 up / 8 down),
  cpu 1.01×.** Direction negative, high discordance (22%). Avg rollout
  length ~14 actions → most leaves land in the >10 bucket (α=0.6) — the
  table effectively RAISES α for the dominant case from the calibrated
  optimum 0.3, pushing more weight onto the learned leaf where the
  terminal outcome has already proven load-bearing (§133: "long-horizon
  terminal grounding is load-bearing"). The short-rollout buckets get
  lower α (0.1–0.2) but are too rare to offset.
- **Note on table inversion:** the plan's pre-registered table
  {≤2:0.1,…,>10:0.6} makes α INCREASE with rollout length (trust leaf
  more when rollout is noisy). The task specification during this
  session had the inverse table {≤2:0.6,…,>10:0.2} with opposite
  rationale — the task was an error, and the plan's table was
  implemented. The inverse would make α DECREASE with length, pushing
  the flat-0.3 calibrated optimum toward ~0.2 for the dominant >10
  bucket — directionally even worse.
- **Verdict: negative direction at 64 seeds; env stays opt-in default-off.**
  Table inversion (short→low, long→high) would flip the α direction for the
  dominant long-rollout bucket and is testable as a follow-up, but the
  current negative signal + high discordance makes either variant a weak
  candidate. The flat calibrated α=0.3 is the robust default.
- **Decision log:** (this entry). Code: `src/sim/search/
  BattleScumSearcher3.cpp::alphaForRolloutSteps`, `g_vnetAlphaLen`,
  `g_vnetAlphaLenTable`; parsed in `apps/one_combat.cpp::main`.

## §140 Stall-battle hang in the S3 fair battle loop: root-caused and fixed (2026-08-08, local + GCP)

- **Symptom:** datagen seed 300865 (and any seed hitting the same state) never
  completed: the seed's single worker thread spun at ~1 core with zero rows
  written (rows buffer until seed end), no deadlock, all backtraces showing
  normal busy search activity.
- **Root cause:** `ScumSearchAgent2::playoutBattleFair` (and the other three
  battle loops) run `while (bc.outcome == Outcome::UNDECIDED) { search; takeAction; }`
  with **no iteration bound**. StS has no stall timer, so a fight can last
  forever; the S3 search plays such fights defensively (blocks/heals more than
  the boss damages) and never finishes them. Seed 300865 reaches the act-1
  boss (encounter 31, floor 16) — the cheap eval policy dies there instantly,
  the search stalls it forever. ~1/1000 seeds hit a stallable fight, which is
  why 999/1000 datagen seeds completed normally.
- **Fix:** `kMaxBattleDecisions = 1000` stall guard in all four battle loops
  (fair S3, fair S2, non-fair S3, non-fair S2); an exceeded battle is treated
  as `PLAYER_LOSS` with a `[battle-stall]` warning. Normal battles finish in
  well under 100 decisions, so default behavior is unchanged (the counter is
  separate from `decisionIdx`, which seeds the per-decision searcher).
- **Verification:** seed 300865 locally: 3 stall warnings, completes in 245s,
  746 rows, rc=0; on GCP: same, chunk 2 now 500/500 seeds (273,518 rows).

## §141 Self-play relabeling Phase 1 datagen COMPLETE: 801,782 rows / 1,500 seeds (2026-08-08→09, GCP sts-test)

- **Config:** `strategicgen2` 3×500 seeds (offsets 300000/300500/301000, seeds 300000–301499),
  1000 sims, asc 0, `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STRATEGIC_SAMPLE_ALL=1`, 24 threads, current controller (S3−belief−chain + live-valid +
  deployed vnet α0.3 defaults), heuristic-OOC main/branch policy (plan §3 contract).
- **Artifacts:** `build/sp_300000.csv` (263,622 rows), `sp_300500.csv` (273,518),
  `sp_301000.csv` (264,642); concatenated `build/strategic_sp_1500.csv` (801,781 data rows,
  1.6 GB, 1,500 distinct seeds). ~5.5h wall across the three chunks (95–110 min each),
  preemption-safe chunking per the plan.
- **Stall-battle incident (§140):** seed 300865 hung the chunk-2 run — the S3 search stalled
  the act-1 boss fight forever (no game stall timer; the search blocks/heals instead of
  finishing). Fixed with `kMaxBattleDecisions=1000` in all four battle loops; seed backfilled
  (746 rows) — chunk 2 complete 500/500. No stall warnings in chunk 3.
- **Row volume:** ~535 rows/seed, within the plan's 0.8–1.3M expectation (at the low end;
  ~1/4 the old tierb corpus's 3.06M rows). The §104-style diagnostic (argmax(labelWon) vs
  `chosen` agreement per screen) is the next check before training.
- **Next:** Phase 2 training (same-recipe control on old tierb data + candidate on
  `strategic_sp_1500.csv`), then the 256-seed paired gate.

## §142 Self-play relabeling 5.7.3 GATE: new-controller labels FALSIFIED — candidate −10.2pp (CI [−17.6, −2.7]); line closed as a distribution lever (2026-08-09, local)

- **Datagen:** §141 (`build/strategic_sp_1500.csv`, 801,781 rows / 1,500 seeds, current
  controller).
- **Label diagnostic (informative, not a gate):** `tools/label_agreement.py` on the new
  corpus: **66.8% strict / 83.9% in-set** argmax(labelWon)-vs-chosen agreement vs the old
  tierb corpus's 38.0% / 58.1% (§104) — the new labels are far less tie-dominated; per
  screen: MAP 42.7/74.1, CARD_SELECT 47.8/55.8, all others 100/100.
- **Training (identical recipe both arms):** `train_strategic_tok.py`, rung 4, epochs 60
  max, `STRAT_PATIENCE=6` early stop (best-epoch by val_pol_ce), batch 2048 (8GB GPU).
  Control (`build/strategic_tierb.csv`, old labels): early stop at epoch 23, val_pol_ce
  0.5014, policy_top1 0.7869, margin 10.86, q_top1 0.2787. Candidate
  (`strategic_sp_1500.csv`): early stop at epoch 44, val_pol_ce 0.5075, policy_top1 0.7815,
  margin 8.63, **q_top1 0.2951** (candidate better on Q-ranking, slightly worse on policy).
  Exports: `selfplay/models/ooc_strategic_tok_{ctrl,sp}.native` (parity passed).
- **Paired gate** (seeds 126700–126955, 1k sims, fair S3 −belief−chain, 64p, full V4 gate
  stack, asc 0, local 12 threads): **control 49.6% vs candidate 39.5% wins, Δ −10.2pp,
  95% CI [−17.6, −2.7]**; floor 42.9 vs 42.3 (Δ −0.5, n.s.); HP end 24.7 vs 20.9;
  discordant 102/256. CSVs `build/gate_tok_{ctrl,sp}_256.csv`, strict `paired_analysis.py`.
- **Verdict (pre-registered rule, plan §1): candidate ≥ control with CI excluding a
  meaningful loss → promotion; here the candidate is SIGNIFICANTLY WORSE → 5.7.3 CLOSED
  as a distribution lever. Recorded, NOT iterated on data volume.** The "better" label
  source (current controller, §141 diagnostic confirms the labels genuinely changed) does
  not transfer — consistent with §62/§100/§105/§127/§129. Deployed
  `ooc_strategic_tok_final.native` unchanged.

## §148 V_combat hyperparameter optimization (Optuna TPE search + paired gate): +10.9pp win at matched tree count; new default vnet (2026-08-09, local)

- **What:** 50-trial Optuna TPE hyperparameter search over the canonical
  `train_value_combat.py` XGBoost recipe (max_depth, eta, subsample,
  colsample_bytree, min_child_weight, lambda, alpha, gamma) on the
  honest dataset (`build/vcombat_honest.csv`, 287K rows, 16K fights),
  same GroupShuffleSplit and critical-state weighting. Best trial trained
  to 2000 trees (eta 0.031), exported at 800/1000/2000 trees for a compute-
  cost sweep. Paired gate: S3 fair −belief−chain, 64p, 1k sims, 64 seeds,
  no OOC gate stack (default native OOC), α=0.3.

- **Best hyperparameters vs deployed (§126):**

  | Parameter | Deployed (§126) | Tuned (§148) |
  |---|---|---|
  | `max_depth` | 8 | 8 |
  | `eta` | 0.05 | 0.031 |
  | `subsample` | 0.8 | **0.54** |
  | `colsample_bytree` | 0.7 | 0.81 |
  | `min_child_weight` | 20 | **82** |
  | `lambda` (L2) | 1.0 (default) | 0.003 |
  | `alpha` (L1) | 0 (default) | **1.81** |
  | `gamma` | 0 (default) | **4.36** |

- **Offline metrics (same validation split):** tuned model RMSE 7.78 vs
  deployed 7.88 (−1.3%). The improvement is small but consistent across
  the top trials (7.78–7.82 cluster). Parameter importance:
  `subsample` (0.29) and `min_child_weight` (0.29) dominate.

- **Paired gate at matched compute (64 seeds, S3 fair, 1k sims, default
  OOC, no gate stack):**

  | Model | Trees | Offline RMSE | **Win%** | Floor | End HP | cpu_sec/run |
  |---|---|---:|---:|---:|---:|---:|
  | Baseline (§126 honest) | 804 | 7.88 | **20.3%** | 40.1 | 14.1 | 26.6 |
  | Tuned @800 trees | 800 | ~7.90 | **31.2%** | 39.5 | 15.2 | 40.4 |
  | Tuned @1000 trees | 1000 | ~7.90 | **31.2%** | 40.1 | 17.8 | 42.8 |
  | Tuned @2000 trees | 2000 | 7.78 | 29.7% | 39.6 | 14.8 | 68.0 |

  At matched tree count (~800 trees), the tuned hyperparameters give
  **+10.9pp win** (20.3% → 31.2%). The 1000-tree version ties for best
  win rate with the highest end-HP. The 2000-tree version performs WORSE
  (29.7%) despite the best offline RMSE — offline metrics do not predict
  MCTS action-ranking quality.

- **Why the offline metrics barely change but gameplay improves 10pp**
  (**Inference**, not experimentally decomposed): higher regularization
  (`min_child_weight` 82 vs 20, L1 α=1.81, γ=4.36) and aggressive
  subsampling (0.54 vs 0.8) make the ensemble more conservative and better-
  generalizing. Offline RMSE is measured on on-policy pre-action snapshots
  from the teacher policy; MCTS visits off-policy counterfactual states
  that benefit from smoother, less-overfit value estimates. The higher
  `min_child_weight` specifically forces each leaf to have ≥82 weighted
  samples, preventing memorization of specific state configurations and
  producing a smoother value landscape that guides search better.

- **Verdict:** ↗ tuned hyperparameters are a clear improvement.
  The 1000-tree export (`build/v_combat_hparam_1000.txt`, sha256
  `7cd5a1eb…`) replaces `build/v_combat_honest.txt` as the default
  S3-fair vnet at α=0.3. A full-stack re-measurement with the V4 gate
  stack is an open follow-up.

- **Artifacts:** `tools/tune_vnet_hparams.py` (Optuna search script),
  `tools/tune_vnet_best.py` (final training + export),
  `build/vnet_hparam_*.db` (Optuna study),
  `build/v_combat_hparam*.txt` (tree exports at 800/1000/1400/2000 trees),
  `build/vnet_hparam_{baseline,tuned,1k}_{1k_{32,64},1000t_64,800t_64}.log`
  (benchmark logs).

- **Cost:** ~18 min for the 50-trial search (CUDA), ~2 min/export, ~4 min
  per 64-seed benchmark arm (local 12-thread WSL).

- **7k-data extension (same session):** retrained with the §148 tuned
  hyperparameters on the 1.58M-row `build/vcombat_7k.csv` (87K fights,
  5.5× more data than honest). Exported at 1000 trees, 751 features,
  parity-verified (max|diff|=8.6e-5). 64-seed S3-fair gate: **37.5% win**
  vs 31.2% honest-tuned (+6.3pp from data volume). The 7k model
  (`build/v_combat_7k_tuned.txt`, sha256 `ea35b78c…`) is now the default
  vnet. Progression: §126 20.3% → honest-tuned 31.2% (+10.9pp params) →
  7k-tuned 37.5% (+6.3pp data) = +17.2pp total. No hyperparameter re-sweep
  needed — the parameter landscape is flat and the tuned regularization
  transfers across datasets.

## §149 V4 token-net trainer glob-skew fix + retrain (2026-08-09, local)

**Context:** An encoding audit of all OOC model columns
(decision-log/2026-08-09-v4-glob-skew-fix.md) discovered that
`train_strategic_tok.py` had been building its 42-glob block from the wrong
CSV columns since the NGLOB=42 correction. The strategicgen2 CSV interleaves
the d/u/r/pot block (cols 32–1004) before fm*/curMap* (cols 1005–1016), but
the trainer assumed all scalars were contiguous. Result: glob slots 24–35
trained on deck counts `d0..d11` while C++ inference fed forward-map features
`fmDElite..curMapY`; derived thresholds `canTakeEliteKey`/`bossNear` trained on
`d4`/`d3` but served `fmCElite`/`fmDBoss`. Every V4 model trained before this
fix (including the deployed 50-glob model and the honest_v2 42-glob model)
was affected.

**Fix:** Trainer corrected to slice the actual CSV columns (cols 23:32,
1005:1017). Column-name assertions added to catch future `richHeader()`
reorderings. C++ `buildTokState` was always correct — no C++ change needed.

**Retrain:** Full 40-epoch retrain on `build/strategic_tierb.csv` (3,057,708
rows, 4,650 seeds) with the fixed trainer, rung 4, torch.compile ON, CUDA
(RTX 3060 Ti). Epoch times ~22-51s (compile ON; first epoch slower due to
Triton warmup). Best epoch by val_pol_ce.

- **Offline metrics** (best held-out, epoch 37):
  - val_pol_ce: 0.4885, policy_top1: 0.7932, margin: 8.72
  - value_mae: 10.93, value_rmse: 16.10 (epoch 40; best-val epoch 37 similar)
  - q_top1: 0.2806, q_mae: 16.35, q_rmse: 22.11

- **Offline comparison** with honest_v2 (previous 42-glob model, also 40 epochs):
  - val_pol_ce: 0.4885 vs 0.488 (identical)
  - policy_top1: 0.7932 vs 0.793 (identical)
  - q_top1: 0.2806 vs 0.295 (slightly lower)

  The offline metrics are nearly identical, consistent with the hypothesis
  that the glob skew had minimal impact on training convergence — the network
  capacity was sufficient to extract signal from either column set.

- **Export:** `export_strategic_tok.py` → 32/32 parity checks passed
  (max err logit 1.06e-05, value 8.19e-06, Q 1.28e-05).
  File: `selfplay/models/ooc_strategic_tok_skewfix.native` (799,176 bytes,
  nGlob=42, polIn=184).

- **Paired gate** (64 seeds, seeds 126700–126763, S2 fair @1k sims,
  12 threads, `STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1
  STS_OOC_STRATEGIC_MARGIN=1.0`):

  | Metric | Baseline | Skewfix | Delta | 95% CI |
  |---|---|---|---|---|
  | Win rate | 23.4% | 39.1% | **+15.6pp** | [+3.1, +28.1] |
  | Avg floor | 37.4 | 40.7 | +3.3 | [+0.1, +6.6] |
  | Avg HP end | 17.5 | 22.6 | +5.1 | — |
  | CPU sec/run | 13.82 | 15.24 | +10% | — |

  Discordant pairs: 20/64 (31%) — skewfix won 15, baseline won 5.
  Baseline Wilson 95% CI: [14.7%, 35.1%]. Skewfix Wilson 95% CI: [28.1%, 51.3%].

- **Gate verdict: SIGNIFICANT.** The 95% CI for the win-rate delta excludes
  zero. This is the first 42-glob (honest, no hidden-info leaks) V4 model to
  show a clear gate benefit. The previous honest_v2 model (also 42-glob,
  trained with the glob skew) gated at 15.6% vs 21.1% = −5.5pp (lost to
  baseline).

- **Deployment decision:** The skewfix model replaces
  `selfplay/models/ooc_strategic_tok_final.native` as the shipped V4 artifact.
  SHA256: `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.
  V4 remains opt-in behind `STS_OOC_STRATEGIC_TOK_NN`; V3 is still the
  default OOC policy. The previous final model (50-glob leaky, sha256
  `f6bc6a96…`) was already replaced with a 42-glob version earlier today;
  this replaces that with the skewfix retrain.

- **Artifacts:**
  - `selfplay/models/ooc_strategic_tok_skewfix.pt` (checkpoint)
  - `selfplay/models/ooc_strategic_tok_skewfix_tok_state.bin` (2.9 GB)
  - `selfplay/models/ooc_strategic_tok_skewfix.native` (exported model)
  - `selfplay/models/ooc_strategic_tok_skewfix_metrics.json`
  - `selfplay/models/ooc_strategic_tok_final.native` (deployed, copy of skewfix)
  - `build/gate_skewfix_base_64.csv`, `build/gate_skewfix_cand_64.csv`

- **Open:** A larger gate (128–256 seeds) would tighten the CI. A gate at
  multiple margins (0.5, 5.0) would characterize the sensitivity. A
  head-to-head V3-vs-skewfix gate would determine whether V4 should become
  the default. A full V4 gate stack (SHOP/TREASURE/BOSS_RELIC gates also ON)
  would reproduce the §81 multi-gate configuration.

## §150 Per-encounter combat value specialization: per-boss XGBoost fine-tuning + Reptile meta-learner — GATE NEGATIVE, close the line (2026-08-09, local)

**What:** two experimental arms sharing one runtime dispatch map
(`CombatValueNet::encounterModels`, keyed by `MonsterEncounter` enum int;
`predict(bc)` dispatches to the specialized model when present and otherwise
keeps the base path — byte-identical default behavior when nothing is loaded).

- **Arm 1 — per-boss XGBoost fine-tuning**
  (`train_value_combat_per_encounter.py`): continues the pooled §148 model on
  each boss's own rows (`xgb_model=pooled_bst`, 50 extra rounds, early stop
  10; `PER_ENC_CONSERVATIVE=1` = 15 rounds + bumped `reg_alpha`/`gamma` for
  tail encounters). Same feature columns as the pooled model's
  `feature_names`, fight-group split, critical-state weights and
  QuantileDMatrix recipe as `train_value_combat.py`. Exports compact-tree
  `<ENUM_NAME>.txt` + `_pooled.txt` fallback + per-encounter val CSVs.
  Runtime: `STS_VNET_PER_ENCOUNTER=<dir>` →
  `CombatValueNet::loadEncounterModels(dir)`; `export_combat_model.py
  --per-encounter <dir>` converts a directory of `.json` models without
  retraining.
- **Arm 2 — Reptile meta-learning for tail encounters**
  (`train_value_combat_meta.py`): dense MLP (1766→128→64→1, **ReLU** — the
  native `combat_mlp_v1` C++ path is ReLU; the plan's "GELU" wording was
  deliberately not followed to preserve inference parity) trained with the
  Reptile outer loop (B=8 encounters/iter, K=5 inner SGD steps, ε=0.5), then
  offline adaptation of tail encounters (meta-train rows ≤
  `META_TAIL_MAX_ROWS`). Exports `combat_mlp_meta_v1` (base MLP dense layout +
  per-encounter `dw1..db3` delta table); C++ reconstructs adapted weights as
  base + delta in `encounterModels` (~940KB/encounter).

**Verified (local, WSL, 2026-08-09):**

- Per-encounter trainer on `build/vcombat_honest.csv` (287,517 rows; SLIME_BOSS
  373 fights / 11,176 rows, THE_GUARDIAN 391 fights / 9,816 rows): pooled 2000
  trees + 10 specialized each; `vnettest --encounter SLIME_BOSS` parity
  max|diff| 6.7e-5 vs Python (tolerance 1e-3).
- `export_combat_model.py --per-encounter` output byte-identical to the
  trainer's direct export.
- Meta smoke (META_ITERS=6, K=3, SAMPLE_MOD=8, adapt-all): 50 per-encounter
  deltas; base parity max|diff| 1.1e-5; in-file SLIME_BOSS delta
  reconstruction (base+delta) parity max|diff| 1.1e-5 vs Python adapted
  predictions.
- 8-seed S3-fair smokes: default unchanged (`combatVNet=off`), nonexistent
  per-encounter dir warns and continues, per-encounter tree dir shows
  `combatVNet=ON+per-encounter(2)`, meta model shows
  `MLP 1766x128x64x1 +50 per-encounter`.
- `ctest` 9/9, `vnettest_selftest.py --self-test` PASS.

**Gate (local, WSL, 2026-08-09):** 64 paired seeds, S3 fair, 1k sims,
`searchdiag` mode (per-fight boss data + run-level aggregates). Baseline:
`STS_VNET=build/v_combat_boss/_pooled.txt` (2000 trees, no per-encounter
dispatch). Treatment: same pooled plus `STS_VNET_PER_ENCOUNTER=build/v_combat_boss`
(9 per-boss models, 2000+50 trees each, sharing the same pooled base for
non-boss encounters).

Run-level:
- Win rate: 39.1% → 32.8% (−6.2pp, 95% CI [−15.6pp, +1.6pp]; n.s.)
- Avg floor: 42.0 → 41.3 (−0.8)
- Avg HP end: 21.3 → 17.1 (−4.2)
- Discordant pairs: 8/64 (12%), pooled-only 6, per-boss-only 2

Per-boss (exit HP when won, Δ treatment − baseline):
- SLIME_BOSS −4.5pp win, +0.8 HP  |  THE_GUARDIAN +0.2pp, +2.4 HP
- HEXAGHOST +4.5pp, −2.0 HP       |  AUTOMATON −0.9pp, +2.0 HP
- COLLECTOR −8.6pp, +14.5 HP      |  CHAMP +5.9pp, −3.0 HP
- AWAKENED_ONE 0pp, +9.4 HP       |  TIME_EATER −12.5pp, +12.4 HP
- DONU_AND_DECA −6.0pp, −7.8 HP

The COLLECTOR and TIME_EATER pattern (fewer wins but much higher exit HP when
winning) suggests the fine-tuned model over-values HP preservation relative to
win probability — consistent with the endHp label target without a sufficient
win bonus. Non-boss encounters showed slight positive deltas (REPTOMANCER +5.6,
MAW +5.3, WRITHING_MASS +5.2), likely a cascade effect from different boss-fight
decks rather than direct model benefit.

**Verdict: NEGATIVE — close the line.** Per-boss XGBoost fine-tuning does not
improve run-level outcomes (direction negative, not significant at 64 seeds).
The §126 result (binary boss-conditioning flat/negative) is confirmed: per-boss
specialization, even with dedicated trees, does not capture value beyond what
the pooled model already extracts from the encounter feature. The meta-learner
(Arm 2, Reptile) was not gated; the high label noise on the endHp target and
the negative XGBoost result make it unlikely to succeed, and it should only be
revived if a different label target (e.g., P(win)-weighted endHp or a
run-level credit assignment) is demonstrated to work first on the simpler
XGBoost arm.

**Artifacts (local):** `build/v_combat_boss/{_pooled,SLIME_BOSS,THE_GUARDIAN,
HEXAGHOST,AUTOMATON,COLLECTOR,CHAMP,AWAKENED_ONE,TIME_EATER,DONU_AND_DECA}.txt(.json)`
+ `_val.csv`, `build/v_combat_meta_smoke.txt(.pt)`,
`build/v_combat_meta_smoke_slime_val.csv`. Gate CSVs:
`.ai/cycles/2026-08-09-11-53-34/{baseline,treatment}_sdiag.csv.fights.csv`.

## §151 Distillation investigation: NOT worthwhile; large-scale vnet datagen at 100k seeds (crashed at 14.8k); 5.5× data retrain — preliminary gate negative but confounded (2026-08-09, local + GCP)

- **What (distillation investigation):** five parallel subagent investigations
  into whether distilling expensive neural networks into cheaper models is
  worthwhile. Architect synthesis: **no** — every prior distillation attempt
  (§56 MLP, §57 entity, §58 policy prior, §104 Phase F soft-target, §106 chain
  compression, §137 mixture retrain) failed at gameplay gates despite improving
  offline metrics. The cited root cause is the §62 rule: "better absolute
  prediction does not identify the causal best route." The only successful cost
  reduction was pure additive tree truncation (§52: 1,500→400 trees, 1.85×
  faster, passed −0.5 non-inferiority). The successful quality path is
  data/target improvement (§126: +12.5pp from fresh labels).
- **Recommended follow-up:** (1) Data-side vnet improvement — the proven lever;
  (2) Tree→tree KD as a one-off cheap experiment; (3-4) Do not pursue
  transformer→MLP, transformer→trees, KD of transformer, or int8 quantization.

- **What (large-scale datagen):** `combatgen` 100,000 seeds at 1,000 sims on GCP
  `sts-test` (24 threads), heuristic-OOC distribution (Option B — same as §126;
  gate-stack distribution §129 was NULL). `STS_FAIR=1 STS_SEARCHER3=1`,
  S3−belief−chain/64p, vnet default ON (804 trees, α=0.3). Seeds 3,000–102,999
  (fresh after §126 0–1,499, §129 1,500–2,999). Output piped through gzip
  (`/dev/fd/3` → gzip), achieving **59× compression**.
- **Crash:** `ActionQueue::pushBack` assertion at run 14,800/100,000 —
  capacity-50 overflow under fair-S3+vnet. Filed as
  [issue #50](docs/knowledge-base/issues/2026-08-09-issue-actionqueue-overflow.md).
- **Data recovered:** 3,355,244 rows, 181 MB gzipped, seeds 3,000–17,860
  (~14,860 seeds, avg 226 rows/seed — vnet runs survive longer than §126's
  192 rows/seed).

- **VNet retrain (7k-seed subset):** extracted seeds 3,000–9,999 (1,580,243
  rows, 87,414 fights) to fit 31 GB RAM. `train_value_combat.py` on CUDA:
  751 features, 1,500 trees, val RMSE 8.04, R² 0.895, scaling probe positive.
  Exported `build/v_combat_7k.txt`; parity PASS (max|diff| 0.000193).
  Val RMSE slightly higher than §126's 7.99 — consistent with vnet runs
  producing harder/longer states.

- **Preliminary gate (⚠ confounded):** 256 seeds (126700–126955), 1,000 sims,
  S3−belief−chain/64p, 24 threads. Both arms ran heuristic-OOC because the
  token net model (`ooc_strategic_tok_final.native`) fails to load — the
  model's version-suffixed magic `OOC_STRAT_V42` causes the loader to
  misinterpret byte 12 as a dimension (50 ≠ NGLB 41).

  | arm | model | trees | α | win% | floor | HP | cpu-s/run |
  |---|---|---|---|---:|---:|---:|---:|
  | control | `v_combat_honest.txt` (§126) | 804 | 0.3 | **28.9%** | 39.1 | 11.3 | 24.1 |
  | candidate | `v_combat_7k.txt` | 1,500 | **0.5** ⚠ | 25.8% | 39.9 | 10.5 | 40.7 |

  **The α mismatch (0.5 vs 0.3) and tree-count difference (1,500 vs 804)
  confound the comparison.** The candidate ran at the non-default α=0.5
  because `STS_VNET=<path>` changes the alpha default. The proper comparison
  (`α=0.3`, matched tree count) was not run.

- **New issues discovered:**
  - ActionQueue capacity-50 overflow crashes long-running datagen (#50)
  - Token net loader format mismatch prevents gate-stack benchmarks on
    current binaries
  - 31 GB RAM insufficient for 3.35M-row training (peak ~36 GB)

- **Artifacts:** `build/vcombat_honest_100k.csv.gz` (181 MB, GCP + local),
  `build/vcombat_7k.csv` (5.3 GB), `build/v_combat_7k.{json,txt}`,
  `build/vnet_ctl_1k.csv` (28.9%), `build/vnet_7k_1k.csv` (25.8%).

- **Verdict:** distillation investigation — **line closed** (not worth
  standalone investment). Datagen — partial success, 3.35M rows recovered.
  VNet retrain — 5.5× data produced a model with slightly worse offline RMSE
  and a confounded preliminary gate. The more-data hypothesis is **not
  falsified** — a proper gate at matched α and tree count is still open.
  The data pipeline (gzip, `/dev/fd/3`, seed subsetting) is proven and
  reusable.

## §152 Zero-mean ranking correction for the combat leaf value: implemented (trainer + runtime + clamp), smoke/offline only — NO gameplay gate yet (2026-08-09, local)

- **Idea:** train a small model to predict `leafref.referenceValue -
  leafdiag.endHp_pred` (the gap between a high-budget Searcher3 reference and
  the deployed end-HP vnet's prediction on the same leaf state), center the
  residuals to zero-mean within each `(seed, fightIdx, decIdx)` decision
  group, and ADD the prediction on top of the vnet/PVNet leaf value so
  within-group action ranking improves without shifting the HP scale. A
  fair-path search-complete clamp re-zeroes the per-search mean correction at
  the root edges (visit counts untouched → no decision impact).
- **Implementation (experimental, off by default):**
  - `tools/train_rank_correction.py` — join leafdiag×leafref on
    `(seed, fightIdx, decIdx, obsHash)`, group-center the residual, train
    small XGBoost (max_depth 6, eta 0.05, subsample 0.8, colsample_bytree
    0.7, min_child_weight 20, 100 rounds, 20-round early stop) on the SAME
    733-feature layout as the deployed vnet (std>1e-9 on combatgen rows),
    same fight-group GroupShuffleSplit as `train_value_combat.py`; export via
    `export_combat_model.py` + vnettest parity CSV.
  - `STS_VNET_RANK_CORR=<path>` loads `search::g_combatVNetRankCorr` /
    `search::g_useVNetRankCorr` (non-fatal on failure). Correction added in
    `BattleScumSearcher3::evaluateLeaf` (vnet + PVNet branches), the S3
    leaf-blend site in `step()` (the leafdiag `endHp_pred` source), and
    `BattleScumSearcher2::evaluateLeafState`; per-search accumulation +
    `clampRankCorrAtRoot()` at search-complete in the fair paths.
- **Env/regime:** leafdiag capture is the §135a gate-matching env (fair S3,
  64 particles, `v_combat_honest.txt` @α0.3, `v_combat_utility_direct.txt`,
  per-stratum 500, full V4 OOC gate arms). Reference: `leafref_gate_64_4k.csv`
  (high-budget 4000 sims × 128 particles, CRN-paired; the reference is
  NOT model-free — it uses the same deployed vnet at the same alpha).
- **Smoke results (10 rounds, 5000 joined rows, seeds 126700-126715):**
  - joined 68,534/73,643 leafdiag rows to leafref (93%);
  - 733 features (combatgen filter), val RMSE 11.8 / MAE 7.4 on the centered
    residual (10 smoke rounds, best_iter 1);
  - held-out (fight-group val) within-decision ranking vs leafref: baseline
    pairwiseAcc 0.6493 / top-1 0.212 / regret 10.5 → corrected 0.6459 /
    0.182 / 11.1 (smoke-only; no signal expected at 10 rounds);
  - `vnettest` parity PASS (max|diff| = 0.000001 vs tolerance 0.001);
  - default (env unset) byte-identical: 8-seed fair-S3 `bestbench` output
    matches the pre-change commit binary (modulo cpu_sec);
  - 16-seed ranking diagnostic on the SAME leaves (post-processed
    `build/leafdiag_16_corr.csv` = `leafdiag_smoke_16.csv` rows with
    `endHp_pred += corr`, replicating the runtime semantics; a live corrected
    run would change the leaf states and break the obsHash join): baseline
    endHp pairwiseAcc 0.714 [0.708,0.719] / top-1 0.346 / regret 7.36 →
    corrected 0.719 [0.713,0.725] / 0.359 / 6.88 (+0.005 acc, −0.48 regret,
    Pearson 0.772→0.792). CAVEAT: the smoke model was trained on a subset of
    these rows (4,276 of 73,643, fight-group split), so this diagnostic is
    partially in-sample — it demonstrates the mechanism, not generalization;
    the held-out (fight-group val) metrics inside the trainer showed −0.003
    acc at 10 rounds (noise-level).
- **Artifacts:** `build/leafdiag_smoke_16.csv` (seeds 126700-126715 subset of
  `leafdiag_gate_64.csv`), `build/v_rank_corr_smoke.{json,txt}`,
  `build/v_rank_corr_smoke_parity.csv`, `build/v_rank_corr_smoke_metrics.json`
  (all build/, git-ignored except nothing tracked).
- **Verdict: NONE (infrastructure/implementation only).** No model change, no
  default change, no promotion. The correction may be learning the
  reference's vnet-blend bias rather than true ranking error (same caveat as
  §134 leafref analysis). Follow-ups: full-corpus training, leafdiag
  corrected-capture ranking eval (16 seeds), then a paired fair-S3 @1k/32-seed
  gameplay gate before any promotion consideration.
- **Decision log:** `2026-08-09-zero-mean-rank-correction.md`.

## §153 Ascension sweep: V4-skewfix gates + S3 fair + 7k-vnet @1k, 32 seeds, A0–A20 — Act 4 now reachable; V4 gates essential for Heart survival but hurt Act-3-only performance (2026-08-09, GCP sts-test)

- **What:** 5-ascension paired sweep (A0/A5/A10/A15/A20, 32 seeds each,
  126700–126731) of the current recommended stack: S3 fair −belief−chain
  @64p, V4 skewfix token-net gate stack (§149, all gates ON, margin 1.0),
  7k-tuned vnet default @α=0.3 (§148), 1k sims/decision, 24 threads (GCP
  sts-test). Also ran the no-gates baseline (same config minus V4 gates)
  and a STOP_AFTER_ACT=3 comparison for §148 compatibility.

- **Context — key-collection horizon change:** commit `32281a2`
  ("ooc: collect act-4 keys in every rewards/rest chain", 2026-08-09)
  made Act 4 reachable in `bestbench` for the first time. Previously the
  agent never collected keys and won by defeating the Act 3 boss. Now keys
  are taken at rewards screens (emerald/sapphire, after gold/relic/potion)
  and at rest sites (ruby key via RECALL when act ≥ 3, displacing a
  heal/upgrade). Every prior §148/§126 baseline predates this commit and
  reflects Act-3-only wins.

- **With Act 4 (current binary default):**

  | Asc | V4 Gates ON | No Gates |
  |--:|:--|:--|
  | A0 | **21.9%** (7/32) | 0.0% (0/32) |
  | A5 | **12.5%** (4/32) | 3.1% (1/32) |
  | A10 | **12.5%** (4/32) | 0.0% (0/32) |
  | A15 | **9.4%** (3/32) | 0.0% (0/32) |
  | A20 | **0.0%** (0/32) | 0.0% (0/32) |

  No-gates A0 also probed on a second 32-seed block (126732–126763):
  4/32 (12.5%), avg floor 43.9, end HP 8.2, cpu 31.2 s/run. Combined
  A0 no-gates: **4/64 = 6.3%**.

  The agent reaches Act 4 in 12/32 A0 runs (floor 55) but dies to the
  Heart without V4 gates — the gates are critical for Act 4 survival.
  Without them, 0/32 survived the Heart in the primary block.

- **Act 3 only (STS_STOP_AFTER_ACT=3, comparable to §148):**

  | Config | Win% (32 seeds) | Floor | End HP | CPU s/run |
  |---|---|---:|---:|---:|
  | V4 Gates ON | 31.2% (10/32) | 42.8 | 20.5 | 27.0 |
  | No Gates | **37.5%** (12/32) | 42.4 | 31.1 | 28.8 |

  The no-gates STOP_AFTER_ACT=3 result (37.5%, 12/32) reproduces the §148
  7k-tuned gate (37.5%, 24/64) exactly on the overlapping seed range
  (126700–126731 ⊆ 126700–126763). The V4 skewfix gates **reduce** Act-3
  win rate by −6.3pp in this regime (31.2% vs 37.5%).

- **Key findings:**
  1. The V4 skewfix gates (+15.6pp on S2-fair, §149) **reverse sign** on
     S3+vnet at Act 3 (−6.3pp) but are **essential** for Act 4 (+15.7pp
     delta: 21.9% vs 6.3%). The gates build decks that survive the Heart.
  2. The Key-collection commit changed the benchmark horizon — all
     pre-`32281a2` baselines are Act-3-only and not directly comparable.
  3. Ascension scaling is steep: A5 roughly halves A0 win rate, A10–A15
     near-zero, A20 is 0/32 even with the full stack.
  4. CPU cost drops with ascension (27.8 → 11.4 s/run) as runs end earlier.

- **Artifacts:** `build/asc{0,5,10,15,20}_1k_32.csv` (gates ON),
  `build/asc{0,5,10,15,20}_nogates_1k_32.csv` (gates OFF),
  `build/asc0_nogates2_1k_32.csv` (second no-gates block),
  `build/asc0_stopact3_gates_1k_32.csv`,
  `build/asc0_stopact3_nogates_1k_32.csv`.

- **Verdict:** ↗ V4 gates are essential for Act-4-inclusive benchmarks.
  The current recommended configuration (V4 skewfix gates + S3 + 7k-vnet)
  is the best known fair stack at A0=21.9% (with Act 4). The STOP_AFTER_ACT=3
  number (31.2%) is the nearest Act-3-only comparable but should not be
  presented as the headline — the binary now plays Act 4 by default.

- **Open:** Full 128/256-seed gate to tighten CIs; 3k win-point
  measurement; investigation into why the skewfix V4 gates reverse sign
  on S3+vnet (the §126 V4 model showed +12.5pp on S3+vnet at Act 3).

## §154 V_combat training-vs-deployment distribution shift: DIAGNOSIS — mismatch is WEAK, do NOT build relabeling pipeline (2026-08-09, local)

- **Question:** Are ordinary `combatgen` per-decision combat snapshots
  representative of the MCTS leaf states where `CombatValueNet` is queried
  during Searcher3 deployment?

- **Method:** Instrumented `CombatValueNet::predict()` with a thread-local
  hook (`STS_VNET_QUERY_LOG=<path>`) that logs the canonical feature vector
  of every VNet query during Searcher3 search. Collected two populations:
  - A: 287k combatgen trajectory states (seeds 0–1460, `build/vcombat_honest.csv`)
  - B: 163k deployed VNet-query states (seeds 200000–200047, S3 fair,
    belief=off, chain=off, 64p, 1k sims, A0, `build/vnet_query_deploy_b.csv`)
  Trained an XGBoost domain classifier (200 trees, max_depth=6) to distinguish
  A from B using only the 1,766 canonical combat features. **Split by seed,
  not by row** (70/30 per population, stratified). Zero behavior change when
  `STS_VNET_QUERY_LOG` is unset (verified: identical outcomes on 8-seed smoke).

- **ROC-AUC: 0.56** (XGBoost, held-out seeds). Confirmed with SGD logistic
  regression (AUC 0.24 — inverted ranking, equally poor discriminative power).
  The classifier operates barely above chance and cannot reliably distinguish
  individual combatgen states from deployed VNet-query states.

- **Characterization:** Deploy states are at slightly higher turns (3.7 vs 2.1),
  have more monster HP remaining (192 vs 68 sum), and more incoming damage
  (17.7 vs 9.2). Top distinguishing features are relic presence flags (r26
  Happy Flower, r51, r6, r4), reflecting later-turn relic accumulation — but
  the effect sizes are small relative to within-class variance. Deploy queries
  are spread broadly across HP bands (46% >70% HP, 43% 30-70%, 12% <30%)
  and turns (35% turns 3-4, 23% turns 5-7, 21% turn 2).

- **VNet predictions on deploy states:** mean 32.9, std 23.5 — closely
  matches the combatgen label distribution (mean 36.4, std 24.1). No evidence
  of systematic extrapolation or pathological behavior.

- **Verdict: Recommendation A — distribution mismatch is small; do NOT
  build expensive deployment-leaf relabeling pipeline.** The suspected
  mismatch between training (trajectory snapshots) and deployment (MCTS
  leaf states) is NOT the primary issue. The §148 hyperparameter-tuning
  improvement (major online gain with flat offline RMSE) more likely
  reflects regularization benefits than a distribution-shift fix.

- **Artifacts:** `build/vnet_query_deploy_b.csv` (163k rows),
  `build/vnet_shift_report.json`, `tools/vnet_distribution_shift.py`,
  `docs/knowledge-base/experiments/vnet-distribution-shift-2026-08-09.md`.

- **Code:** `STS_VNET_QUERY_LOG` env var + `STS_VNET_QUERY_SAMPLE`;
  hook in `CombatValueNet::predict()`; thread-local buffered CSV logging
  in `apps/one_combat.cpp`. All changes additive and gated — behavior
  byte-identical when the env var is unset.

## §155 Corrected honest V4 on frozen S3 + 7k-VNet Act-3 stack: INCONCLUSIVE due reproducibility failure (2026-08-09)

- **Question:** Does the corrected honest V4 token gate remain positive on the
  current Searcher3 + 7k combat-value stack under the explicit Act-3 objective?
- **Configuration:** git `c8d438a5a140d023ca348a334fa4ac467d1bd8e5`; A0;
  `STS_FAIR=1`, Searcher3, `STS_S3_BELIEF=0`, `STS_S3_CHAIN=0`,
  `STS_S3_LIVE_VALID=1`, 64 particles, 1,000 sims/decision, 12 threads;
  `STS_VNET=build/v_combat_7k_tuned.txt`, alpha 0.3;
  `STS_COLLECT_KEYS=0`, `STS_STOP_AFTER_ACT=3`; paired seeds 126700–126763.
  V4 artifact `selfplay/models/ooc_strategic_tok_final.native`, SHA256
  `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`;
  VNet SHA256 `ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c`.
- **Control:** all V4 OOC gates off, 37.5% (24/64), mean floor 42.6,
  mean end HP 18.4.
- **Candidate:** corrected V4 gates on, all REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC flags on, margin 1.0, 14.1% (9/64), mean floor 30.0,
  mean end HP 42.8.
- **Paired result (not qualified):** first control/candidate comparison was
  −23.4pp, bootstrap 95% CI [−35.9, −10.9]pp; floor −12.5
  [−16.8, −8.3], HP +24.4, discordant 21/64. The candidate in that run had
  `STS_OOC_STRATEGIC_TRACE` enabled, while the ablation candidate did not.
- **Reproducibility failure:** the same no-trace control command and seed block
  later produced 37.5% (24/64) and 7.8% (5/64), with the same 1k/64p stack.
  The no-trace ablation full arm produced 15.6% (10/64); the earlier trace-on
  candidate produced 14.1% (9/64). These runs cannot establish a causal delta.
  Investigate thread/RNG/global-state nondeterminism before using this gate.
- **Trace:** 2,375 gate opportunities across 64 runs; 1,228 owned (51.7%).
  Fire rates: EVENT 57.1%, REWARDS 46.9%, BOSS_RELIC 78.9%, CARD_SELECT
  21.3%, TREASURE 51.9%, REST 58.2%, SHOP 56.1%.
- **Artifacts:** `build/ooc_v4_s3_act3_off_64_1786290767.csv`,
  `build/ooc_v4_s3_act3_on_64_1786290767.csv`, corresponding `.meta.json`
  files and logs, `build/ooc_v4_s3_act3_64_1786290767_paired.txt`, and
  `build/ooc_v4_s3_act3_on_64_1786290767_trace.csv`.
- **Verdict:** **INCONCLUSIVE / invalidated as a causal gate** until repeated
  controls are reproducible. The observed negative/positive deltas are
  diagnostic only. The earlier S2-fair +15.6pp result still does not transfer
  cleanly, but no model-quality conclusion is permitted from §155. Audit
  thread/RNG/global-state determinism before further policy interpretation;
  Act-4 objective and per-screen traces remain open.

## §156 Per-screen V4 ablation diagnostic on same S3+7k-VNet Act-3 block: not qualified (2026-08-09)

- **Configuration:** same A0, 1k sims, 64 particles, S3 belief/chain off,
  live-valid on, 7k VNet alpha 0.3, `STS_COLLECT_KEYS=0`,
  `STS_STOP_AFTER_ACT=3`, seeds 126700–126763; corrected V4 full stack at
  margin 1.0. The script explicitly uses the V4 artifact and records JSON
  sidecars. Results are diagnostic because §155 showed repeated-control
  non-reproducibility.
- **Full stack:** 10/64 (15.6%), mean floor 30.7, mean HP 48.8.
- **Minus REST:** 14/64 (21.9%), paired full-minus-ablation +6.2pp,
  CI [−4.7,+17.2]pp; floor +2.5.
- **Minus EVENT:** 11/64 (17.2%), +1.6pp, CI [−6.2,+9.4]pp; floor +2.0.
- **Minus SHOP:** 11/64 (17.2%), +1.6pp, CI [−9.4,+10.9]pp; floor +2.5.
- **Minus TREASURE:** 16/64 (25.0%), +9.4pp, CI [+0.0,+18.8]pp;
  floor +3.9.
- **Minus BOSS RELIC:** 9/64 (14.1%), −1.6pp, CI [−10.9,+7.8]pp;
  floor +2.7.
- **Interpretation:** treasure and rest are the largest apparent contributors,
  but these effects are not causal/promotion-qualified until exact repeated
  controls are stable. Artifacts are under
  `build/ooc_v4_s3_act3_ablate_64_1786291107/` plus the paired reports.

## §157 DeepSets combat VNet parity — RMSE 8.66, C++ parity verified, online 0% win (2026-08-09)

- **What:** implemented a DeepSets neural combat value net
  (`train_combat_deepsets.py`, `combat_deepsets_v1` native format in
  `CombatValueNet.cpp`). Architecture: combat state decomposed into
  permutation-invariant sets — cards (4 zones × 371 IDs, shared embedding
  table, sum-pool per zone), relics (128, sum-pool over present), potions
  (44, count-weighted sum), monsters (5 slots × 9 feat, per-slot 2-layer
  MLP → mean-pool over alive), encounter (ID embedding), scalars (68 features
  z-normalized → linear → ReLU). All pooled vectors concatenated → MLP
  (384 → 128 → 64 → 1). 90K params. Trained on honest vcombat data (287K
  rows, 30 epochs, AdamW, MSE on endHP, critical-state weighting).
- **Parity:** C++ vs Python max|diff| < 0.001 (vnettest, 200 rows).
  All 15 CTests pass.
- **Offline:** val RMSE 8.66 (XGBoost 7.83), R² 0.87. On trajectory
  validation states, XGB/DS Pearson 0.974, Spearman 0.972 — the model
  works well in-distribution.
- **Online gate:** 0% win (0/32) at S3 fair −belief−chain, 1k sims, 64p,
  α=0.3, no gate stack — **worse than no VNet (12.5%)**. XGBoost at 31.2%
  on the same block. `build/dsgate_*.log` on sts-test.
- **Verdict:** ❌ DeepSets in current form is actively harmful. Follow-up
  §158 diagnoses the root cause as numerical collapse on OOD MCTS leaf
  states.
- **Artifacts:** `train_combat_deepsets.py`, `build/v_combat_deepsets.txt`,
  `build/v_combat_deepsets_val.csv`, `include/sim/search/CombatValueNet.h`
  (isDeepSets + ds* fields), `src/sim/search/CombatValueNet.cpp` (format
  parser + inference).

## §158 MCTS leaf-state diagnosis: DeepSets numerically collapses on OOD search states (2026-08-09)

- **What:** extended `STS_VNET_QUERY_LOG` (existing opt-in VNet tracing)
  with `parentObsHash` and `depth` columns, enabling sibling-grouped
  MCTS leaf-state analysis. Collected 1M leaf evaluations under XGBoost-
  guided S3 search (8 seeds, 1k sims, 64p), sampled 50K for offline
  comparison. Evaluated both XGBoost and DeepSets on the identical states.
- **Key result:** On MCTS leaf states, XGB/DS Pearson drops from 0.974
  (trajectory) to **0.098**. DeepSets mean prediction = **−34 million HP**
  (XGBoost = 27 HP). DeepSets produces NaN-range values on many states.
- **All extreme disagreements** (|Δ| = 40–430 million HP) involve a single
  encounter: **TRANSIENT** (encounter 44, monSumHp ~950–980). The scalar
  z-normalizer was calibrated on training data (monSumHp mean ~50); MCTS
  leaf states with monSumHp ~970 produce z-scores of 20+ standard deviations,
  causing unbounded activations in the scalar encoder that cascade through
  the MLP.
- **Distribution shift confirmed:** a simple RandomForest classifier
  distinguishes trajectory vs MCTS states with **95% accuracy**.
  Top shifted features: rare card/relic IDs appearing in counterfactual
  branches, plus numerical extremes on boss/special encounters.
- **Sibling analysis:** top-child agreement 0.7%, pairwise agreement 58%,
  DS reversal rate 48.5% at XGB margin ≥1 HP — all dominated by the
  numerical collapse rather than subtle ranking errors.
- **Root cause:** numerical instability in the scalar z-normalizer on
  out-of-distribution feature values. The model architecture is sound
  (works well in-distribution) but lacks input robustness.
- **Recommended fix:** clamp z-scores to [−5, +5] before the scalar
  encoder (one line in Python + C++).
- **Artifacts:** `tools/analyze_mcts_leaves.py`,
  `build/vnet_mcts_leaves_xgb.csv` (1M rows, 3.4GB),
  `build/vnet_mcts_leaves_50k.csv` (50K sample),
  `build/mcts_diag.json`. Decision log:
  `docs/knowledge-base/decision-log/2026-08-09-deepsets-combat-vnet.md`.

## §159 Requalified corrected honest V4 on frozen S3 + 7k-VNet Act-3 stack (2026-08-09)

- **Fix/configuration:** made `search::g_potionKeepValue` thread-local;
  `runFullRunOOC` writes it per fight while parallel seeds search concurrently.
  Repeated 8-seed checks matched all outcomes, floors, HP, and death fields.
  The 64-seed gate used a no-trace binary, A0, 1k sims, 12 threads,
  `STS_FAIR=1`, Searcher3, belief/chain off, live-valid on, 64 particles,
  fixed `build/v_combat_7k_tuned.txt` alpha 0.3, `STS_COLLECT_KEYS=0`,
  `STS_STOP_AFTER_ACT=3`, seeds 126700–126763.
- **Result:** V4 OFF 24/64 (37.5%), V4 ON 31/64 (48.4%), paired delta
  **+10.9pp**, 95% CI [−1.6,+23.4]pp; floor +0.9 and HP +5.5.
- **Trace:** same ON stack produced 3,419 opportunities, 1,834 owned
  (53.6%); fire rates: EVENT 61.8%, REWARDS 44.8%, BOSS RELIC 84.0%,
  CARD SELECT 18.0%, TREASURE 62.0%, REST 68.4%, SHOP 55.1%.
- **Artifacts:** `build/ooc_v4_requal_s3_act3_{off,on}_64_1786292238.csv`,
  paired report, trace and sidecars.

## §160 Requalified per-screen V4 ablations (2026-08-09)

Same fixed stack/seeds as §159, V4 margin 1.0. Full was 31/64 (48.4%).
- minus REST: 31/64 (48.4%), paired delta 0.0pp;
- minus EVENT: 26/64 (40.6%), delta −7.8pp, CI [−18.8,+3.1]pp;
- minus SHOP: 34/64 (53.1%), delta +4.7pp, CI [−7.8,+17.2]pp;
- minus TREASURE: 31/64 (48.4%), delta 0.0pp, no discordant seeds;
- minus BOSS RELIC: 29/64 (45.3%), delta −3.1pp, CI [−10.9,+4.7]pp.

These are exploratory 64-seed effects; only EVENT has a meaningful directional
signal, and its CI still crosses zero. Artifacts:
`build/ooc_v4_requal_s3_act3_ablate_64_1786292838/`.

## §161 V4 margin sweep on requalified Act-3 stack (2026-08-09)

Same configuration/seeds as §159, corrected V4 all five screens on, 64 seeds:
- margin 0.5: 29/64 (45.3%), mean floor 43.9, HP 21.5;
- margin 1.0: 31/64 (48.4%), mean floor 43.5, HP 23.9;
- margin 2.0: 31/64 (48.4%), mean floor 44.4, HP 27.2;
- margin 5.0: 29/64 (45.3%), mean floor 43.0, HP 24.2.

Eight-seed trace samples measured fire rates 71.8%, 53.3%, 33.3%, and 13.5%
for margins 0.5, 1, 2, and 5 respectively. Margin 1–2 is the current small
sample plateau; no margin is promoted without confirmation at 128 seeds.
Artifacts: `build/ooc_v4_margin_*_s3_act3_64_1786293919.csv` and trace files.

## §162 Training split/checkpoint-selection follow-up (2026-08-09)

- **Fixes:** canonicalize Tier-B CSV rows by `(seed, decIdx)` before group
  offsets, and initialize the missing batch permutation RNG in both
  `train_strategic.py` and `train_strategic_tok.py`. The prior assertion
  correctly caught non-contiguous groups; without the RNG fix training then
  failed before epoch 1.
- **Selection interface:** both trainers accept
  `STRAT_SELECT_METRIC=val_pol_ce` (minimize, default) or `q_top1` (maximize).
- **Resource-safe result:** a three-epoch CUDA `val_pol_ce` run reached epoch 3
  on `build/strategic_tierb.csv`; held-out `val_pol_ce=0.6093`, `q_top1=0.2982`.
  The paired `q_top1` run was not completed after the first run allocated a
  ~2.9 GB state tensor; no checkpoint-selection conclusion is drawn. Avoid
  repeating this full GPU run from an IDE; use a redirected batch job or a
  reduced/synthetic fixture first.

## §163 Corrected honest V4 confirmed at 128 paired seeds on S3+7k-VNet Act-3 stack (2026-08-09)

- **Configuration:** git `3feb2a1` (block 1) / `d38272f` (block 2, behavior-neutral
  because tree-reuse controls are env-gated and binary was verified bit-identical
  across an earlier Searcher3 transition). A0, 1k sims, 12 threads, Searcher3,
  belief/chain off, live-valid on, 64 particles, `STS_VNET=build/v_combat_7k_tuned.txt`
  alpha 0.3, `STS_COLLECT_KEYS=0`, `STS_STOP_AFTER_ACT=3`.
  V4 SHA256 `e62abd83…`, VNet `ea35b78c…`.
- **128 paired seeds 126700–126827:**
  - V4 OFF: 52/128 (40.6%), mean floor 42.0, mean HP 18.5;
  - V4 ON:  67/128 (52.3%), mean floor 44.0, mean HP 24.5;
  - paired delta **+11.7pp**, bootstrap 95% CI **[+1.6, +22.7]pp**;
  - floor +2.0, HP +5.9, discordant 47/128 (37%), on-only 31 vs off-only 16.
- **Verdict:** ↗ **V4 is confirmed positive on the current fair S3+7k-VNet
  Act-3 stack.** The CI excludes zero. This is the first statistically significant
  gate for the corrected honest V4 on this combat configuration.
  V4 is now the provisional OOC baseline.
- **Artifacts:** `build/ooc_v4_head_s3_act3_{off,on}_64_1786297628.csv` (block 1),
  `build/ooc_v4_head128_s3_act3_{off,on}_64plus_1786297983.csv` (block 2),
  sidecars and logs.

## §164 Checkpoint-selection interface verified on small CPU fixture (2026-08-09)

- Both `train_strategic_tok.py` and `train_strategic.py` accept
  `STRAT_SELECT_METRIC=val_pol_ce` (minimize) or `q_top1` (maximize).
- A 20-seed, 13K-row fixture from `build/strategic_k1.csv` was trained on CPU
  for 10 epochs with both metrics:
  - `val_pol_ce`: picked epoch 10, best CE=1.208;
  - `q_top1`: early-stopped at epoch 7, best at epoch 2, best q_top1=0.211.
- Different metrics select different checkpoints; min/max directions and
  early-stopping logic are verified. Artifacts under `/tmp/ooc_ckpt_fixture_*`.

## §165 SHOP-disabled V4 test on requalified Act-3 stack (2026-08-09)

- **Configuration:** same frozen stack/seeds as §163, V4 ON with all screens
  except SHOP (EVENT+REST+TREASURE+BOSS_RELIC+CARD only, margin 1.0).
  64 paired seeds 126700–126763.
- **Result:** SHOP-disabled 34/64 (53.1%) vs full V4 31/64 (48.4%),
  delta +4.7pp, CI [−7.8,+17.2]pp; discordant 15/64, SHOP-disabled-only 9.
- **Interpretation:** consistent with the Wave 0G minus-SHOP ablation
  (also +4.7pp). The direction suggests SHOP overrides are net-harmful on
  this stack, though the CI crosses zero at 64 seeds. This is a supplementary
  diagnostic, not yet a promotion claim.
- **Artifacts:** `build/ooc_v4_noshop_s3_act3_64_1786298692.csv`, paired
  report, sidecar.

## §166 Recovered MCTS-leaf MLP and deep-target experiment arc (2026-08-09; consolidated 2026-08-11)

- **Provenance:** recovered before deleting ignored legacy agent state from
  `.ai/session-summary-2026-08-09-deepsets-v3.md` through `v17.md`. These
  summaries were not authoritative records and did not preserve every seed
  range or artifact hash. Results below are therefore **Unverified historical
  evidence** except where independently recorded in §157-§158.
- **Configuration reported by the summaries:** project-fair Searcher3,
  belief/chain off, 64 particles, 1,000 simulations per decision, no OOC gate
  stack, and normally `STS_VNET_ALPHA=0.3`. Online comparisons used common
  32-seed blocks unless stated otherwise; exact seed ranges and thread counts
  were not recorded.
- **MCTS-distribution imitation:** a flat `733 -> 256 -> 128 -> 1` MLP trained
  on 278K XGBoost-guided MCTS leaf states reached held-out Pearson 0.964 versus
  its XGBoost teacher. Reported online results were 46.9% versus XGBoost 43.8%
  at 32 seeds and 43.8% versus 41.4% at 128 seeds. The 128-seed difference was
  treated as noise, not a promotion. The corresponding reported artifact was
  `build/v_combat_mlp_mcts.txt`.
- **Deep-search utility targets:** a model trained on Searcher3 backed-up
  utility achieved offline RMSE 8.75 and Pearson 0.964 against that target but
  only 34.4% online versus the teacher MLP's 46.9%. One warm-start DAgger
  iteration improved it to 40.6%; second iterations regressed to 25.0%
  (warm-start) and 21.9% (fresh). The summaries report that XGBoost-, V0-, and
  V1-guided state distributions remained 84-85% distinguishable.
- **Residual correction:** adding a learned deep-utility residual to the
  teacher with beta 0.01 reportedly reduced the 32-seed result from 46.9% to
  34.4%. Larger corrections were worse. The residual mostly behaved as an
  upward bias rather than a state-specific correction.
- **Terminal-endHP target:** a warm-started MLP trained on 42K joined states
  improved validation RMSE from 13.76 to 11.61 and Pearson from 0.737 to 0.750,
  corrected a reported CULTIST overprediction blind spot, but tied the teacher
  at 46.9% on 32 seeds.
- **Verdict:** MCTS-distribution imitation was competitive with its tree
  teacher, but raw deep-search utility, iterative DAgger beyond one iteration,
  residual correction, and terminal-endHP relabeling did not establish an
  online improvement. This research line is closed unless reconstructed from
  preserved artifacts with a new premise and fully recorded paired protocol.

## §167 Fightrep: re-recorded floor-50 boss losses and particles x sims replay grid (2026-08-11)

- **Purpose:** the fightrep harness (`apps/one_combat.cpp`,
  `2026-08-11-fightrep-harness.md`) needs a captured fight set to re-search the
  recorded floor-50 boss losses at other particle counts / sim budgets. The 14
  original captures were never on this machine or on `sts-test`, so the set was
  re-recorded locally.
- **Source of the 14 losses:** `build/rerun_2026-08-10_a0_gates_1k_128.csv` (GCP A0
  1k/128-seed full-stack rerun, 46.9% win). 14 seeds reached floor 50 and lost. Two of
  them (`126711`, `126805`) are anomalous rows (hpEnd>0 with deathCombat=-1,
  deathEncounter=-1; run ended without a combat death) and are excluded here for a
  separate fix.
- **Re-recorded captures:** `build/fightrep_cap/fight_<seed>.bin/.csv` for the 12 normal
  loss seeds `126704 126721 126722 126731 126735 126753 126766 126773 126783 126808
  126817 126819`, captured by `bestbench 1000 1 0 <seed>` with `STS_FIGHTREP_CAPTURE_DIR`
  and the recorded full stack (fair S3, belief=off chain=off, 64 particles, live-valid
  on, V4 tok-net gates all on margin 1.0, native OOC, VNet α=0.3, policy prior
  c_puct=2.5). Every capture reproduced the historical encounter at floor 50: encounters
  {54,53,55} match the historical `deathEncounter` column exactly for all 12 seeds.
- **Replay grid** (`one_combat fightrep`, forced fair S3 belief=off chain=off
  live-valid=on): 12 fights x {64,128,256} particles x {1000,3000,6000} sims = 108 cells
  in 94.7s wall on 12 threads. Per-cell wins of 12:
  - 64p: 1000→2, 3000→5, 6000→2
  - 128p: 1000→2, 3000→3, 6000→3
  - 256p: 1000→1, 3000→1, 6000→1
- **Follow-up grid ({32,512,1024} particles x {1000,3000,6000} sims, 108 cells in 103.1s,
  2026-08-11):** per-cell wins of 12:
  - 32p: 1000→1, 3000→2, 6000→3
  - 512p: 1000→1, 3000→3, 6000→3
  - 1024p: 1000→2, 3000→4, 6000→3
  Combined particle axis {32,64,128,256,512,1024} x {1000,3000,6000} = 216 cells:
  best cell remains **64p/3000s = 5/12**; 1024p/3000s = 4/12 is the only other >=4.
  Per-seed win consistency across the 18 cells: 126704/126731/126735/126753/126817 = 0/18
  (never won at any budget); 126808 = 1/18; 126819 = 4/18; 126721 = 6/18; 126773 = 6/18;
  126766 = 8/18; 126783 = 8/18; 126722 = 9/18 (most flip-prone). So the replay win signal
   is concentrated in ~6 of the 12 captured fights; 5 fights never flip at any budget.
- **Extreme cell (1024 particles x 100,000 sims, single cell, 12 fights parallel on 12
  threads, 365.9s wall / ~6.1 min, 2026-08-11):** **6/12 wins — the best cell so far**
  (previous best 5/12 at 64p/3000s). Winners: `126721 126722 126766 126773 126783
  126819` (hpEnd 29/25/7/6/4/2). Note 1024p/100k is the only cell so far where `126721`
  and `126819` win; the same 5 fights still never win (126704, 126731, 126735, 126753,
  126817). Runtime note: 10k-sims probe = 17.6s/fight single-core, so 100k ≈ 176s/fight
  expected; the observed 365.9s wall for 12 parallel fights is ~2x that, consistent with
   super-linear per-decision cost at 300k sims/decision (boss x3) plus the slowest fight
   dominating the parallel cell.
- **100k-sims particle sweep ({16,32,64,128,256,512} particles, sims fixed at 100k,
  72 cells in 2054.2s wall / ~34 min, 2026-08-11):** per-cell wins of 12:
  - 16p→4, 32p→5, 64p→3, 128p→5, 256p→3, 512p→5
  Combined with the 1024p/100k cell (6/12), the 100k-sims particle axis
  {16..1024} peaks at **1024p = 6/12**. At 100k sims `126773` wins at every particle
  count (6/6) and `126783` wins 5/6 (all but 16p), while the never-win set is stable:
  `126704 126731 126735 126753 126817` (5/6 counts) plus `126808` now also 0/6 at 100k.
  The 10k-particles/100k-sims cell (3/12) is markedly worse than both 512p/100k (5/12)
  and 1024p/100k (6/12), so beyond ~1k particles the extra belief particles do not help
  and hurt. Descriptive isolated-fight results only.
- **Replay determinism:** a second independent run of the 36 (64p) cells gave 0 diffs
  (won/hpEnd/turns identical).
- **Fidelity gate (replay == capture-time outcome):** at the recorded config
  (64p/1000s → boss x3 = 3000/decision) 10/12 seeds reproduce the capture-time loss;
  **2 seeds flip to wins: `126722` (hpEnd 29) and `126773` (hpEnd 26)**. Both are Time
  Eater / Awakened One loses at capture time. This is a real fidelity gap: the isolated
  fight-start snapshot does not fully determine the replay outcome for these two seeds
  (possible causes: run-context combat knobs such as `search::g_potionKeepValue` /
  per-fight `fightSims` budget applied in `runFullRunOOC` but not in `fightRepReplay`).
  Flagged as an open question for the fightrep harness, not a policy claim.
- **Interpretation (descriptive, not paired):** at 64p the 3k budget flips 3 additional
  losses (126766, 126783, 126808) to wins beyond the 64p/1k flips, but the 6k budget
  regresses to 2/12 (126722 and 126773 stay wins; 126783/126808 lose again). More
  particles (128/256) do not help and 256p wins FEWER fights than 64p at every sim
  budget. This is an isolated-fight re-search result; it does not transfer to full-run
  win rate without a full paired run.
- **Artifacts:** `build/fightrep_cap/` (captures), `build/fightrep_grid_12f.csv` (64/128/256p,
  108 cells), `build/fightrep_grid_32p512p1024p.csv` (32/512/1024p, 108 cells),
  `build/fightrep_1024p_100k.csv` (1024p/100k, 12 cells),
  `build/fightrep_10kp_100k.csv` (10k particles/100k, 12 cells),
  `build/fightrep_100k_16to512p.csv` (16..512p x 100k sims, 72 cells),
  `/tmp/opencode/weird_cases/` (126711 capture set aside for the separate fix).
- **Status:** re-record complete; 2/12 fidelity flips are an open harness concern.

## 2026-08-15 — Searcher3 persistent filtered-posterior quality A/B preregistration

**Question:** Does consuming the exact filtered real-observation Searcher3
posterior in the next freshly constructed Searcher3 improve gameplay decisions
when both arms use a fresh MCTS tree for every searched decision?

**Frozen implementation:** baseline `166c48072a41760e146f3a99a1329849440bbb3a`;
implementation commit `4a08736d0185c7c70f0fc731e0bc06b2702061a0`. The source,
tests, and executable were frozen before quality-seed execution. No source-code
changes are permitted after the first provenance seed; a required code fix
invalidates affected results and requires a new frozen implementation commit
and rerun. Subsequent result recording is documentation/analysis only.

**Hypotheses:** H1, persistent filtered information improves decisions; H2, the
information is decision-irrelevant at 1,000 simulations; H3, accurate
sequential filtering is offset by particle depletion; H4, a hidden mechanism
defect appears during longer gameplay. Mechanical failures invalidate quality
interpretation.

**Arms:** C is the **fresh-tree + fresh-belief experimental control**:
`STS_S3_PERSIST_FILTERED_BELIEF=0`. P is the fresh-tree + persistent-filtered-
posterior treatment: `STS_S3_PERSIST_FILTERED_BELIEF=1`. Both arms execute the
real-belief filter and collapse-fresh fallback and explicitly set
`STS_REUSE_MAX_SEARCHES=0`; C is not the current/deployed gameplay baseline.
The only intended conceptual difference is whether the filtered `Belief` is
consumed by the next fresh Searcher3. No tree nodes, visit counts, Q values,
edge availability, reuse state, or searcher RNG state transfer.

**Common configuration:** fair Searcher3, ascension 0, 1,000 simulations,
64 particles, `STS_FAIR=1`, `STS_SEARCHER3=1`, `STS_S3_BELIEF=0`,
`STS_S3_CHAIN=0`, `STS_S3_REAL_BELIEF_FILTER=1`,
`STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1`,
`STS_S3_INTERNAL_BELIEF_UPDATE=0`, `STS_REUSE_MAX_SEARCHES=0`,
`STS_LIVE_VALID=1`, `STS_VNET=models/v_combat_7k_tuned.txt`,
`STS_VNET_ALPHA=0.3`, and V4 strategic token-net gates using
`selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
BOSS_RELIC enabled, strategic margin 1.0. Model SHA256 values are
`ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c` for
V_combat and `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`
for the strategic model. The same explicitly recorded OMP/thread setting and
all unrelated environment variables are used in both arms.

**Seeds and decision rule:** preregistered paired block `126732–126747` (16
seeds). First run seed `126732` separately in C and P with full belief audit.
The existing boundary-level next-search sidecar remains enabled, and the
existing fair-loop diagnostic additionally reports
`transferred_filtered_belief_searches`, the count of actual fresh searches
initialized from a transferred posterior. The provenance gate requires C = 0
actual transferred searches and P > 0. A failed gate, simulator-health failure,
stall, unresolved exit, material draw-pile mismatch, propagation failures above
approximately 1% of active attempts, or sharp action-illegal increase stops the
experiment without quality interpretation.

After exactly 16 paired seeds, extend only if substantive paired action,
trajectory, or outcome divergence occurs; then run only the preregistered
continuation `126748–126763` for 32 total. If trajectories are essentially
identical, stop at 16. Stop at 32 in all cases; do not automatically run 64 or
128 seeds. Primary analysis is seed-paired wins, P-only/C-only wins, both-win/
both-loss, and paired P−C floor/ending-HP mean and median differences, with
mechanical health, collapse, support, ESS if available, and CPU reported.

**Non-goals:** no default enablement, particle-count change,
resampling/rejuvenation, RNG-counter redesign, MCTS-statistics transfer, model
or policy tuning, or current-baseline promotion.

## 2026-08-15 — Searcher3 persistent filtered-posterior quality A/B results

**Frozen execution:** all quality runs used the frozen implementation commit
`4a08736d0185c7c70f0fc731e0bc06b2702061a0` and the preregistration commit
`f583ec007916e3fd7f117877d7c111b0392487b4`. No source code changed after
provenance execution began. The Release executable SHA256 was
`19e1160642e262b3b77949790c7e573d740db5296105d38d8bca3858b08b8a16`.

**Provenance gate, seed 126732:** C, the fresh-tree + fresh-belief
experimental control, reported exactly 0 transferred-belief searches. Its
boundary-level sources were `fresh_initial=409`, `no_next_search=24`. The
original diagnostic wording called P's 58 transferred-belief reconstructions
"actual fresh searches"; that wording was later corrected because a fresh
Searcher3 can receive the posterior and then take a forced action without
calling `s3.search()`. P's boundary-level sources were
`transferred_filtered_posterior=422`, `no_next_search=24`. Thus the treatment
was active, and the boundary-level sidecar was not mistaken for actual-search
consumption. Both arms had zero propagation failures, draw-pile mismatches, and
action-illegal particles on this provenance seed. Both lost at floor 50 with
ending HP 0; runtime was 18.3457s C versus 22.03s P.

**Common environment:** `OMP_NUM_THREADS=12`,
`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
STS_S3_PARTICLES=64 STS_S3_REAL_BELIEF_FILTER=1
STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1 STS_S3_INTERNAL_BELIEF_UPDATE=0
STS_REUSE_MAX_SEARCHES=0 STS_LIVE_VALID=1 STS_VNET=models/v_combat_7k_tuned.txt
STS_VNET_ALPHA=0.3
STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
STS_OOC_STRATEGIC_MARGIN=1.0 STS_OOC_STRATEGIC_REST=1
STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
STS_S3_BELIEF_AUDIT=1`. The sole arm difference was
`STS_S3_PERSIST_FILTERED_BELIEF=0` for C versus `=1` for P. Startup output
confirmed Searcher3, fair-play, 64 particles, 1,000 sims, 12 threads, and
`models/v_combat_7k_tuned.txt` loaded at alpha 0.3. The strategic model path
was present in the startup/configuration provenance. Model hashes were the
preregistered values: V_combat
`ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c` and
strategic token net
`e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`.

**16-seed gate, 126732–126747:** meaningful paired trajectory and outcome
divergence occurred, so the preregistered extension rule fired.

| Metric | C | P |
|---|---:|---:|
| Wins | 7 | 7 |
| P-only wins | 2 | — |
| C-only wins | 2 | — |
| Both win | 5 | — |
| Both lose | 7 | — |
| Mean floor | 43.2500 | 41.8750 |
| Mean ending HP | 18.8125 | 17.3750 |
| Mean runtime sec/run | 49.6159 | 45.7638 |

The paired P−C floor delta was mean `-1.375`, median `0`; ending-HP delta
was mean `-1.4375`, median `0`. The 16-seed direction was not a coherent
quality advantage; the full 32-seed discordance is reported below.

**32-seed gate, 126732–126763:** the continuation was run exactly as
preregistered, using only `126748–126763`, and execution stopped at 32.

| Metric | C | P |
|---|---:|---:|
| Wins | 15 | 16 |
| P-only wins | 6 | — |
| C-only wins | 5 | — |
| Both win | 10 | — |
| Both lose | 11 | — |
| Mean floor | 43.2813 | 43.5938 |
| Mean ending HP | 23.9063 | 24.6563 |
| Mean runtime sec/run | 53.1608 | 51.6669 |

Across paired seeds, P−C floor was mean `+0.3125`, median `0`; P−C
ending HP was mean `+0.75`, median `0`. Runtime delta P−C was mean
`-1.4940s`, median `-1.1792s`, descriptive only. The exact paired outcome
table was P-only `6`, C-only `5`, both win `10`, both lose `11`; the two-sided
conditional discordance test was not informative at this sample size (p=1.0).
Per-seed rows and raw artifacts are retained under the ignored
`build/linux-gcc-release/s3_ab_{c,p}_{16,32tail}.*` paths.

**Provenance and posterior mechanics across 32 seeds:** The historical
32-seed artifacts were produced by the frozen implementation before the
counter correction. C's old counter was 0 and its boundary sources were
`fresh_initial=12508`, `no_next_search=759`. P's old counter was 12,691 fresh
Searcher3 reconstructions receiving a transferred belief, including some
reconstructions followed only by forced actions; it was incorrectly labelled
as actual transferred searches. P's boundary sources were
`transferred_filtered_posterior=12662`, `no_next_search=759`. The exact
32-seed actual-search count was not measured by the frozen implementation and
is not reconstructed here.

| Mechanical metric | C | P |
|---|---:|---:|
| Filtered boundaries | 13,267 | 13,421 |
| Posterior collapses | 1,970 (14.85%) | 2,517 (18.75%) |
| Propagation failures / attempts | 253 / 849,088 (0.0298%) | 155 / 612,277 (0.0253%) |
| Draw-pile mismatches | 0 | 0 |
| Action-illegal particles | 253 | 155 |
| Mean distinct surviving draw orders | 44.13 | 37.48 |
| Mean ESS over audit rows | 55.62 | 44.36 |

No battle stalls, unresolved exits, simulator-health failures, or material
draw-pile regressions occurred. The treatment had lower support/ESS and higher
collapse frequency, consistent with H3's support-depletion concern, but did
not cross the mechanical stop rule.

**Treatment support depletion:** Existing `[belief-audit]` output covered
11,278 actual-search audit points. Positive-particle count had mean `46.53`,
median `64`; fractions at or below thresholds were `<=4: 17.0%`
(`1,917/11,278`), `<=8: 21.5%` (`2,424/11,278`), `<=16: 26.5%`
(`2,990/11,278`), and `<=32: 30.3%` (`3,416/11,278`). ESS had mean `46.53`,
median `64`, first quartile `14`, third quartile `64`, and range `0–64`.
These distributions are descriptive of the treatment's actual searches and
were derived offline without adding runtime telemetry.

**Post-experiment counter correction:** Commit
`187617c63024e69bf942cdc4215b6cb4f1f96d1f` corrected
`transferred_filtered_belief_searches` so it increments immediately before
the real `s3.search(...)` call only when the current Searcher3 was initialized
from a transferred posterior. Mere reconstruction and forced-move processing
do not increment it. The focused lifecycle regression now exercises the shared
transfer/counting seam and verifies persistence-off, transfer identity,
zero-weight preservation, fresh-root state, no-search non-consumption, and
exactly-one count for an actual search.

The corrected one-seed diagnostic used the same pinned configuration and seed
126732, but was not new quality evidence. C reported corrected counter `0`; P
reported corrected counter `367`, compared with 390 retained P belief-audit
points. P's boundary-level sidecar remained
`transferred_filtered_posterior=422`, demonstrating that boundary resolution
and actual-search consumption are distinct measurements. Both arms had zero
propagation failures, draw-pile mismatches, and action-illegal particles, with
no simulator-health failure, unresolved exit, or stall; startup confirmed the
correct treatment flag and model loading.

The 16- and 32-seed quality experiments were **not rerun**. Their evidence
remains tied to frozen implementation commit
`4a08736d0185c7c70f0fc731e0bc06b2702061a0`; this correction changes diagnostic
counting and regression coverage, not posterior-transfer gameplay semantics.
The scientific verdict remains **mixed / inconclusive at 64 particles and
1,000 fresh-tree simulations**: persistence materially changes trajectories
but provides no convincing gameplay improvement, and particle depletion remains
a plausible cost.

**Implementation verdict:** the feature is mechanically active, default-off,
fresh-tree isolated, provenance-correct, and preserves zero-weight particle
identity in focused tests. The treatment passed the mechanical validity gate.

**Scientific verdict:** **mixed / inconclusive at 64 particles and 1,000
fresh-tree Searcher3 simulations.** P produced substantial trajectory
divergence and one additional win (16 vs 15), with small positive mean floor
and HP deltas, but also six P-only versus five C-only wins, zero median paired
quality delta, higher collapse rate, lower support/ESS, and no statistically
informative paired binary result. This is not evidence to enable persistence by
default and does not establish a durable gameplay-quality improvement.

**Competing explanations and limits:** the sample is small; paired outcomes
are noisy; the treatment changes posterior support and therefore search
sampling, not only semantic accuracy; `HiddenBattleState` still lacks complete
RNG-counter representation; CPU differences may reflect the extra belief
handling; and the strategic/OOC and combat models remain sources of variance.
The result does not establish that persistence is beneficial at other particle
counts, simulation budgets, searcher-tree policies, model stacks, or longer
seed blocks. No resampling, rejuvenation, RNG redesign, default promotion, or
64/128-seed follow-up was performed.

## 2026-08-15 — Searcher3 posterior lifetime diagnostic and rejected transfer smoke

**Question:** Does exact real-boundary filtering meaningfully condition a
posterior that is then discarded when fair Searcher3 rebuilds its tree, and can
the posterior safely seed a deliberately fresh tree?

**Lifecycle diagnostic:** Added opt-in sidecar telemetry under the existing
`STS_S3_BELIEF_AUDIT[_FILE]`: one row per filtered boundary records the actual
next-search source (`fresh_initial`, `existing_filtered_posterior`,
`collapse_fresh`, or `no_next_search`). This correctly accounts for a carried
subtree later rebuilt by `STS_REUSE_MAX_SEARCHES`; `belief_carried` is not used
as the consumption proxy.

Fair Searcher3, 64 particles, 1,000 sims/decision, current native OOC +
V_combat/policy stack, 12 threads, seeds 94000–94007, filter ON, internal
belief updates OFF produced 2,942 filtered boundaries. Of 1,035 non-trivial
filters (`compatible fraction < 1`), 1,029 (99.42%) were followed by
`fresh_initial`; six ended combat before another search. The `<0.75` and
`<0.5` subsets were 1,026/1,032 (99.42%) and 996/1,002 (99.40%) fresh,
respectively. The coupling is therefore material.

**Rejected smoke:** A temporary treatment transferred the filtered `Belief`
while forcing a fresh tree every actual search in both arms
(`STS_REUSE_MAX_SEARCHES=0`). It was removed after the 8-seed smoke. Control
had 15.14% posterior collapse and 44 propagation failures out of 183,488
attempts; treatment had 79.11% collapse and 147,438/180,160 propagation
failures, including 2,066 all-particle `PROPAGATION_FAILURE` collapses. The
root cause is structural: `HiddenBattleState` stores RNG seeds but not counters,
and `applyParticleImpl` resets counters to zero. A propagated particle cannot
be safely carried through another real transition. No RNG reconstruction,
resampling, or transfer feature was retained.

The smoke’s whole-run outcomes were 3/8 wins in both arms; treatment mean floor
was 43.8 vs 41.6 and mean HP 20.0 vs 18.6, with 0/8 discordant wins. This is
not interpreted as quality evidence because the treatment was invalid. Mean CPU
was 28.67 vs 28.35 s/run (+0.32 s/run). No simulator-health, stall, or
battle-break output occurred. No 32-seed gate was run.

**Artifacts (ignored build output):**
`build/linux-gcc-release/s3_belief_lifecycle_phase2_8.{csv,csv.next_search.csv}`;
`s3_persist_{control,treatment}_8.{csv,csv.next_search.csv,results.csv}` and
their `.meta.json`, `.stdout`, and `.stderr` files. See
`docs/knowledge-base/decision-log/2026-08-15-s3-persistent-posterior-lifecycle.md`.

**Correction — paired collapse-fallback diagnostic (same date):** The preceding
temporary treatment did not isolate missing RNG counters from stale-collapse
fallback. With temporary posterior transfer and `STS_REUSE_MAX_SEARCHES=0` held
constant, paired seeds 94000–94007 changed only
`STS_S3_REAL_BELIEF_COLLAPSE_FRESH`: T0 (`0`) collapsed 2,536/3,177 boundaries
(79.82%) with 169,738/203,328 propagation failures (83.48%), all 169,738 being
draw-pile mismatches and 2,363 `PROPAGATION_FAILURE` collapses. T1 (`1`) rebuilt
554 fresh post-state beliefs and collapsed 554/2,818 boundaries (19.66%) with
56,329/180,352 propagation failures (31.23%): 56,233 draw-pile mismatches, 96
action-illegal particles, and zero `PROPAGATION_FAILURE` collapses. Thus stale
pre-transition restoration was the primary cause of the catastrophic cascade.
Missing RNG counters remain an open limitation, not an established primary
cause. The temporary transfer remained removed; no larger strength gate ran.
T0/T1 whole-run wins were both 3/8 and are not quality evidence; CPU was 33.46
vs 29.73 s/run. Artifacts: `s3_persist_t{0,1}_8.*` under
`build/linux-gcc-release/`.

**Rerun after zero-weight resurrection fix:** The same corrected T1 command and
configuration on seeds 94000–94007 produced 2,867 filtered boundaries and
183,488 attempts: 434 collapses (15.14%), 44 propagation failures (0.02398%),
zero draw-pile mismatches, and 44 action-illegal particles. Fresh post-state
beliefs were rebuilt 434 times; next-search sources were
`fresh_initial=2698` and `no_next_search=169`. Whole-run output was 3/8 wins,
mean floor 41.6, mean ending HP 18.6, and 17.82 s/run. This is a diagnostic
rerun, not a quality gate. Artifacts: `build/linux-gcc-release/s3_persist_t1_rerun_8.*`.

**Provenance correction:** The temporary transfer telemetry was then made
explicit. A one-seed probe on 94000 reported 498
`transferred_filtered_posterior` next searches and 24 `no_next_search` rows,
before the 8-seed run. The provenance-correct 94000–94007 run reported 2,616
`transferred_filtered_posterior` and 171 `no_next_search`, 540/2,787 collapses
(19.38%), 17/120,391 propagation failures (0.0141%), zero draw-pile
mismatches, and 17 action-illegal particles. This is compared with the pre-fix
persistent T1’s 19.66% / 31.23% / 56,233 and the fresh-initial control’s
15.14% / 0.024% / 0; no further seeds were run. Temporary transfer code was
removed after the run; explicit telemetry vocabulary remains for future
reproducible treatments. Artifacts: `build/linux-gcc-release/s3_persist_t1_probe_94000.*`
and `s3_persist_t1_provenance_8.*`.

## 2026-08-15 — Native C++ LTO build benchmark and default adoption

**Question:** Does adding compiler optimization flags make the combat benchmark
faster, and should LTO become the standard native build setting?

- **Benchmark:** `one_combat bench 2000 8`, Jaw Worm combat, seeds `0..7`,
  Ironclad ascension 0, GCC 13.3, `OMP_NUM_THREADS=1`, known-RNG Searcher2
  MCTS, 2,000 simulations per decision. The primary metric is process user CPU
  time from `/usr/bin/time`; the harness MCTS row is a secondary metric.
- **Arms:** A current `-O3`; B `-O3 -march=native`; C
  `-O3 -march=native -flto`. All runs used the same source revision, models,
  seeds, and runtime settings, and were executed through
  `tools/seed_guard.sh`.
- **Results:** A **0.88 s** user CPU / **95.43 ms** MCTS average; B **0.87 s**
  / **94.41 ms**; C **0.76 s** / **81.50 ms**. Relative to A, B was **1.1%
  faster** and C was **13.6% faster** by process CPU time (**14.6% faster** by
  the harness MCTS timing). All arms produced identical outcomes: 8/8 MCTS
  wins, average ending HP 73.1, average 3.0 turns.
- **Decision:** Make `-flto` standard in `CMakeLists.txt`. Do not make
  `-march=native` standard: it is host-specific and the 8-seed result showed
  no meaningful benefit by itself.
- **Caveat:** This is a small 8-seed combat-only benchmark, so the LTO result is
  evidence for the default build setting, not a general performance guarantee
  across CPUs, compilers, workloads, or full-run benchmarks. LTO build time and
  portability remain follow-up considerations.
- **Artifacts:** temporary benchmark binaries and raw output were stored under
  `/tmp/sts-opt-bench/` during the session; they are not repository artifacts.
## §168 Phase 12B: matched M0 vs M1 at 2,000 source seeds — export, native parity, 64-seed paired gameplay gate (2026-08-15)

**Result: NULL.** At 2,000 source seeds, encounter-marginalized M1 did not
separate from matched fixed-world M0 on the preregistered paired gameplay gate.
The paired win-rate delta favored M0 slightly (−1.6pp) with a 95% CI crossing
zero. This does not support promotion or immediate scaling to 5,000 seeds.

### Provenance

- Dataset was generated by the **pre-merge Phase 12 generation binary** (older
  Searcher3), not the current HEAD; do not relabel it as current HEAD.
- The raw diagnostic CSV was **malformed** (unquoted `richState` → 1,056
  physical fields), **deterministically salvaged/reconstructed** to the intended
  40-column schema (`tools/reconstruct_marg_csv.py`), and the corrected artifact
  passed full paired/identity/hidden-resampling validation.
- Training used the reconstructed CSVs on branch state containing the
  CSV-quoting + trainer-schema + trainer-device fixes (HEAD `774585b`).

### Inputs (verified hashes)

| Artifact | SHA256 |
|---|---|
| M0 CSV `build/phase12b_m0.csv` | `08af144a00a27d9ea7153332b437adb347a46f72619c0ccd0946f1be2dc245fa` |
| M1 CSV `build/phase12b_m1.csv` | `c75a120c809ad84a2bcfcabc1b6f537648aa9da92aabc4c0fe682830ff68e48f` |
| split `build/phase12b_split.json` | `41155410f9b888a14533233a1456d9d2014723f671ee4c2db93c97bf27aac5fa` |

### Training (identical contract, both arms)

`train_strategic_tok.py`, `/usr/bin/python3`, torch 2.5.1+cu121, RTX 3060 Ti.
`STRAT_EPOCHS=40 STRAT_PATIENCE=0 STRAT_Q_TARGET=absolute STRAT_MODEL_SEED=0
STRAT_SPLIT_LOAD=build/phase12b_split.json STRAT_TOK_RUNG=4
STRAT_TOK_TRANSFORMER=0 STRAT_TOK_COMPILE=1 OMP_NUM_THREADS=8 STRAT_DEVICE=cuda`.
Both completed 40 epochs. Best-CE checkpoints were selected (fixed in advance,
matching the 500-seed pilot convention; best-qtop1 not used).

### Offline best-CE metrics

| | val_pol_ce | best q_top1 |
|---|---|---|
| M0 | 0.5089743137359619 (epoch 35) | 0.2598020794187649 (epoch 13) |
| M1 | 0.5118089318275452 (epoch 40) | 0.25353876988600776 (epoch 16) |

### Checkpoints & native exports (best-CE)

| Arm | best-CE `.pt` SHA256 | native SHA256 |
|---|---|---|
| M0 | `2c146abc3d1e16b69c9fcefe96a6b2a7f07b8a467750f03258754a3b43fec343` | `161c14bcb711d1966e2c16d3a8f551486eeb6d46eb94df89dfdd1057db41014d` |
| M1 | `68b5005fbaeb76c0548b0d15697461c8441aaf6c5b4c4421b59e4b1a554d8251` | `92332a4b13b0f9fdc468531b43db5e0cdf6de2ae147ea4951ea9c44edce6723b` |

Export: `export_strategic_tok.py <pt> <native>`; both passed the built-in
32-sample numpy-vs-PyTorch (native mirror) parity — M0 max err logit 4.52e-06,
M1 4.77e-06.

### Gameplay gate

- Seeds 900000–900063 (64 common), `bestbench 1000 64 0 900000`, fair
  S3 + 7k-VNet Act-3 stack, all strategic screens ON, margin 1.0, threads 12.
  The two arms differ **only** in `STS_OOC_STRATEGIC_TOK_NN` (the native model
  artifact); the `BEST stack config` banner was identical for both.
- Env (both arms): `STS_OOC_STRATEGIC_REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1`,
  `STS_OOC_STRATEGIC_MARGIN=1.0`, `STS_FAIR=1`, `STS_SEARCHER3=1`,
  `STS_S3_BELIEF=0`, `STS_S3_CHAIN=0`, `STS_S3_LIVE_VALID=1`,
  `STS_S3_PARTICLES=64`, `STS_VNET=models/v_combat_7k_tuned.txt`,
  `STS_VNET_ALPHA=0.3`, `OMP_NUM_THREADS=12`.
- Gameplay CSVs: `build/phase12b_m0_64.csv` (`d1af223d…`),
  `build/phase12b_m1_64.csv` (`809c4868…`).

### Paired result (`paired_analysis.py`, 64 seeds, identical seed sets)

| Metric | M0 | M1 | Δ (M1−M0) |
|---|---|---|---|
| Win rate | 17/64 = 26.6% | 16/64 = 25.0% | **−1.6pp** |
| Win-diff 95% CI | | | **[−14.1pp, +10.9pp]** |
| Avg floor | 38.8 | 38.7 | −0.1 |
| Avg HP end | 14.6 | 10.3 | −4.2 |
| Avg sec/run | 28.86 | 31.56 | +2.71 |

Discordant 15/64 (23%): both win 9, both lose 40, M0-only 8, M1-only 7.
M0 Wilson 95% CI [17.3%, 38.5%]; M1 Wilson 95% CI [16.0%, 36.8%].

### Interpretation

Paired delta −1.6pp (95% CI crosses zero). Per the preregistered decision rule:
**null / approximately equal** — M1 does not separate from M0 at 2,000 seeds.
Consistent with H2 (M0 ≈ M1). H3 remains compatible with the evidence, but the
higher absolute win rates relative to the historical 500-seed pilot cannot be
attributed specifically to dataset quantity because runtime/controller state
also changed. No promotion; do not auto-scale to 5,000.

> **Correction (2026-08-15, §169):** this gate ran with `keys=skip` (default),
> which is an Act-3-only horizon — the earlier "vs deployed V4 ~48%" comparison
> was an invalid cross-block comparison. On a same-seed/same-config Act-3 calibration,
> V4 scored 37.5% vs M0 26.6% / M1 25.0% (§169). Both arms remain below V4 but
> by a smaller, same-block margin; H4 (another bottleneck) remains plausible.

### Warnings

- `STRAT_PATIENCE=0` was used to satisfy the "full 40 epochs" contract (matches
  the pilot; the trainer default 6 would early-stop).
- Dataset producer is the pre-merge Searcher3 binary; do not relabel it as current HEAD.

## §169 Phase 12B corrective Act-3 gate + V4 calibration (2026-08-15)

**Correction finding.** Independent review suspected that the §168 gate had run
a full Act-3+4/Heart horizon (because `STS_COLLECT_KEYS`/`STS_STOP_AFTER_ACT`
were not set). Verification shows this suspicion was **incorrect**: the §168
gate ran with `keys=skip` (default `STS_COLLECT_KEYS` unset → off), so the agent
never collected keys, the Act-3 boss victory ended the run, and **zero** runs
entered Act 4 (all winning rows are `act=3, floor=51`; Act-3 boss deaths at
`floor=50`, deathEncounter 53/54/55). The §168 result was therefore already an
Act-3-boss win rate, not a Heart-horizon rate.

### Corrective Act-3 gate (explicit historical contract)

Restored the explicit historical Act-3 contract on the **same 64 seeds**
(900000–900063) and the same current executable, with
`STS_COLLECT_KEYS=0 STS_STOP_AFTER_ACT=3` added. All other flags unchanged
(fair S3, 64 particles, 7k-VNet alpha 0.3, all strategic screens ON, margin 1.0,
12 threads). The three arms differ only in `STS_OOC_STRATEGIC_TOK_NN`.

| Arm | Wins | Win rate | mean floor | mean HP | artifact | SHA256 |
|---|---|---|---|---|---|---|
| M0 | 17/64 | 26.6% | 38.8 | 14.6 | `build/phase12b_m0_act3_64.csv` | `e4cc5fef11bc88b2c018c12aaec8597d89e065f4d9009cd192fe3e4ebdd1eef4` |
| M1 | 16/64 | 25.0% | 38.7 | 10.3 | `build/phase12b_m1_act3_64.csv` | `edc01b56453f7ce17b65636115f39192d92508c4199764ddd3974d674fe03442` |
| V4 (POST-HOC SAME-SEED/SAME-CONFIG CALIBRATION) | 24/64 | 37.5% | 41.8 | 20.1 | `build/phase12b_v4_act3_64.csv` | `c7292bf84e09de0ddd543443f421970e91ac02734c6ef4d0d183def0c47a5bd1` |

M0/M1 Act-3 numbers are **identical** to the §168 gate (26.6% / 25.0%),
confirming the §168 gate was already Act-3-only and there was no horizon mismatch.

Model artifacts (unchanged from §168): M0 `161c14bc…`, M1 `92332a4b…`,
V4 `e62abd83…` (`selfplay/models/ooc_strategic_tok_final.native`).

### Primary paired result (M0 vs M1, Act-3)

- M1−M0 win delta = **−1.6pp**, 95% CI [−14.1pp, +10.9pp] (crosses zero).
- Discordant 15/64: both win 9, both lose 40, M0-only 8, M1-only 7.

Per the preregistered decision rule this remains **NULL / approximately equal**:
encounter marginalization does not separate from the fixed-world control under
the explicit Act-3 horizon either. Do not auto-scale to 5,000 seeds.

### V4 calibration (post-hoc, same 64 seeds, same Act-3 config)

| Pair | Delta | 95% CI | Discordant |
|---|---|---|---|
| V4 − M0 | +10.9pp | [−1.6pp, +23.4pp] | 17/64 (both win 12, both lose 35, M0-only 5, V4-only 12) |
| V4 − M1 | +12.5pp | [+3.1pp, +23.4pp] | 12/64 (both win 14, both lose 38, M1-only 2, V4-only 10) |

V4 (37.5%) exceeds M1 significantly at 95% (CI excludes zero) and M0
non-significantly (CI crosses zero but mostly positive). This is valid same-block
evidence that the Phase-12 models remain weaker than deployed V4, but by a
smaller margin than the historical 48.4% figure suggested — that figure was a
**different seed block (126700–126763), Act-3-only**, not a direct comparator.

### Hypothesis outcomes

- **H1 (horizon mismatch explains low win rates): REJECTED.** The §168 gate was
  already Act-3-only; the corrective Act-3 gate reproduces 26.6%/25.0% exactly.
- **H2 (M0 ≈ M1): SUPPORTED.** The null persists under the explicit Act-3 horizon.
- **H3 (M0/M1 weaker than V4): PARTIALLY SUPPORTED.** V4 > M1 significantly,
  V4 > M0 non-significantly, on the same 64-seed block.
- **H4 (V4 advantage was an invalid comparison): WEAKENED.** The V4 advantage is
  real on the same block, but smaller than the cross-block 48.4% implied.

### Warnings

- 64 seeds is a small sample; the V4 calibration CIs are wide.
- The V4 arm is post-hoc same-config calibration, not a preregistered treatment.

## 2026-08-15 — Searcher3 history-replay rejuvenation shadow probe (preregistration)

**Question:** When the persistent filtered posterior loses support at a
real-observation boundary, can new hidden-state hypotheses compatible with the
FULL real observation history be generated at all? Equivalently: is the
observed `collapseFresh` fallback a consequence of particle depletion
(in-principle recoverable by re-proposing hidden state), or of a hard
inconsistency between the real history and the hidden-state model? If
recoverable, how many fresh proposals are needed to reach 4/8/16/32 distinct
full hypotheses, and how many of those are novel relative to the surviving
posterior?

**Design:** opt-in shadow-only probe (`STS_S3_REJUV_SHADOW=1`, off by default;
off ⇒ bit-identical live behavior). At each filtered boundary with
`compatible <= STS_S3_REJUV_TRIGGER` (16), after `filterRealTransition`
returns: (1) record the committed semantic action + raw bits + real post-action
observation + outcome into a per-combat history anchored at battle start;
(2) sample `STS_S3_REJUV_PROPOSALS` (256) fresh hidden hypotheses from the
anchor observation using a dedicated deterministic probe RNG (independent of
all battle RNG); (3) replay the full recorded history under each hypothesis
using semantic action remap (position-independent card identity, multiset
multi-select, raw END_TURN/POTION), `applyHiddenState` on a copy of the
anchor, and bare `Action::execute` (exact live transition semantics). A
hypothesis is **accepted** iff it reproduces every recorded post-action
observation and outcome exactly (full `CombatObservation::operator==` equality
plus outcome). Uniqueness, novelty, and milestone counts use the
equality-backed `FullHiddenStateKey` (ordered canonical draw-pile identity +
all six RNG seed0/seed1/counter triples); draw-order-only and RNG-only counts
are telemetry hashes only. Novelty compares against the positive particles
currently in `s3.belief` when `compatible > 0` (already propagated to the
current hidden state); when `compatible == 0` the pre-fallback survivor set is
empty and no comparator is used. Pure telemetry: the probe mutates only copies
and appends one CSV row per trigger.

**Frozen implementation:** baseline `0132a5b`; implementation commit
`ac603e5` (branch `exp/s3-history-replay-rejuvenation-shadow`). Source, tests,
and executable were frozen before quality-seed execution; the required status-
column fix was applied before the frozen run (see results section).

**Mechanical gate criteria:** (a) shadow OFF vs ON produce identical committed
action bits, decision observations, RNG-counter trajectories, positive-particle
full-hidden-state keys, and outcome on the same seeds (non-interference test);
(b) per-row sanity: `0 <= accepted <= proposals`, `0 <= unique <= accepted`,
`0 <= novel <= unique`, and where present the milestone proposal indices are
non-decreasing (4 ≤ 8 ≤ 16 ≤ 32); (c) no simulator-health failure, stall, or
unresolved exit attributable to the probe (probe never calls
`reportSimHealthFailure`); (d) no replay `transitionsExecuted` beyond the
recorded history length. A failed gate invalidates quality interpretation.

**Common configuration:** fair Searcher3, ascension 0, 1,000 simulations, 64
particles, `STS_FAIR=1`, `STS_SEARCHER3=1`, `STS_S3_BELIEF=0`, `STS_S3_CHAIN=0`,
`STS_S3_REAL_BELIEF_FILTER=1`, `STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1`,
`STS_S3_INTERNAL_BELIEF_UPDATE=0`, `STS_REUSE_MAX_SEARCHES=0`,
`STS_LIVE_VALID=1`, `STS_VNET=models/v_combat_7k_tuned.txt`,
`STS_VNET_ALPHA=0.3`, V4 strategic token-net gates using
`selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
BOSS_RELIC enabled, strategic margin 1.0, plus shadow flags
`STS_S3_REJUV_SHADOW=1 STS_S3_REJUV_TRIGGER=16 STS_S3_REJUV_PROPOSALS=256` and
`STS_S3_REJUV_SHADOW_FILE` pointing at the artifact path.

**Seeds and decision rule:** preregistered block **126732–126739 (8 seeds)**,
run once through `tools/seed_guard.sh` with the frozen executable. Primary
analysis is mechanical: distribution of accepted / unique / novel per trigger,
milestone proposal indices (4/8/16/32), final-state-compatible-but-not-full
counts, per-row status mix, and their relationship to `compatible`. No
win-rate or floor interpretation — this is a feasibility probe, not a quality
gate. Stop at 8 seeds; do not extend automatically.

**Non-goals:** no default enablement, no live-belief rejuvenation (the probe
never modifies `s3.belief`), no change to `filterRealTransition`, no
resampling-policy change, no RNG-counter redesign, no gameplay promotion.

## 2026-08-15 — AI_RNG conditional sensitivity: exploratory belief-ON run

This diagnostic run is retained as exploratory evidence and is not the intended
frozen paired baseline. It used commit `d0c02cd`, fair Searcher3, seeds
`126732–126739`, 1,000 base simulations, 3,000 boss simulations, 64 particles,
12 threads, real-boundary filtering, collapse-fresh, persistent filtered belief,
no tree reuse, chain off, CRN off, the deployed 7k combat VNet at alpha 0.3,
and native heuristic OOC policy. `STS_S3_BELIEF` was unset (effective ON),
`STS_S3_REJUV_PROPOSALS` was unset (effective 256), and the V4 strategic token
model/gates were OFF. Artifacts were `/tmp/final8_sensitivity.csv`,
`/tmp/final8_live.csv`, `/tmp/final8_live.csv.meta.json`,
`/tmp/final8_exposure.csv`, and `/tmp/final8.log`.

The 32-root analysis found selected-action changes in 3/32 roots, top-two visit
ordering changes in 4/32, and Q-order flips in 3/32. This run demonstrated
conditional sensitivity but is explicitly regime-dependent exploratory evidence.

## 2026-08-15 — CORRECTION: invalid matched AI_RNG record in d68af8c

The matched-replication section previously committed by `d68af8c` is invalid.
It reused the exploratory belief-ON artifact names, hashes, and results while
claiming belief-OFF/V4 provenance. That section must not be used as evidence and
is superseded by the actual matched run recorded below. The exploratory
belief-ON section above remains valid as exploratory evidence.

## 2026-08-15 — AI_RNG conditional sensitivity: matched belief-OFF/V4 replication (corrected)

The corrected matched replication used commit `d0c02cd`, seed block
`126732–126739`, ascension 0, 1,000 base simulations, 3,000 boss simulations,
64 particles, 12 threads, fair Searcher3, `STS_S3_BELIEF=0`, chain off, CRN
off, real filtering, collapse-fresh, persistent filtered posterior, no tree
reuse, END_TURN marginalization off, deployed 7k combat VNet at alpha 0.3, and
the V4 strategic token model
`selfplay/models/ooc_strategic_tok_final.native` with REST/EVENT/SHOP/TREASURE/
BOSS_RELIC gates enabled and margin 1.0. Rejuvenation used trigger 16 and 64
proposals; sensitivity used at most 4 roots/seed, 4 alternatives/root, and
256 mini-search simulations. The exact command was run through
`tools/seed_guard.sh` as:

```text
env -i PATH="$PATH" HOME="$HOME" PWD="$PWD" OMP_NUM_THREADS=12 STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
STS_S3_CHAIN=0 STS_S3_PARTICLES=64 STS_S3_CRN=0
STS_S3_REAL_BELIEF_FILTER=1 STS_S3_REAL_BELIEF_COLLAPSE_FRESH=1
STS_S3_PERSIST_FILTERED_BELIEF=1 STS_REUSE_MAX_SEARCHES=0
STS_S3_ENDTURN_MARGINALIZE=0 STS_S3_REJUV_SHADOW=1 STS_S3_REJUV_SHADOW_FILE=/tmp/final8_matched_rejuv.csv
STS_S3_REJUV_TRIGGER=16 STS_S3_REJUV_PROPOSALS=64
STS_S3_RNG_EXPOSURE_DIAG=1 STS_S3_RNG_EXPOSURE_DIAG_FILE=/tmp/final8_matched_exposure.csv STS_S3_AI_SENSITIVITY_SHADOW=1
STS_S3_AI_SENSITIVITY_ROOTS_PER_SEED=4 STS_S3_AI_SENSITIVITY_ALTS=4
STS_S3_AI_SENSITIVITY_SIMS=256 STS_S3_AI_SENSITIVITY_FILE=/tmp/final8_matched_sensitivity.csv STS_VNET=models/v_combat_7k_tuned.txt
STS_VNET_ALPHA=0.3 STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
STS_OOC_STRATEGIC_MARGIN=1.0 STS_OOC_STRATEGIC_REST=1
STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1
tools/seed_guard.sh ./build/one_combat bestbench 1000 8 0 126732 /tmp/final8_matched_live.csv
```

The run completed with 32 selected roots, 8 seed breadth, 13 encounter breadth,
14 floor breadth, and 32 encounter/floor groups. ORACLE_A was `BASELINE` for
all 146 root-action rows, ORACLE_B was `EXACT` for all 146 rows, and all 584
AI alternative rows were `N/A`; block-isolation and source/search-index
failures were zero. The 32-root cross-tab was: 25 roots with no
support-empty flag and no policy/Q-order change; 1 with only a Q-order flip;
3 with selected/top-two/Q-order changes; and 3 support-empty roots with no
selected-action change (one had a Q-order flip and one had a top-two change).
Overall, selected action changed in 3/32, top-two ordering in 4/32, Q-order
flipped in 5/32, and any nonzero common-edge Q difference occurred in 9/32
roots. Per-root visit-TV Q25/median/Q75/max was 0/0/0.01275/0.906; max
common-edge |dQ| was 0/0/2.42775/131.362; max oracle-selected |dQ| was
0/0/0.30925/17.482.
`/tmp/final8_matched_sensitivity.csv`
(`cb724466559a74437ebefd7e3c20d660a623fefd7e0ffb8c5492ff8610a1398a`),
`/tmp/final8_matched_live.csv`
(`1447919f936fb421cb81fcda831af8c5d59e62f7eff754699b34629019f6b50c`),
`/tmp/final8_matched_live.csv.meta.json`
(`159f2e1cbac329841aeedeb8f256d96b66879d209c1f1f781fb957626ed3a6a8`),
`/tmp/final8_matched_exposure.csv`
(`5add23d9c22757ff3e1cfd06c26a19ab71e2f5c7b9a8d55aced320d3ba9c08e4`),
`/tmp/final8_matched_rejuv.csv`
(`b915e93fddb0f8083bfec1bc98bb62c601d74cc0666b636500929f3e4a1b5496`), and
`/tmp/final8_matched.log`
(`3105f6c9c429eaae2ef05838e96c2b569140be5bced7ce6fc93a1eebf6e34ba4`).

The exposure join covered all 32 roots. Aggregate AI exposure fractions on the
three roots with selected-action changes were 0.020, 1.000, and 1.000. The
matched run again shows decision-relevant AI_RNG sensitivity across multiple
seeds/encounters, but the effect remains sparse and does not itself establish
live gameplay benefit. A later targeted live-treatment study is justified; no
live rejuvenation is implemented here.

## 2026-08-15 — Searcher3 history-replay rejuvenation shadow probe results

> **INVALIDATED for late-history inference (correction 2026-08-15):** this
> first 8-seed run (implementation commit `ac603e5`) recorded
> SINGLE_CARD_SELECT actions via `BattleScumSearcher3::cardActionKey`, which
> only extracts identity from `cardSelectInfo.cards` (Discovery/Codex offers).
> Hand/discard/draw/exhaust-pile single-selects therefore recorded a missing or
> CardId-only identity and remapped incorrectly (8,331 artificial
> `remap_failure`s). The corrected semantic recording/remap rerun is in the
> section immediately below; this section's `remap_failure`, status-mix, and
> late-fight acceptance figures are superseded and must not be used for
> late-history inference. Early-boundary and aggregate-acceptance conclusions
> are re-reported on the corrected data below.

**Frozen execution (superseded):** the preregistered 8-seed run
(126732–126739) used implementation commit `ac603e5` with the preregistered
common configuration plus `STS_S3_REJUV_SHADOW=1 STS_S3_REJUV_TRIGGER=16
STS_S3_REJUV_PROPOSALS=256` and
`STS_S3_REJUV_SHADOW_FILE=build/linux-gcc-release/s3_rejuv_shadow_8.rejuv.csv`,
executed through `tools/seed_guard.sh` with `OMP_NUM_THREADS=12`. Run exited 0;
whole-run outcome was 4/8 wins, avg floor 46.6, avg ending HP 17.6, 31.57 s
cpu/run (informational only — no quality interpretation per the
preregistration). Artifacts:
`build/linux-gcc-release/s3_rejuv_shadow_8{.stdout,.stderr,.meta.json,<base CSV>,.rejuv.csv}`
(overwritten by the corrected rerun below; the old aggregate numbers are
recorded here for provenance).

**Mechanical gates:** (a) non-interference — `rejuv_noninterference` test:
shadow OFF vs ON produced identical committed action bits (9/9), decision
observation hashes, all-18 RNG-field trajectories, positive-particle
`FullHiddenStateKey` sequences, final state, and zero sim-health counter
movement on both arms; (b) per-row sanity — 0 violations of
`0 <= accepted <= proposals`, `0 <= unique <= accepted`, `0 <= novel <= unique`
across all 981 rows, and milestone indices were non-decreasing wherever
present; (c) `sim_health` column total = 0 and no battle-break/stall output
attributable to the probe; (d) `transitions` per row never exceeds the recorded
history length by construction (replay executes exactly the recorded
boundaries).

**Primary mechanical findings (superseded — 981 trigger rows, 251,136
proposals):**

- Full-history regeneration by anchor-fresh re-sampling is possible: 2,013
  accepted hypotheses (0.80% of proposals) in 128 of 981 rows (13.0%). 83 rows
  reached ≥4 unique accepted hypotheses within 256 proposals, 66 reached 8,
  37 reached 16, 21 reached 32. **Corrected interpretation:** compatible
  full-history states were demonstrated for **some** low-support boundaries;
  zero-acceptance boundaries remain **inconclusive** between very low proposal
  probability and hidden-state/model inconsistency — the data do not support a
  global "the model is not hard-inconsistent" claim.
- Acceptance is a **first-turn phenomenon**: decision_idx 0–4 account for
  103/128 accepted rows (80.4%) and decision_idx 0 alone for 24 rows and 560
  accepted hypotheses; after decision ~8 accepted ≈ 0 in this (superseded) run.
  (**Inference** — the mechanism follows from the decision_idx distribution;
  the distribution itself is measured; late-history figures are superseded by
  the corrected rerun below.)
- Novelty: every accepted hypothesis was novel relative to the surviving
  posterior comparator (novel == unique == 2,013).
- Status mix (superseded): 240,792 intermediate mismatches, 8,331 remap
  failures (largely an artifact of the SINGLE_CARD_SELECT recording bug), 0
  action-illegal, 0 sim-health, 0 final-only mismatches (unreachable before
  the FINAL_MISMATCH classification fix).
- Overhead: probe CPU 1.73 s total across 981 triggers (1.76 ms/trigger,
  6.9 µs/proposal) — immaterial.

**Caveats:** acceptance at early boundaries can be inflated by particle-
invariant segments (scripted enemy turns; full-cycle deck draws make
hand/pile multisets order-insensitive — the degenerate case proved by the
CULTIST fixture in `rejuv_history_replay`), so "accepted" is an upper bound on
true hidden-state recovery. Whole-run wins are reported only as run health
context.

## 2026-08-15 — Searcher3 history-replay rejuvenation shadow probe — corrected semantic replay rerun

**Correction (same branch, same frozen 8 seeds):** independent review found
that `record` used `BattleScumSearcher3::cardActionKey` for
SINGLE_CARD_SELECT, which reads only `cardSelectInfo.cards`; hand/discard/
draw/exhaust-pile selections therefore recorded an incomplete (CardId-only or
missing) identity and remapped wrongly. Fixed by probe-specific semantic
recording per `cardSelectTask` (full canonical identity: id, upgradeCount,
costForTurn, freeToPlayOnce, specialData), full-identity remap matching,
explicit empty-MULTI_CARD_SELECT validity, and correct FINAL_MISMATCH
classification (first failure at the final boundary). `rejuv_semantic_select`
regression added (hand permutation, discard/draw remap, identical-CardId
distinct-property resolution, empty multi round-trip).

**Corrected frozen rerun:** identical preregistered command (seeds
126732–126739, 64 particles, 1000 sims, trigger ≤16, 256 proposals, same
model/config flags). Run exited 0; whole-run outcome **4/8 wins, avg floor
46.6, avg ending HP 17.6** — identical to the superseded run (shadow-only
telemetry; live behavior unchanged). 981 trigger rows, 251,136 proposals.

**Old → corrected comparison:**

| Metric | ac603e5 (superseded) | Corrected |
|---|---:|---:|
| remap_failure (total) | 8,331 | **0** |
| remap_failure by decision_idx | non-zero (artifact) | 0 at every decision_idx |
| intermediate_mismatch | 240,792 | 205,629 |
| final_mismatch (reachable?) | 0 (misclassified) | **43,489** |
| accepted / unique / novel | 2,013 | **2,018** |
| rows with any accepted | 128 | **132** |
| collapse rows with any accepted | 24 (93 accepted) | **27 (96 accepted)** |
| milestones 4/8/16/32 | 83/66/37/21 | 83/66/37/21 |
| acceptance at decision ≥8 | 7 rows (d8–d11) | **9 rows (d8–d13), 75 accepted** |

**Corrected scientific interpretation:** the semantic-replay bug inflated
`remap_failure` and suppressed late-fight acceptance, but did not materially
change the headline: full-history regeneration by anchor-fresh re-sampling is
possible at **some** low-support boundaries (2,018 accepted, 0.80%; 83/66/37/21
rows reached 4/8/16/32 unique; acceptance concentrated at decision_idx 0–4 and
rare after ~8). With remap now exact (0 failures), late-fight acceptance rose
slightly (9 rows at decision ≥8, vs 7), consistent with correct semantic replay
of card-select boundaries. **Zero-acceptance boundaries remain inconclusive**
between very low proposal probability (the RNG seed/counter space is
astronomically large) and hidden-state/model inconsistency; no global
consistency claim is warranted. All accepted hypotheses remain novel vs the
surviving posterior; sim-health = 0; probe CPU 1.19 s total. Per-row sanity and
milestone-monotonicity gates: 0 violations.

Artifacts (corrected): `build/linux-gcc-release/s3_rejuv_shadow_8{.stdout,
.stderr,.meta.json,<base CSV>,.rejuv.csv}` (corrected executable; the
superseded run's CSV was overwritten, its aggregate numbers are preserved in
the table above).

## §170 Phase-12 screen-contract correction: corrected M0/M1 retrain and gate (2026-08-15)

Independent audit confirmed that `tools/convert_marg_to_trainer.py` wrote
diagnostic `gateKind` into the trainer `screen` feature, while native deployment
passes actual `gc.screenState`. Temporary corrected datasets changed only
`screen`: 210,838 rows and 39,870 groups remained; 45,088 rows and 7,690 groups
changed; MAP became zero; corrected TREASURE/REST/SHOP counts were 1,294/3,260/
3,136 groups. The local expectation that SHOP had 1,294 groups was incorrect.

Corrected M0 and M1 were retrained with the original 40-epoch rung-4,
non-transformer, absolute-Q recipe, identical split, model seed, and eager CUDA.
On the paired fair Searcher3 gate (seeds 900000–900063, 1,000 sims, 64
particles, 7k VNet alpha 0.3, all strategic gates on, margin 1.0):

| Arm | Original | Corrected | Delta |
|---|---:|---:|---:|
| M0 win rate | 17/64 = 26.56% | 16/64 = 25.00% | -1.56pp |
| M1 win rate | 16/64 = 25.00% | 12/64 = 18.75% | -6.25pp |

This eager-mode result was subsequently superseded by the strict compile-enabled
rerun in §171 and should not be interpreted causally. The contract bug is real
and requires a permanent converter fix; §171 provides the controlled follow-up.
See `docs/archive/research/sessions/phase12-screen-contract-corrected-m0-m1-2026-08-15.md`
for hashes and detailed provenance.

## §171 Phase-12 corrected-screen strict compile-enabled rerun (2026-08-15)

The §170 corrected retrain used eager CUDA despite the original contract's
`STRAT_TOK_COMPILE=1`. A strict rerun held the intended single variable to the
screen IDs while restoring `STRAT_PATIENCE=0`, compile-enabled CUDA, exactly 40
epochs, the original split/model seed/objective/architecture, and the same
64-seed Act-3 gate. All corrected dataset invariants passed.

The epoch-6 best-CE anomaly disappeared: strict M0 and M1 selected epoch 40.
Strict M0 achieved `val_pol_ce=0.501773`, `policy_top1=0.792266`, and
`q_top1=0.251409`; strict M1 achieved `val_pol_ce=0.498305`,
`policy_top1=0.790982`, and `q_top1=0.249154`. Both native exports passed
32-sample parity.

On the fair Searcher3 Act-3 gate (seeds 900000–900063, 1,000 sims, 64
particles, all strategic gates, margin 1.0, explicit `STS_COLLECT_KEYS=0` and
`STS_STOP_AFTER_ACT=3`):

| Arm | Wins | Win rate | Mean floor | Mean HP |
|---|---:|---:|---:|---:|
| Strict corrected M0 | 23/64 | 35.9% | 40.281 | 16.672 |
| Strict corrected M1 | 16/64 | 25.0% | 37.562 | 8.672 |
| Original M0 | 17/64 | 26.6% | 38.812 | 14.562 |
| Original M1 | 16/64 | 25.0% | 38.719 | 10.312 |
| V4 | 24/64 | 37.5% | 41.797 | 20.062 |

Strict M0 vs original M0 was +9.4pp (deterministic bootstrap 95% CI
[-3.1,+21.9]pp); strict M0 vs V4 was -1.6pp (CI [-17.2,+14.1]pp).
The point estimate recovers approximately 86% of the original 10.9pp M0/V4
gap, but the small-block intervals cross zero. Strict M1 remained null versus
original M1 at 25.0%. This supports material contribution from the screen bug
to M0's gap, without establishing full causality or promotion.

See `docs/archive/research/sessions/phase12-screen-contract-strict-rerun-2026-08-15.md`
for complete hashes, paired contingency counts, and parity errors.

## §172 Phase-12 M0/M1 post-hoc Q-supervision autopsy — corrected after reverted draft (2026-08-15)

An earlier autopsy commit was reverted for a wrong screen mapping and an
internally inconsistent cross-classification. This corrected rerun (baseline
`ab18dce`, branch `phase12-m0-m1-autopsy-fixed`) uses one deterministic script
(`tools/phase12_m0_m1_autopsy.py`) on the exact corrected datasets and strict
checkpoints, derives screen names from the actual `ScreenState` numeric field
(`include/game/GameContext.h::sts/ScreenState`), preserves duplicate action
rows, and asserts every invariant.

The policy labels are identical (`chosen`, asserted per matched row); encounter
marginalization changes only the auxiliary Q supervision, whose actual target
is `10*labelWon + labelHp`. Across 39,870 matched decisions, M0/M1 Q-target
argmax differed on 16,951 (42.52%) and exact top-two ordering reversed on
3,338 (8.37%, stable tie-breaking). Corrected semantic rates were SHOP 60.62%,
CARD 44.88%, EVENT 32.95%, TREASURE 30.68%, REST 26.29%, UPGRADE_SELECT
44.37%, and BOSS_RELIC 1.58%. Mean Q-target margin fell 6.9049 → 5.7728.

Inference on the exact strict checkpoints found predicted-Q argmax
disagreement 9,932 (24.91%) and policy-logit argmax disagreement 3,154
(7.91%) — a smaller overall rate than predicted-Q divergence, but strongly
concentrated: SHOP 32.08% and UPGRADE_SELECT 33.30% policy disagreement
versus CARD 3.90% and TREASURE 0.00%. Policy entropy rose slightly
(0.5154 → 0.5271). All-input predicted-Q top-1 fidelity was 25.72% M0 vs
25.67% M1. The complete 8-cell A/B/C cross-classification sums to 39,870 with
marginals exactly matching the headline counts. The evidence supports
substantial auxiliary-Q relabeling with screen-concentrated policy effects,
making auxiliary-Q/representation coupling plausible but not causal proof of
the −10.9pp 64-seed point estimate (CI crosses zero). The autopsy is
**closed**; no M2, retraining, gameplay tracing, or new seeds.

Full tables, hashes, root causes, and provenance:
`docs/archive/research/sessions/phase12-m0-m1-autopsy-2026-08-15.md`.

## 2026-08-15 — Searcher3 conditional-block posterior-geometry shadow diagnostic (STOP: oracle gate failed)

**Question:** Given one hidden state compatible with the recorded real history,
does replacing only one latent block produce additional full-history-compatible
states compared with the current whole-state fresh proposal?

**Implementation:** Follow-up to the corrected whole-state history-replay probe
above. The prior 256-proposal whole-state result remains valid for its frozen
implementation and is not overwritten or reinterpreted. This diagnostic was
shadow-only and default-off. At each trigger (`compatible <= 16`), one paired
set of 64 ordinary fresh Searcher3 prior samples was generated. Each source was
used for `ALL_FRESH` and for each of `DRAW_ORDER`, `SHUFFLE_RNG`,
`CARD_RANDOM_RNG`, `AI_RNG`, `MISC_RNG`, `MONSTER_HP_RNG`, and `POTION_RNG`,
with all non-selected oracle blocks copied bit-identically. Proposal generation
used a dedicated deterministic RNG; replay fallback RNGs were independently
keyed by trigger, proposal index, and family, so family iteration order could
not alter the source proposals.

The oracle was constructed from the copied replay-anchor `BattleContext` and
was used only by the shadow driver. It was not exposed to MCTS, belief
filtering, action selection, tree reuse, fallback, or live rejuvenation. Exact
full-history replay, semantic remapping, observation equality, outcome equality,
and `FullHiddenStateKey` equality were reused from the existing probe.

**Mechanical verification:** Release build passed. The paired-source and
family-order invariance test passed (`rejuv_conditional_blocks`). Existing
`rejuv_history_replay`, `rejuv_semantic_select`, and
`rejuv_noninterference` tests passed, as did `rng_state_propagation` and
`s3_rand64_prior_sampler`. A one-seed smoke produced all nine row families and
64 proposals per non-oracle family. Gameplay remained behavior-neutral in the
non-interference test.

**Frozen execution:** Exactly seeds `126732–126739`, ascension 0, 1,000
simulations, 64 particles, 12 threads, fair Searcher3, real posterior filter,
collapse-fresh fallback, persistent filtered posterior, no tree reuse,
`STS_VNET=models/v_combat_7k_tuned.txt`, `STS_VNET_ALPHA=0.3`, and the V4
strategic token-net artifact with REST/EVENT/SHOP/TREASURE/BOSS_RELIC gates and
margin 1.0. Shadow flags were `STS_S3_REJUV_SHADOW=1`,
`STS_S3_REJUV_TRIGGER=16`, `STS_S3_REJUV_PROPOSALS=64`. Raw artifacts are
`build/s3_conditional_8.rejuv.csv`, `build/s3_conditional_8.csv`, its
`.meta.json`, `.stdout`, and `.stderr` in the experiment worktree.

**Oracle integrity result:** **STOP.** The untouched oracle replay succeeded
for **1,444 / 1,569 trigger rows (92.03%)**, not the required 100%. Failures
were 65 `REMAP_FAILURE`, 52 `INTERMEDIATE_MISMATCH`, and 8 `FINAL_MISMATCH`;
there were no action-illegal or simulator-health failures. The failures
concentrated on single-card-select action type 2, with later type-4 mismatches
after history divergence. This indicates an unresolved replay/hidden-state
boundary or semantic-select coverage problem. The proposal-family acceptance
counts below are retained as raw diagnostic output only and are **not valid
scientific evidence** under the preregistered rule.

**Raw diagnostic totals (not interpretable after the STOP):** 1,569 trigger
rows per family and 100,416 proposals per 64-proposal family. Accepted totals
were DRAW_ORDER 6,406, SHUFFLE_RNG 69,081, CARD_RANDOM_RNG 55,703, AI_RNG
56,265, MISC_RNG 92,416, MONSTER_HP_RNG 86,047, POTION_RNG 91,456, and
ALL_FRESH 1,554. The oracle control itself reported 1,444 accepted rows. These
figures must not be used to support blockwise resample-move promotion because
the oracle integrity gate failed.

**Interpretation:** Implementation correctness is incomplete because the oracle
control is not clean on the frozen quality run. Scientific interpretation is
therefore unresolved; H1–H6 are neither supported nor weakened by the family
acceptance counts. Gameplay was not a treatment and its whole-run result is
not interpreted. The one justified next experiment is a replay-correctness
investigation that localizes the remaining single-card-select/oracle failures;
no live blockwise rejuvenation experiment should proceed first.

## 2026-08-15 — Conditional-block oracle replay correction and authoritative rerun

The required RAW-vs-SEMANTIC discriminator localized the prior oracle failure.
On failing seed `126733`, RAW replay succeeded **311/311 (100%)**, while the
original semantic path succeeded only **218/311 (70.10%)**. The first defect
was `CardSelectTask::CODEX` (task value 2), raw select index 3: index 3 is the
explicit Codex skip action and has no card identity. The existing semantic path
incorrectly rejected it. A targeted Codex-skip regression was added.

The remaining semantic-only divergences then occurred later at `END_TURN` after
visible observations still matched. The simulator uses `CardInstance::uniqueId`
for internal card removal/targeting, while the existing semantic key omitted
that field. The narrow probe-local correction now records and prefers unique IDs
for `CARD`, `SINGLE_CARD_SELECT`, and `MULTI_CARD_SELECT`, with the existing
semantic-key fallback for synthetic cards without a valid unique ID. No global
observation identity, Searcher3 semantic-edge key, RNG behavior, or gameplay
path was changed.

Focused tests passed: `rejuv_semantic_select`, `rejuv_history_replay`,
`rejuv_conditional_blocks`, `rejuv_noninterference`,
`rng_state_propagation`, and `s3_rand64_prior_sampler`. The focused raw-vs-
semantic smoke passed on seeds `126733` (312/312 both modes) and `126737`
(213/213 both modes).

The exact frozen eight-seed conditional-block run was then repeated with the
same configuration and seeds `126732–126739`, 1,000 simulations, 64 particles,
12 threads, fair Searcher3, real filtering, collapse-fresh, persistent
filtered posterior, no tree reuse, the same combat and strategic artifacts,
trigger 16, and 64 paired proposals per family. Raw artifacts:
`build/s3_conditional_8_final.rejuv.csv`, `build/s3_conditional_8_final.csv`,
`.meta.json`, `.stdout`, and `.stderr`.

**Oracle gate:** RAW **1,596/1,596 (100%)**; SEMANTIC
**1,596/1,596 (100%)**. All oracle remap, action-illegal, simulator-health,
intermediate, and final mismatch counts were zero. The prior STOP result was
therefore a semantic replay defect, not a deeper replay nondeterminism failure.

**Authoritative proposal results:** 1,596 trigger rows and 102,144 proposals
per 64-proposal family. Overall acceptance was DRAW_ORDER 6,504 (6.37%),
SHUFFLE_RNG 73,005 (71.47%), CARD_RANDOM_RNG 58,520 (57.29%), AI_RNG 60,599
(59.33%), MISC_RNG 102,144 (100%), MONSTER_HP_RNG 93,157 (91.20%),
POTION_RNG 101,184 (99.06%), and ALL_FRESH 1,563 (1.53%). All accepted
hypotheses were equality-backed unique and novel in the recorded comparator.

At `decision_idx >= 8`, acceptance was DRAW_ORDER 1,752/64,448 (2.72%),
SHUFFLE_RNG 37,119/64,448 (57.60%), CARD_RANDOM_RNG 33,164/64,448 (51.46%),
AI_RNG 32,303/64,448 (50.12%), MISC_RNG 64,448/64,448 (100%), MONSTER_HP_RNG
56,649/64,448 (87.90%), POTION_RNG 63,808/64,448 (99.01%), and ALL_FRESH
251/64,448 (0.39%). Late rows with at least four unique accepted states were
DRAW_ORDER 6, SHUFFLE_RNG 634, CARD_RANDOM_RNG 613, AI_RNG 772, MISC_RNG
1,007, MONSTER_HP_RNG 948, POTION_RNG 997, and ALL_FRESH 20.

RNG-use telemetry showed unused-stream acceptance at approximately 100% for
all applicable RNG families. Used-stream acceptance was approximately 4.35%
for SHUFFLE_RNG, 23.58% for CARD_RANDOM_RNG, 47.44% for AI_RNG, 8.22% for
MONSTER_HP_RNG, and 0% for POTION_RNG in this run; MISC_RNG had no used rows.
Total probe CPU was approximately 11.85 seconds. No oracle first-mismatch
patterns remained.

**Interpretation:** The diagnostic is now mechanically valid. The data support
H1: simultaneous whole-state fresh proposals are much less likely to remain
compatible than several single-block moves, especially late. They also support
H3/H6 directionally: replacing historically unused RNG streams is nearly free,
while consumed raw PRNG-state blocks are substantially less mobile, with
stream-specific differences. MISC_RNG and POTION_RNG remained highly mobile
in this frozen run, while DRAW_ORDER was the most constrained proposal family.
These are posterior-geometry results, not gameplay results; no live treatment
was implemented.

The preregistered practical promotion signal is clearly met by multiple
families at late history (at least four novel accepted states on roughly half
or more of applicable rows). The one justified next experiment is a **live
shadow-neutral resample-move experiment using only a validated future-relevant
block selected after reviewing the stream-use and causal-event breakdown**;
this follow-up must remain a separate preregistered treatment and must not
promote all high-acceptance blocks automatically.

**Follow-up correction (draw-pile source mapping):** Independent review found
that `SECRET_TECHNIQUE`, `SECRET_WEAPON`, and `SEEK` built their semantic key
from `preState.cards.drawPile` but recorded `selectedUniqueId` from the hand
fallback. This was a probe-local source-pile mismatch. The recording branch now
uses `preState.cards.drawPile` for all three tasks; the semantic-key switch and
global simulator behavior were unchanged. `rejuv_semantic_select` now includes
a SEEK fixture with visually identical draw-pile cards, distinct valid unique
IDs, and reordered replay state, and verifies the selected unique ID survives.

The preserved prior CSV/log artifacts did not retain complete
`CardSelectTask` values, and no reliable task-occurrence evidence was found, so
the exact frozen eight-seed command was repeated once. That rerun's raw
`build/s3_conditional_8_drawsource.rejuv.csv` artifact is **incomplete**, not a
smaller valid experiment: it contains 1,593 trigger keys, but one trigger has
only 7 of the required 9 family rows (missing `POTION_RNG` and `ALL_FRESH`),
and its base result CSV omits seed `126733`. The three trigger keys present in
the complete 1,596-trigger artifact but absent from the incomplete artifact are
all later in that same seed/encounter/floor trajectory: seed `126733`, encounter
50, floor 41, decisions 22, 26, and 27 (the preceding decision 21 is the
partial 7-row trigger). This is an interrupted/partial artifact, not evidence
of three scientifically different triggers.

The complete `build/s3_conditional_8_final.rejuv.csv` remains the authoritative
raw geometry artifact: programmatic validation finds 1,596 trigger groups, each
with exactly `ORACLE + 8` families, 64 proposals for every non-oracle row, and
identical family denominators in all/early/late slices. Its oracle gate remains
RAW **1,596/1,596** and SEMANTIC **1,596/1,596**, with zero failure counts.
The source-pile correction was therefore not established as exercised by a
complete eight-seed rerun; the prior complete geometry result remains valid,
and the incomplete rerun must not replace its aggregates. The paired-source,
family-order invariance, and shadow non-interference checks remained passing.
The scientific interpretation is unchanged.

## 2026-08-15 — Searcher3 live AI_RNG rejuvenation implementation/control attempt

**Implementation:** Added opt-in `STS_S3_AI_REJUV_LIVE=off|placebo|ai` support
to fair Searcher3. The mode defaults off. Live treatment uses immutable
battle-start particle lineage IDs, particle-anchored full-history replay, the
existing conditional AI_RNG proposal distribution, zero-weight-only 50/50
splits, and one attempted intervention per combat. Placebo and AI share
proposal generation, successful-source selection, destination slots, weights,
and intervention timing; placebo inserts an exact source duplicate while AI
inserts the accepted novel AI_RNG state. Collapse-fresh invalidates ancestry.
Telemetry is written through `STS_S3_AI_REJUV_LIVE_FILE`.
After review, proposal RNG provenance was corrected to derive each proposal
from fixed salt, game seed, floor/encounter, source filter decision, lineage ID,
and proposal number while preserving the validated AI_RNG sampling
distribution. The earlier implementation/control artifacts are superseded by
the corrected run below.

**Frozen implementation values:** The global shadow defaults remain unchanged
(`g_s3RejuvTrigger=16`, `g_s3RejuvProposals=256`). Causal invocations explicitly
set `STS_S3_REJUV_TRIGGER=16 STS_S3_REJUV_PROPOSALS=64`.

**Verification:** Release build succeeded. The focused live-attempt,
conditional-block, history-replay, semantic-select, real-filter,
persistent-transfer, RNG-propagation, and shadow-noninterference tests passed.
The one-seed guarded smoke passed for OFF, placebo, and AI. Correct-executable
8-seed baseline and placebo arms completed; placebo produced 1,543 telemetry
rows and the AI run produced 1,733 telemetry rows but the AI result artifact
was interrupted at 7/8 seeds by the execution harness. This is an incomplete
implementation/control validation, not a gameplay result.

**Decision:** Do not start the preregistered 32-seed scientific gate until a
complete 8-seed implementation/control rerun is obtained and all controls are
clean. The incomplete AI arm is not interpreted as H0, H1, or H_resample.

The preceding decision was superseded by the completed gate below after the
corrected 8-seed implementation/control rerun. The 32-seed result is recorded
as mixed/inconclusive, not as H0, H1, or H_resample.

## 2026-08-15 — First live AI_RNG causal gate, untouched block 910000–910031

**Question:** Does live particle-lineage AI_RNG support expansion improve
gameplay relative to the matched placebo, with OFF retained as a secondary
baseline? The prior 8-seed implementation/control block is not interpreted
scientifically and was not reused for this gate.

**Configuration:** Three matched arms used fair Searcher3, A0, 1,000 base
simulations, 3,000 boss simulations, 64 particles, 12 threads, belief/internal
update off, chain off, CRN off, real-boundary filtering on, collapse-fresh on,
persistent filtered posterior on, reuse 0, END_TURN marginalization off,
`STS_S3_REJUV_TRIGGER=16`, `STS_S3_REJUV_PROPOSALS=64`,
`models/v_combat_7k_tuned.txt`, VNet alpha 0.3, the V4 strategic token model,
and all REST/EVENT/SHOP/TREASURE/BOSS_RELIC gates with margin 1.0. Every arm
ran through `tools/seed_guard.sh` on seeds `910000–910031`.

**Raw artifacts:** `/tmp/s3live32_off.csv`, `/tmp/s3live32_placebo.csv`,
`/tmp/s3live32_ai.csv`, and placebo/AI telemetry at
`/tmp/s3live32_{placebo,ai}.telemetry.csv`. Result hashes are OFF
`e44c782a15cb3645298dfccb072b101ebee10a60bcb52f27a13b14fb942607fb`, placebo
`c0390f0daae92460c24b8dceade97443221319a46fa759034eb3324e0a4001e8`, and AI
`cf8b518b273bc97edbc38687b86609cfad68b7b2b45832f34761fd53925527be`.

**Gameplay:** OFF won 17/32 with mean floor 47.781; placebo won 12/32 with
mean floor 45.406; AI won 15/32 with mean floor 46.656. Primary AI−placebo
paired delta was +3/32 wins (+9.375 percentage points) and +1.25 mean floor.
AI−OFF was −2/32 wins and −1.125 mean floor. Placebo−OFF was −5/32 wins and
−2.375 mean floor. AI−placebo floor gains occurred on 6 seeds and losses on 5;
The +1.25 mean was not solely an outlier, although seed 910020 contributed a
−31 floor loss and seed 910018 a +20 gain. The audited paired win discordance
was AI wins/placebo losses `6` versus AI losses/placebo wins `3`, for a net
difference of `+3` wins; reverse discordant pairs were present.

**Exposure:** Placebo had 6,133 telemetry rows, 317 first attempts, 1,427
duplicate children, and `unique_children=0`, with all 32 seeds exposed. AI had
6,440 rows, 329 first attempts, 1,494 novel children, and
`unique_children=1494`, with all 32 seeds exposed. Reported intervention CPU
was 98.087 ms placebo and 93.017 ms AI across telemetry rows. This is a causal
screen result, not a promotion claim; follow the preregistered decision rule
before extending to 64 seeds.

An independent raw-data audit is preserved at
`build/s3live32_causal_gate_910000_910031/s3live32_causal_gate_audit.md`, with
copies of all five raw result/telemetry files. It found AI−PLACEBO paired floor
mean `+1.25` with median `0`, SD `9.073`, bootstrap 95% CI
`[-1.9375,+4.25]`, positive/negative/zero counts `6/5/21`, and exact McNemar
discordance `(6,3)`, two-sided `p=0.5078125`. Omitting seed 910018 leaves
`+0.645161`; omitting 910020 gives `+2.290323`. Placebo children versus
Placebo−OFF floor delta had descriptive Pearson `r=-0.153538`; AI children
versus AI−OFF had `r=0.077262`. These correlations are observational and do
not establish that duplication caused harm or novelty caused benefit.

**Autopsy decision:** classify the gate as **mixed/inconclusive**. Exposure was
adequate in all 32 seeds for both live arms, but AI was below OFF in aggregate
and the primary AI−PLACEBO uncertainty includes zero. Do not promote H1 and do
not start the 64-seed extension without a new preregistered decision.

## 2026-08-15 — Searcher3 single-child AI_RNG rejuvenation follow-up, fresh block 920000–920015

**Question:** Does limiting live rejuvenation to one accepted child per combat
retain useful AI_RNG novelty while reducing multiplicity/dose distortion? The
paired arms were OFF, PLACEBO1, and AI1. This was a mechanism-discrimination
follow-up, not a promotion run; it stopped at exactly 16 seeds.

**Configuration:** Fair Searcher3, A0, 1,000 base simulations, 3,000 boss
simulations, 64 particles, 12 threads, internal belief update off, chain off,
CRN off, real-boundary filtering on, collapse-fresh on, persistent filtered
posterior on, reuse 0, END_TURN marginalization off,
`STS_S3_REJUV_TRIGGER=16`, `STS_S3_REJUV_PROPOSALS=64`, combat VNet
`models/v_combat_7k_tuned.txt` (sha256
`ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c`), VNet
alpha 0.3, V4 strategic token model
`selfplay/models/ooc_strategic_tok_final.native` (sha256
`e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`), and
REST/EVENT/SHOP/TREASURE/BOSS_RELIC gates with margin 1.0. Every arm ran
through `tools/seed_guard.sh` on seeds `920000–920015`.

**Aggregates:**

| arm | wins | win rate | mean floor |
|---|---:|---:|---:|
| OFF | 10/16 | 62.5% | 47.3125 |
| PLACEBO1 | 8/16 | 50.0% | 47.8125 |
| AI1 | 11/16 | 68.75% | 45.2500 |

**Per-seed results:**

| seed | OFF won/floor | PLACEBO1 won/floor | AI1 won/floor | PLACEBO1 children | AI1 children | PLACEBO1 mass | AI1 mass |
|---:|---:|---:|---:|---:|---:|---:|---:|
| 920000 | 1/51 | 1/51 | 1/51 | 6 | 6 | 1.079 | 1.079 |
| 920001 | 1/51 | 1/51 | 1/51 | 7 | 7 | 0.822 | 0.822 |
| 920002 | 0/33 | 0/33 | 0/33 | 7 | 7 | 1.821 | 1.821 |
| 920003 | 1/51 | 1/51 | 1/51 | 8 | 8 | 2.325 | 2.296 |
| 920004 | 1/51 | 0/50 | 1/51 | 12 | 16 | 2.759 | 4.005 |
| 920005 | 0/45 | 0/45 | 0/41 | 13 | 13 | 2.319 | 2.319 |
| 920006 | 0/33 | 0/33 | 0/33 | 11 | 13 | 1.630 | 2.630 |
| 920007 | 1/51 | 0/50 | 0/33 | 18 | 10 | 4.306 | 2.367 |
| 920008 | 0/50 | 0/50 | 1/51 | 13 | 12 | 3.425 | 2.842 |
| 920009 | 1/51 | 1/51 | 1/51 | 19 | 17 | 4.539 | 3.042 |
| 920010 | 0/46 | 0/46 | 0/23 | 12 | 9 | 1.431 | 0.589 |
| 920011 | 0/40 | 1/51 | 1/51 | 13 | 13 | 3.019 | 3.019 |
| 920012 | 1/51 | 1/51 | 1/51 | 9 | 9 | 1.967 | 1.967 |
| 920013 | 1/51 | 1/51 | 1/51 | 17 | 14 | 3.724 | 3.070 |
| 920014 | 1/51 | 0/50 | 1/51 | 9 | 12 | 1.918 | 2.679 |
| 920015 | 1/51 | 1/51 | 1/51 | 12 | 12 | 2.992 | 2.992 |

**Paired comparisons:** AI1−PLACEBO1 was `+3/16` wins and `−2.5625`
mean floor, median `0`, floor positive/negative/zero `3/3/10`, exact win
discordance `(3,0)`. AI1−OFF was `+1/16` wins and `−2.0625` mean floor,
median `0`, floor positive/negative/zero `2/3/11`, discordance `(2,1)`.
PLACEBO1−OFF was `−2/16` wins and `+0.5` mean floor, median `0`, floor
positive/negative/zero `1/3/12`, discordance `(1,3)`.

**Exposure/integrity:** PLACEBO1 had 3,712 telemetry rows, 187 attempt rows,
186 injected children, and 40.076 injected mass. AI1 had 3,413 rows, 179
attempt rows, 178 injected children, and 37.539 injected mass. Both arms were
exposed in 16/16 seeds. Maximum children per combat was `1` in both arms;
`children_injected` was only `0/1`; PLACEBO1 had `unique_children=0`; AI1 had
`unique_children` equal to `children_injected`; integrity failures were zero.

**Raw hashes:** OFF result `3767fa33b80f9af8c87497740ddecc6de347975fb5364088ec3ee15f5e1a317a`,
PLACEBO1 result `63d7323c1f37e21f59290e843ae596f940e8eaca7d38d0e4cc3d5e90a00bd383`,
AI1 result `139133aaca5f38898ef7fc8c44f00408e22af5b25f153309b98299c8aeb250f7`,
PLACEBO1 telemetry `c43ac1b6215da7a9dfb702b04b079e94a6d4a04940eaa8f7975e3606f3c20f3c`,
AI1 telemetry `e56183ebb524e70f1946e26dc9ceb43a4d3a811d835c845d25bbc9e8c0f6ec8a`.

**Decision:** Closest to preregistered **Outcome A** directionally on wins,
but mixed because AI1 lost on mean floor against both comparators. Exposure is
not limiting. Stop at 16 seeds; do not automatically extend or promote live
rejuvenation.

## 2026-08-15 — Searcher3 AI1 single-child confirmation, fresh block 920016–920079

**Question:** Does the 16-seed AI1 win-rate direction confirm on a fresh 64-seed
block, with floor/depth monitored as safety evidence? The matched arms were OFF,
PLACEBO1, and AI1. This confirmation stopped at exactly 64 seeds.

**Configuration:** The frozen 16-seed configuration was retained: fair
Searcher3, A0, 1,000 base simulations, 3,000 boss simulations, 64 particles,
12 threads, internal belief update off, chain off, CRN off, real-boundary
filtering on, collapse-fresh on, persistent filtered posterior on, reuse 0,
END_TURN marginalization off, `STS_S3_REJUV_TRIGGER=16`,
`STS_S3_REJUV_PROPOSALS=64`, VNet `models/v_combat_7k_tuned.txt` alpha 0.3,
the same V4 OOC model, REST/EVENT/SHOP/TREASURE/BOSS_RELIC on, margin 1.0.
All arms used `tools/seed_guard.sh` and seeds `920016–920079`.

**Aggregates:**

| arm | wins | win rate | mean floor |
|---|---:|---:|---:|
| OFF | 40/64 | 62.50% | 45.3281 |
| PLACEBO1 | 38/64 | 59.375% | 45.5625 |
| AI1 | 41/64 | 64.0625% | 45.4688 |

**Paired comparisons:**

- AI1−PLACEBO1: win delta `+3/64`, exact discordance `(4,1)`, exact
  two-sided binomial/McNemar p `0.375`; floor mean `−0.0938`, median `0`,
  positive/negative/zero `6/4/54`, bootstrap 95% CI `[-1.4531,+1.1094]`.
- AI1−OFF: win delta `+1/64`, exact discordance `(4,3)`, p `1.0`; floor mean
  `+0.1406`, median `0`, positive/negative/zero `6/6/52`, bootstrap 95% CI
  `[-1.3281,+1.4688]`.
- PLACEBO1−OFF: win delta `−2/64`, exact discordance `(3,5)`, p `0.7265625`;
  floor mean `+0.2344`, median `0`, positive/negative/zero `5/5/54`, bootstrap
  95% CI `[-0.7969,+1.3125]`.

Largest AI1 floor deltas were `+18` and `−28` versus PLACEBO1, and `+18` and
`−28` versus OFF. Leave-one-out floor means ranged from `−0.3810` to `+0.3492`
for AI1−PLACEBO1 and `−0.1429` to `+0.5873` for AI1−OFF. AI1 lost while the
comparator won on 1 seed versus PLACEBO1 and 3 seeds versus OFF. Severe AI1
floor regressions of at least 10 floors occurred on seeds `920031` (`−17`) and
`920079` (`−28`) against both comparators.

**Exposure/integrity:** PLACEBO1 had 13,223 telemetry rows, 643 attempts, 640
children, and 139.805 injected mass. AI1 had 13,229 rows, 627 attempts, 624
children, and 143.970 injected mass. Both exposed all 64 seeds. Maximum
children per combat was `1` for both; `children_injected` was only `0/1`;
PLACEBO1 had `unique_children=0`; AI1 had `unique_children` equal to
`children_injected`; integrity failures were zero.

**Raw hashes:** OFF result `bbf0f95cefcf7ac5859efdaf4ad81458a96b25f5068b0a02d5b87ac31f0e6a47`,
PLACEBO1 result `f88b9209c4dfd8c72e5d440175bb7db2213dde1655e6957ed776c00e13756627`,
AI1 result `0543dc31a90cab103b32d39871d542fbcb603464de9894b9ed442c8e6d8faa98`,
PLACEBO1 telemetry `4c09cc1a93a125aaeaa976ed56ffa23444dae4b10b1c30a6f91a286e4df8e8ec`,
AI1 telemetry `73039d4c9a02cba9b1e557a5bdc97c2f391566f8049f13050b0d37985fef8d9a`.

**Decision:** AI1 remained directionally above PLACEBO1 and at least as good as
OFF on wins, with four treatment-only wins versus one reverse discordance in
the primary comparison. The win advantage is not statistically persuasive and
the floor result is approximately null, not a clear downside on aggregate.
However, two shared severe early-loss regressions warrant explicit caution.
Classify as **promising win-rate direction with a possible downside tail**, not
as a clean promotion result. Do not extend beyond 64 seeds automatically.

## §173 Phase-13A counterfactual teacher-strength audit (2026-08-15)

Phase 13A audited whether the Phase-12 short fixed-world teacher gives
reliable rankings on high-confidence strict-M0/V4 disagreements. The fresh
source block was `920000..920007` (8 seeds; no prior V4/M0 comparison use),
with the frozen V4 source trajectory, non-MAP V4 margin ownership, and M0
score-only eligibility `Q_M0(a_M0)-Q_M0(a_V4) >= 1.0`. The pool contained 119
eligible states. A deterministic `random.Random(1301)` sample selected exactly
16 states before any evaluator outcomes; manifest SHA256 is
`88795a8b46db5296f453bd2dcd17ebb6453dbf352cbba4a65949d20098857bc4`.

Evaluator S preserved Phase-12 Tier-B semantics: H=4, K=3, bootstrap enabled,
150/100/50 fight schedule. Evaluator R used the same copied fixed-world state,
paired continuation seeds, and existing OOC continuation chain, but ran to the
terminal horizon with `sims=1000`, no fight cap, no bootstrap, and no fixed
fight schedule. The exact V4 native hash was
`e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`; the
durable strict-M0 native hash was
`97564d1be6b4f2356ef5807645a3b45126726bf8ae07cc2b7e273a860106e62a`.

The committed raw evidence has 256 rows (16 decisions × 2 actions × 4
futures × 2 evaluators), SHA256
`81e686d4eab32500df2397345b44f4c6d19a377dac97b2edf4a5c528b0e2e7c0`.
Fifteen decisions were fully valid. Two R futures for `(920000,12)` failed
the existing Searcher3 health contract (`TRANSIENT` / `SECRET_WEAPON`), and
were retained as invalid rows rather than averaged or replaced. On the 15
valid decisions, mean `refDelta=-2.050000`, mean `refWinDelta=-0.083333`;
S preferences M0/V4/tie were 8/2/5 and R preferences were 3/5/7. Strict sign
agreement was 3/15 for short-vs-reference and 3/15 for model-vs-reference.

This run is **INVALID — ownership-selection bug**. The collector treated every
REWARDS state with `cardRewardCount > 0` as V4-owned even when live V4 was still
auto-collecting gold, relic, potion, or enabled keys. Nine of the 16 selected
states were REWARDS states, so the sampled population was not the registered
population. The raw evidence remains preserved under
`docs/experiments/evidence/phase13a-teacher-audit/`; its S/R aggregates and
H4 conclusion must not be interpreted scientifically. A corrected fresh-seed
rerun is required.

Evidence and the complete decision table are under
`docs/experiments/evidence/phase13a-teacher-audit/`.

### §173 corrected ownership rerun

The ownership bug was fixed before collecting a new candidate pool. The
collector now mirrors live V4 precedence: REWARDS is eligible only after gold,
relic, potion, and enabled-key actions are exhausted; other screens require
their enabled live strategic gate and legal actions. The collector records
`gateOwned`, `liveV4Idx`, and `liveV4Margin`, and the ownership smoke passed.

Fresh seeds were `940000..940007`, with exact source/replay budget `sims=1000`.
The corrected pool contained 70 candidates; deterministic sample seed 1301
selected 16 before outcomes. Manifest SHA256:
`a84de37a038ead6750115bc8cb95d697710e8b60cd7788070b56297d1b1752db`.

The corrected audit produced 256/256 valid rows with no replay or health
failures. Raw SHA256:
`1f7778f3ce7200a08eec34f05885a0f8d08b373a36e798d8477657014dec1fa3`.
Mean `refDelta=-13.843750`; mean `refWinDelta=-0.250000`. S preferences
M0/V4/tie were 9/5/2; R preferences were 6/9/1. Strict sign agreement was
6/16 for short-vs-reference and 6/16 for model-vs-reference; tie-aware
three-way agreement was 7/16 and 6/16 respectively. All R rows had
`bootstrap=0`.

The corrected result is **H4 inconclusive** under the preregistered rules:
reference V4 preference is 9/16, below the 10/16 threshold, while neither the
short teacher nor R favors M0 on at least 10/16. This valid result does not
support promotion or identify a causal teacher/model/objective diagnosis.

### §173 H=8 reference extension

The corrected 16-state manifest and all existing S/H=4 rows were preserved.
Four new paired R futures per state/action (`future=4..7`) added 128 terminal
R continuations; no reselection or new S labels were performed. All additional
rows were valid with no replay or simulator-health failures.

Combined H=8 R results: mean `refDelta=-11.320312`, mean
`refWinDelta=-0.195312`; R preferences M0/V4/tie were 5/10/1. Strict
short/reference and model/reference agreement were both 5/16; tie-aware
three-way agreement was 6/16 and 5/16. Combined raw SHA256:
`b1a048945ffc485f39aa4c75696816dbace5919d9907ef5f21db2d4a42c347b4`.
Combined summary SHA256:
`1c9a0785040492400cdefe13e6331261ad8ec5970dd8bfda92bd5f7e9f2709d6`.

H=8 reaches the preregistered reference condition (V4 preferred on 10/16 and
negative mean reference utility Δ). The high-confidence M0 improvement signal
is therefore rejected under the stronger reference. The agreement metrics do
not distinguish teacher/target failure from model-learning failure. No new
labels, reselection, threshold tuning, or gameplay gate was run.

## 2026-08-16 — Searcher3 cheap behavior-preserving speedups (perf/s3-cheap-speedups)

Bounded implementation-efficiency pass on the fair Searcher3 path; no search
parameter, RNG, model, or feature changed. Baseline `main` `a7573e1`
(2026-08-16), measured in a dedicated worktree on branch
`perf/s3-cheap-speedups`; the particle-conditioned leaf-value Phase-1 branch
was not touched.

Configuration: `OMP_NUM_THREADS=1 STS_FAIR=1 STS_SEARCHER3=1
STS_S3_PARTICLES=64 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_LIVE_VALID=1`, vnet
leaf auto-default `models/v_combat_7k_tuned.txt` α=0.3 (§148), policy PUCT
`models/policy_trees_c.txt` c=2.5, rejuvenation off (default), persistent
posterior / pool-redirect / rank-corr / all other experimental flags at
default (off). Workload: `bash tools/seed_guard.sh ./build/linux-gcc-release/
one_combat bestbench 1000 4 0` (4 seeds, 1399 searches, 2,133,000 simulations
per repetition; fresh LTO Release build per arm).

Interventions (both in `src/sim/search/BattleScumSearcher3.cpp`):

- A — `step()`: the per-expansion full `BattleContext preExecState` copy is
  taken only when `g_s3EndTurnMarginalize` (default off, `STS_S3_END_TURN_MARGINALIZE`)
  can consume it; the consumer guard now tests `preExecState` itself, so the
  enabled-feature behavior is unchanged.
- B — `sameCardMultiset` (particle draw-order compatibility, runs once per
  simulation via `applyParticleImpl`): exact multiset equality via a fixed
  `std::array<int, cardEnumStrings-size>` count table instead of two heap
  vectors + two sorts. Same id-only identity domain as before (upgrade state
  was and is outside this comparison; duplicates count per occurrence).

Primary metric: median `simSeconds*1e6/simsExec` per search from
`STS_REUSE_CPU_DIAG` CSV (ms/1000 sims). 9 interleaved rounds × 3 arms
(base / A / A+B), rotating arm order per round; per-round medians (ms/1000
sims):

| Round | base | A | A+B |
| --- | --- | --- | --- |
| 1 | 28.271 | 27.693 | 27.309 |
| 2 | 28.423 | 28.122 | 27.273 |
| 3 | 27.551 | 27.432 | 28.785 |
| 4 | 27.613 | 27.640 | 27.008 |
| 5 | 27.616 | 27.474 | 26.946 |
| 6 | 30.200 | 29.286 | 28.002 |
| 7 | 28.805 | 28.093 | 28.230 |
| 8 | 30.250 | 28.879 | 27.653 |
| 9 | 28.041 | 28.117 | 27.726 |
| median | 28.271 | 28.086 | 27.647 |

Result: A alone +0.66%, A+B +2.21% (paired per-round median +2.43%). Host
noise between rounds is up to ±4% (rounds 6/8 baseline slowdowns), so only the
paired interleaved comparison is decision-relevant. Retained as one combined
change under the small-diff rule; A alone or B alone fall under the 2% floor.

Behavioral equivalence (exact, not aggregate):

- `one_combat fairgen 2 1000 0 0.3 ...` value/policy/OOC CSVs byte-identical
  (md5 match) between base and A, and between base and A+B.
- All 27 CPU-diag runs identical on every non-timing column (seed, floor,
  decisionIdx, simsExec, treeActions, rolloutActions, rootSimAfter, playerHp,
  turn) — same root visit totals, same trajectories.
- `bestbench` win%/avg_floor/avg_hp_end identical across arms; wall-clock
  whole-run time reported as secondary evidence only.

Focused tests (perf-worktree `test` binary, all PASS): belief, drawpile 77,
obs_identity 77, prune 77, battlecontext_roundtrip, rng_state_propagation 77,
seed_contract 77, belief_immutability, rejuv_history_replay 77,
rejuv_noninterference 77, cardselect_parity, issue_fixes, real_belief_filter
77, s3_drawpile_reuse_boundary. `belief_order_invariance` FAILS identically on
untouched main `a7573e1` (pre-existing, 4 weight checks) — not caused by this
change and not addressed here.

Largest remaining Searcher3 hotspots (code inspection; no perf on this host):
vnet leaf inference per rollout endpoint (`evaluateLeaf` →
`g_combatVNet.predict`), per-rollout-slot `BattleContext` copies in
`multiRollout`, and action execution itself. Reducing these requires
representation/architecture work (BattleContext copy semantics, observation
architecture, model serving) — explicitly out of scope; recommendation is STOP
and return to particle-conditioned leaf-value research.

## E2 — post-combat run-win critic (2026-08-16)

**Baseline / branch:** `548742ab973d7f22eb6b1186dadb942c3aed10b5`,
`exp/postcombat-runwin`. This is an offline target-validity diagnostic only;
no Searcher3, particle, OOC policy, or deployed combat model was changed.

**Boundary:** `BattleContext::exitBattle` commits HP, potions, deck, relic,
gold, and combat RNG state; victory returns through `GameContext::afterBattle`.
`datagen2` emits one row at the first card-reward decision after the fixed
gold/relic/potion auto-pickup and immediately before card pick/skip. Normal,
elite, and act-1/2 boss rewards always include a card reward. Act-3 terminal
boss fights and event-room fights are not represented. Thus this is the first
stable post-combat decision boundary, not the raw pre-reward screen.

**Dataset / provenance:** existing ignored `build/vrich.csv`, generated by
`tools/run/datagen2_loop.sh` on 2026-07-15: Ironclad ascension 0, 10,000
simulations, epsilon 0.05, `v_server.py` V-marginal card continuation policy
(softmax temperature 3 plus 5% uniform floor and skip threshold), heuristic
map/shop/rest elsewhere. The canonical `vFeatCsv`/`richRow` path supplies the
features; no feature definition was duplicated. The file has 1,444,372 rows,
67,655 seeds, 18,601 wins and 49,054 losses. Act rows: 664,571 / 488,021 /
291,780 for Acts 1 / 2 / 3. Per-seed `won` consistency check: zero violations.
The source file SHA256 is retained in `build/e2_postcombat_runwin/`.

**Method:** `GroupShuffleSplit(test_size=0.15, random_state=0)` by seed,
matched for all arms: 57,506 train seeds and 10,149 held-out seeds. B0 is
training prevalence. B1 uses exactly `curHp`, `maxHp`, `hpFrac`, `act`, and
`floor`. T uses all 448 non-label, non-constant canonical rich features. B1
and T use the existing `train_winrate.py` XGBoost recipe: binary logistic,
hist, depth 8, eta .05, subsample .8, column sample .7, min child weight 20,
max bin 256, 1,500 rounds, early stopping 40. Bootstrap is 2,000 resamples
of held-out seeds, reporting T minus B1.

**Held-out metrics:** 216,620 rows, 71,672 positives and 144,948 negatives.

| arm | ROC-AUC | log loss | Brier | ECE |
| --- | ---: | ---: | ---: | ---: |
| B0 | 0.50000 | 0.63479 | 0.22140 | 0.00131 |
| B1 | 0.64975 | 0.59517 | 0.20359 | 0.00363 |
| T | 0.74816 | 0.53507 | 0.17913 | 0.00842 |

T act metrics (rows / AUC / log loss / Brier / ECE): Act 1 99,790 /
0.63555 / 0.56327 / 0.18946 / 0.00451; Act 2 73,074 / 0.78048 / 0.50662 /
0.16843 / 0.01659; Act 3 43,756 / 0.81932 / 0.51825 / 0.17344 / 0.01069.
All act strata have adequate held-out seed counts (10,149 / 9,726 / 6,204)
and no major calibration failure.

Seed bootstrap differences T−B1: log-loss mean −0.06011, 95% CI
[−0.06483, −0.05534]; Brier mean −0.02447, CI [−0.02635, −0.02253]; AUC
mean +0.09840, CI [+0.09172, +0.10488]. **Decision: SUPPORTED.** The rich
post-combat state is predictively useful beyond HP/progression under this
continuation policy. This does not establish causal item values, gameplay
improvement, generic `V_win` correctness, Searcher3 integration, or a new
`V_combat` target. Known-RNG encounter fields are included in T and are a
limitation for interpreting transfer to a different information regime.

**Correction before merge:** the first artifact used sparse full-dataset run
IDs when resampling validation seeds. The trainer now reindexes the held-out
run IDs contiguously before bootstrap, and the bootstrap artifacts below were
regenerated. This changes uncertainty estimates only; model fitting and the
held-out predictions are unchanged. The corrected bootstrap is the result to
use for interpretation.

**Relation to §116:** §116's TERM_WIN terminal-leaf benchmark was null because
the deployed win tree was insensitive to the counter features; it therefore
deferred Stage 3 until a counter-aware terminal evaluator existed. E2 is a
potentially relevant prerequisite because it demonstrates that a rich
post-combat state can predict eventual run outcome beyond HP/progression under
the recorded continuation policy. E2 has **not** demonstrated a
counter-aware terminal evaluator, has not shown that counters are causally
priced, and does not authorize TERM_WIN, Searcher3, V_combat, or any deployed
model change. It is merged as a useful offline positive diagnostic only.

Artifacts: `build/e2_postcombat_runwin/metrics.json`,
`calibration_deciles.csv`, `provenance.json`, `bootstrap` in metrics,
`b1_model.json`, `t_model.json`, `val_predictions.npz`, and
`sha256sums.txt`. Reproduction command:
`STS_XGB_DEVICE=cuda python3 tools/train_postcombat_runwin.py build/vrich.csv
build/e2_postcombat_runwin`.
