# 2026-08-08 — Self-play relabeling (5.7.3) Phase 0 verification executed; datagen/training/gate pending

Date: 2026-08-08
Session/task: Execute Phase 0 of the 5.7.3 self-play relabeling handoff plan
(`docs/knowledge-base/plan-selfplay-relabeling-2026-08-07.md`): verify the
`strategicgen2` Tier-B label producer on the current deployed combat
controller and the `train_strategic_tok.py` → `export_strategic_tok.py` chain.

## Decision

- Phase 0 is executed and recorded as EXPERIMENTS.md §136: the 10-seed
  `strategicgen2` smoke with the fair S3−belief−chain + live-valid + §126
  vnet-default stack emits the trainer-consumable schema (1017 rich-state
  columns, Tier-B suffix), labels every decision (STRATEGIC_SAMPLE_ALL=1),
  shows no vnet-load warning, and the trainer/export parity chain works.
- **No C++ code changes** — the plan's claim is confirmed against the code
  (`strategicgen2` main-run and branch OOC are heuristic by design;
  branch battles use the env-selected searcher).
- Phases 1–3 (GCP 1,500-seed datagen, GPU control/candidate retrains, paired
  gate) are deferred to the manual GCP follow-up per the plan protocol; the
  pre-registered verdict rule stands unchanged.
- Plan-vs-repo command discrepancies are recorded for the follow-up session
  (below) rather than silently "fixed" in the plan.

## Rationale

- The plan's Phase-0 verification scope is exactly the cheap, local,
  pre-datagen gate; the expensive items (full datagen, 40-epoch GPU training,
  256-seed gates) are explicitly reserved as manual follow-ups outside the
  automated workflow.
- Evidence-first: EXPERIMENTS.md §136 records only what was actually
  executed; the label-vs-chosen agreement preview is labelled smoke-scale
  and non-gating.
