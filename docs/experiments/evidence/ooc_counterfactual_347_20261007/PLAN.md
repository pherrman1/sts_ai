# #347 OOC counterfactual on the #428 R seeds: chest rule and campfire fallback (plan, 2026-10-07)

Status: draft for independent pre-run review. Philipp asked (thread, 11:06 UTC)
for the chest fix ("always open the chest except when you have curse key") and
then this test of the campfire fallback.

## Question and decision

Ledger §389 found that on the four #428 R seeds OOC MCTS left every treasure
chest closed and rested at 24 of 27 campfires. Main gets the chest rule as a
fix. This run asks: with the chest rule in place, does handing OOC MCTS
campfire decisions to the ordinary flat10k chain produce boss entries that
fixed flat-10k Silver wins from more often?

Arms (all OOC MCTS 2048 sims, #417 `mcts` arm environment):

- **C**: OOC MCTS + chest rule (`STS_347_CHEST_RULE=1`: open every chest
  unless Cursed Key is held).
- **CR**: C + campfire fallback (`STS_347_CAMPFIRE_CHAIN=1`: campfire roots
  and campfire card selects go to the ordinary chain; MCTS keeps every other
  decision).

Primary comparison: CR vs C, paired by run seed and planner rep (shared
planner seeds). Secondary, descriptive only: C vs M and CR vs F against the
frozen #428 rows (same planner seeds; different build, see below).

Decision rule (primary, fixed before the run):

- `CAMPFIRE_CHAIN_SIGNAL`: net CR-only minus C-only wins >= +8 of 32 and at
  least 3 of 4 seeds net positive. Next: 32-pair paired full-run pilot on fresh
  seeds (53M range), MCTS+chest rule vs MCTS+chest rule+campfire fallback,
  after its own plan and review.
- `CAMPFIRE_CHAIN_HARM`: net <= -8 and at least 3 of 4 seeds negative.
- Otherwise `CAMPFIRE_CHAIN_INCONCLUSIVE`: campfire fallback not shown to
  matter at this scale; report the C vs M chest-rule recovery descriptively.

A run that dies before its target boss counts as a loss on all 8 reps (the
OOC policy reached no boss entry). Trajectories diverge in RNG after the first
changed decision, so this measures the total effect of the arm's OOC
trajectory on the reached boss entry, not an isolated campfire effect.
Four selected failure-enriched seeds; not a win-rate estimate.

## Baseline and provenance

- Branch `claude/ooc-divergence-347-x32yu5` (PR #429), base `main` `1e1bdc09`.
- Diagnostic build source: commit on top of `1ed47e5c` (the #389 trace build,
  parent `5549a16a` = #428 build on the #417 baseline `5e9583cc`), so the
  trajectories use #417 mechanics up to the first changed decision. SHA and
  binary SHA-256 recorded in README after build.
- Arm env: `arm_env.sh` at #417 ref `10e56bd8`, SHA-256 `cc0ec6aa…`, `mcts`.
- Models, RNG regime (`STS_FAIR=1`, Ironclad A0, keys off,
  `STS_STOP_AFTER_ACT=3`) and Silver configuration exactly as #428 PLAN.md:
  native Silver, flat exact 10,000 per root, adaptive and learned stopping off,
  reuse cap 32768.
- Planner seeds: #428 domain `boss-prep-347-planner-v1:{runSeed}:{act}:{rep}`,
  reps 0..7, independent of arm.

## Implementation (research-only, diagnostic build only)

- `run_driver.cpp`: `STS_347_CHEST_RULE` and `STS_347_CAMPFIRE_CHAIN`
  (default off; unset, behavior unchanged).
- `combat_datasets.cpp`: `bossrescue347` accepts a third selection schema
  `boss_prep_counterfactual_347_selection_v1`: specs carry no historical row or
  expected source outcome, declare `chestRule`/`campfireChain`, and the process
  refuses to run unless the `STS_347_*` environment matches the spec (old
  schemas require both flags off). Reaching the boss is recorded, not required.
  Capture, control parity, repeat checks, planner seeds and budget accounting
  are the #425/#428 code unchanged.

## Checks before the run

- Build `one_combat` (release) at the diagnostic commit.
- Compatibility: rerun #428 source `M-48000024-a2` with flags off under the
  #428 selection: must be `VALID` with rows identical to the frozen #428 rows
  except CPU/wall time.
- Independent pre-run review of the diagnostic diff, this plan, `run.sh` and
  `analyze.py`.

## Run and cost

`run.sh` over `selection.json` (8 sources) on one 4-CPU cloud container, four
workers. About 8 run reconstructions of ~3.5 min plus 80 boss replays: about
15 minutes. `analyze.py RUN_DIR FROZEN428_RUN_DIR --out report.json`.
Validity: every source `VALID` (control parity, repeats identical, budgets
spent); C traces show the chest rule at every treasure without Cursed Key; CR
traces show every campfire handled by the chain.