- Discrepancy (1) below is recorded because silently changing the plan's
  commands would violate the handoff contract (the orchestrator runs the
  plan's verification commands independently).

## Alternatives considered

- Run the full 1,500-seed GCP datagen now — rejected: it is a ~1–1.5 h
  preemptible-GCP run marked expensive/manual in the plan; the parallel
  agent uses the box; the orchestrator owns long-run verification.
- Retrain control/candidate locally now — rejected: 40-epoch GPU runs are
  out of the cheap-check scope and their gate depends on datagen completing
  first.
- Patch the plan's Phase-2 export command in the plan file — rejected: the
  architecture plan and its verification commands must not be modified.

## Evidence

- `apps/one_combat.cpp::strategicGen2` / `runStrategicGenSeed2` /
  `finishOocCounterfactual` — heuristic OOC, env-selected branch searcher,
  vnet-warning guard (line 7454).
- Phase-0 run: `./build/one_combat strategicgen2 10 1000 0 build/sp_smoke_phase0.csv 300000`
  with `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STRATEGIC_SAMPLE_ALL=1` → 6,244 rows / 10 seeds, 380–771 rows/seed,
  100% labelWon coverage, 2,363 distinct labelWon values.
- Schema check (pandas): 1017 state cols between `chosen` and `won`; suffix
  exactly `labelWon,labelHp,labelFloor,labelBootstrap`.
- Trainer/export: `STRAT_DEVICE=cpu STRAT_EPOCHS=2 .venv/bin/python
  train_strategic_tok.py` on the smoke slice → `build/tok_smoke.pt.pt`;
  `export_strategic_tok.py build/tok_smoke.pt.pt build/ooc_strategic_tok_smoke.native`
  → 32 parity checks, max err ≤1.7e-07; native loads in `one_combat`
  (`[OOC one-ply strategic TOK net ON: …]`, `S3-abl[b,p,c,l,crn]=01010`,
  vnet default ON).
- `cmake --build build -j` clean; `./build/test` exits 0; `ctest` 8/8
  (selfplay_syntax PASSED at this HEAD — the plan's "known CRLF failure" is
  absent).

## Status and follow-up

- Phase 0 DONE; EXPERIMENTS.md §136 records it; decision log updated.
- **Open (manual GCP follow-up, next session):** Phase 1 — 1,500-seed
  `strategicgen2` datagen on sts-test (seeds 300000–301499, three 500-seed
  chunks @24 threads, same envs), concatenate to `build/strategic_sp_1500.csv`,
  compute the §104-style argmax(labelWon)-vs-chosen agreement diagnostic.
  Phase 2 — control retrain on `build/strategic_tierb.csv` and candidate
  retrain on the new data (same recipe, GPU, rung 4, 40 epochs; `rm -f`
  the `_tok_state.bin` before reruns), export both `.native` files. Phase 3 —
  paired 256-seed gate on block 126700–126955 @1k/64p vs
  `build/vnet_all_a03_1k.csv` (50.4%), pre-registered verdict rule.
- **Recorded discrepancies for the follow-up session:** (1)
  `train_strategic_tok.py` writes `OUT + ".pt"`, so the exporter must be
  given the real checkpoint path (`build/tok_control.pt.pt` for trainer OUT
  `build/tok_control.pt`); the plan's Phase-2 export commands as written
  would silently run the exporter selftest on a random checkpoint instead of
  the trained one. (2) The training environment is the repo venv
  (`.venv/bin/python`, torch 2.5.1+cu121); system `python3` has no torch.
  (3) `ctest` 8/8 at this HEAD (no selfplay_syntax CRLF failure).

## Follow-up (same day, verification-fix session)

**Decision:** resolve the environment side of the verification failures
without touching code, the plan, or its verification commands.

- Provisioned torch for the system `python3`: copied the venv's torch
  2.5.1+cu121 stack (torch, torchgen, functorch, triton, nvidia-* cu12 libs,
  and deps filelock/fsspec/jinja2/markupsafe/mpmath/networkx/sympy) into the
  user site `~/.local/lib/python3.12/site-packages` (the same location where
  numpy/pandas already live for system `python3`). The venv remains the
  canonical environment; the user-site copy is a provisioning mirror.
  Rationale: the plan's own Phase-0c/2 commands invoke bare `python3`, and
  the automated verification harness runs the same, so the default
  interpreter must import torch. Verified: `python3 -c "import torch"` →
  `2.5.1+cu121`, `torch.cuda.is_available()` → True.
- Kept `build/tok_smoke.pt` as a symlink to the trainer's real output
  `build/tok_smoke.pt.pt` so `export_strategic_tok.py build/tok_smoke.pt …`
  exercises the trained checkpoint (discrepancy 1) instead of the exporter's
  random selftest fallback.
- Re-ran the two previously failing smokes under plain `python3`: training
  smoke `STRAT_DEVICE=cpu STRAT_EPOCHS=2 python3 train_strategic_tok.py
  build/sp_smoke.csv build/tok_smoke.pt` → PASS (2 epochs, metrics identical
  to the venv run, val_pol_ce 1.5204); export smoke `python3
  export_strategic_tok.py build/tok_smoke.pt
  selfplay/models/ooc_strategic_tok_smoke.native` → PASS (32 parity checks,
  max err 1.66e-07).
- **Open (unresolved, verification-budget mismatch):** the plan's 1-seed
  @100-sim schema-validation check (`strategicgen2 1 100 0
  build/sp_smoke_header.csv 300010`, 60 s budget) cannot complete on this
  machine — measured **166.2 s** for a single seed. The cost is the datagen's
  per-decision branch-fight contract (3 fights × 150/100/50 sims,
  `STRATEGIC_BRANCH_FUTURES=1`, the §84-optimal defaults the plan mandates
  keeping); 12 OMP threads do not help because one seed uses one core. The
  schema it would validate is already verified by the passing 10-seed smoke
  (1017 state cols + Tier-B suffix + 100% labelWon coverage), so no datagen
  code or default was changed to fit the budget — that would alter label
  semantics and invalidate the experiment. Recorded in EXPERIMENTS.md §136.
- Status: Phase 0 verification-complete; Phases 1–3 remain the manual GCP
  follow-up listed above.

## Follow-up (same day, verification-fix session, second pass — REVERTED)

An earlier second-pass attempt resolved the 60 s-budget mismatch by
parallelizing branch-battle evaluation inside a single seed (deferred
`omp taskgroup` when `nSeeds < threads`). **That C++ change was reverted in
full** after review: `apps/one_combat.cpp` is byte-identical to HEAD.

- **Why reverted:** the deferred path is not structurally guaranteed
  byte-identical to the serial path. In deferred mode the thread-local
  `t_curPath` stays set through the whole main loop, so the main-run OOC
  policy (`serverCardRewardPolicy`/`restWinPolicy`/`upgradeSelectWinPolicy`
  via `vFeatCsv`→`richRow`) sees real `pv*` features, while the serial path
  nulls `t_curPath` after the first branch eval (`pv*`=0). The deployed
  floor/win nets consume `pv*` features, so `chosen` rows — and hence
  trajectories and labels — can differ on unverified seeds. Byte-identity was
  only spot-checked (1–3 seeds @100 sims), and the smoke diagnostics recorded
  from the deferred run (37.2% strict argmax-vs-chosen agreement) did NOT
  match the serial path (34.1% strict / 46.0% in-set, §104-style filter on
  1,055 valid groups). The plan also explicitly forbids C++ changes here.
- **Corrections applied (review findings):**
  - `build/sp_smoke.csv` had accumulated 12,488 rows (same 10 seeds twice)
    because `strategicgen2` appends without dedup. It was truncated and the
    10-seed smoke re-run with the reverted serial code → 6,244 rows,
    380–771 rows/seed, 100% labelWon coverage, 2,363 distinct labelWon
    values (identical per-seed content to the original Phase-0 file; only
    seed-block ordering in the file varies across runs, dynamic OMP
    schedule). The training smoke now runs on the clean slice → **1,554
    groups with exactly one chosen row (all with a valid policy action)**,
    policy_top1 0.44→0.42, q_top1 ~0.20, val_pol_ce 1.5204; export → 32
    parity checks (max err logit 3.87e-08, value 8.92e-08, Q 1.66e-07); the
    smoke native loads in `one_combat` with the full gate stack + vnet
    default + `S3-abl[...]=01010` at 64p.
  - The smoke .native was moved out of the git-tracked `selfplay/models/`
    into ignored `build/` — it is not a candidate artifact and must not be
    committed (only the Phase-2/3 control/candidate .native files may ship,
    with sha256 + docs).
  - The 1-seed @100-sim 60 s-budget mismatch remains a recorded verification
    limitation (schema already proven by the 10-seed smoke); no code change
    is justified.
- Status: Phase 0 verification-complete on the exact serial code the GCP
  datagen will use. Phases 1–3 remain the manual GCP follow-up.

## Follow-up (same day, recovery-fix session — reversion verified complete)

**Decision:** complete the reversion described in the section above so the
tree actually contains no C++ change, and make every provenance claim in the
logs true against the working tree.

- **Code:** the deferred-branch `omp taskgroup` parallelization was fully
  removed from `apps/one_combat.cpp`; `git diff apps/one_combat.cpp` is now
  empty (byte-identical to HEAD), restoring the plan's no-C++-change
  constraint. The serial path was always the only path for nSeeds ≥ threads
  (the 500-seed GCP chunks); it is now the only path everywhere.
- **Smoke regenerated on the serial path:** `build/sp_smoke.csv` was truncated
  and re-run from scratch (`strategicgen2 10 1000 0`, same envs; 315 s wall
  @12 threads) → 6,244 rows, 380–771 rows/seed, 100% labelWon coverage, 2,363
  distinct labelWon; per-seed rows byte-identical to the original Phase-0
  serial file (`build/sp_smoke_phase0.csv`), confirming determinism. The
  §104-style diagnostic reproduces the recorded numbers exactly: 34.1% strict
  / 46.0% in-set on 1,055 groups; per-screen EVENT 41.4/50.0, MAP 51.9/56.3,
  REST 50.0/59.7, REWARDS 29.5/45.1, SHOP 15.7/15.7.
- **Trainer/export re-run on the clean slice:** 2-epoch CPU smoke → 1,554
  groups with exactly one chosen row (all with a valid policy action),
  policy_top1 0.44→0.42, q_top1 ~0.20, val_pol_ce 1.5204; export → 32 parity
  checks (max err logit 3.87e-08, value 8.92e-08, Q 1.66e-07). The smoke
  .native was removed from git-tracked `selfplay/models/` — it now exists only
  under ignored `build/ooc_strategic_tok_smoke.native` and must not be
  committed.
- Status: Phase 0 verification-complete on the serial code the GCP datagen
  will use. Phases 1–3 remain the manual GCP follow-up.

## Addendum (same day) — §138 quick partial-data feel-run

A 160k-row chunk-1 snapshot was used for a quick V4-tok retrain + 64-seed
paired feel-run (recorded EXPERIMENTS.md §138): deployed 54.7% vs partial
28.1% (Δ −26.6pp, CI excludes zero). Informal only — the candidate used ~20%
of the planned corpus; the 5.7.3 verdict still requires the same-recipe
control vs the full 1500-seed candidate plus the 256-seed paired gate.
