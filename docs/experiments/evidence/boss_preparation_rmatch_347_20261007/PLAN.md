# #347 boss-preparation R-match on #417 sources (plan, 2026-10-07)

Status: draft for independent pre-run review. Nothing below the smoke has run.

## Pre-review checks already run (diagnostic binary above, never pooled)

- #425 selftest `bossrescue347selftest 1 48009000 1000` (flat10k arm): all eight
  checks PASS ([fixtures/selftest425.log](fixtures/selftest425.log)).
- #425 compatibility: frozen #425 entry `C1-48000062-a1` rerun with the old
  selection under this binary: `VALID`, rows identical to the frozen #425 rows
  on every column except `cpuSeconds`/`wallSeconds` (and executable provenance)
  ([fixtures/compat425/](fixtures/compat425/)).
- Old schema plus `expectedSourceWon` is refused before any run
  ([fixtures/old_schema_with_expected.log](fixtures/old_schema_with_expected.log)).
- sourceWin=1 fixture: the smoke F source with `expectedSourceWon` flipped to 0
  ends `INVALID source_boss_not_lost`, exit 3 ([fixtures/flip.log](fixtures/flip.log)).
- `analyze.py --self-test` PASS (includes sourceWin=1 parity, M/F pairing,
  routing and shape fixtures).
- Smoke `smoke.json` ([smoke/](smoke/)): seed 48000117, both arms, two planner
  reps. Both sources `VALID`: reconstruction matched the #417 rows, M source
  lost and F source won Awakened One, controls reproduced outcome, raw HP,
  trace, post-exit digest and simulations; repeats identical; every root ran
  exactly 10,000 steps; M and F fresh rows use the same planner seeds
  (`73db6a027ccffa44`, `42673263efb84a75`). The M log shows
  `leafValue":"screengbm"` / 2048-sim live OOC MCTS. Smoke outcome
  (descriptive only): M 0/2, F 2/2; entries 69/85 vs 96/96.

## Question and decision

For the four #417 seeds where the OOC-MCTS arm died at a boss and the flat10k
OOC arm won the full run (the frozen #425 R seeds), does the flat10k OOC
trajectory produce a boss-entry state that fixed flat-10k native Silver wins
from more reliably than the MCTS-produced entry?

Hypothesis: the flat10k OOC policy produced materially stronger boss-entry
states on these matched seeds than OOC MCTS did.

This measures the **total** effect of the OOC trajectory on the reached boss
entry. The two OOC policies can consume RNG differently before the boss, so the
captured entries may carry different, legitimate environment RNG states. The
experiment does **not** hold the combat future fixed and does **not** isolate a
deck/HP preparation effect. Held fixed: source run seed, act/boss stratum,
combat algorithm and configuration, combat budget, planner-seed schedule.

- `PREPARATION_HEADROOM_SIGNAL`: prioritize localizing which OOC decisions made
  the flat entries stronger (card/reward, rest vs upgrade, shops, route/elites,
  relics/potions; earliest consequential divergence), then the cheapest
  counterfactual around one recurring decision family. No new model or boss
  heuristic first.
- `PREPARATION_HEADROOM_INCONCLUSIVE`: preparation is not shown equivalent (four
  selected, failure-enriched seeds); return to #347 and consider another
  explanation rather than expanding this experiment.

Failure-enriched attribution evidence, not a full-run win-rate estimate.

## Baseline and provenance

- Execution baseline: `main` `866e8c32353161eefa5a4430651d99e2e2d68329`, the
  merge of #425 (parents `a1eea347`, `3f88c1e9`), the first `main` commit that
  contains corrected #425.
- Historical #417 gameplay baseline `5e9583cc`; #425 diagnostic build source
  `e6b6122a` (#425 research patch on `5e9583cc`).
- This experiment's diagnostic build source: `5549a16a245e1453d0315d2a19b0265ec3b10692`
  (parent `e6b6122a`; adds only the change below), merged into the task branch.
  Binary `linux-gcc-release`, target `one_combat`, GCC 13.3, SHA-256
  `b9dc45ad12fd6cc75faf4f0c21d488868cfc5451456ca513c9e675a74531de0b`.
  Reconstruction and every replay run this one binary, so #420/#421 (later
  act 2/3 OOC mechanics) cannot change the trajectories.
- Arm environment: `arm_env.sh` at #417 evidence ref `10e56bd8`, SHA-256
  `cc0ec6aa1f22bdb537280fedc8992080c35f1a8d2acd4e975305e0f956c6cc97`, checked by
  `run.sh` (`mcts` for M, `flat10k` for F).
- Models (SHA-256 prefix, identical at `5e9583cc` and `866e8c32`):
  `selfplay/models/ooc_strategic_tok_final.native` `e62abd833fc8cb90`,
  `models/v_win_trees.txt` `fc52c14cb7239a33`,
  `models/candidates/v_win_x2b_trees.txt` `a251b33d4f71c1aa`,
  `models/candidates/screen_leaf_gbm_v1.trees` `8e2f9dc78cb31de3`,
  `selfplay/models/combat_transition_deepsets_lizard_t2.native` `abb2a9ead6efd6b9`,
  `selfplay/models/combat_transition_near_full_except_smoke_v2.native` `e9a18951710fdfe9`,
  `models/v_rich_trees.txt` `3a3420469b1d648e`.
- RNG regime: project fair (`STS_FAIR=1`), Ironclad A0, keys off,
  `STS_STOP_AFTER_ACT=3`.

## Sources (frozen before any comparison run)

`select.py` reads the #417 rows (`run/flat10k*.csv`, `run/mcts*.csv` at
`10e56bd8`) and the frozen #425 `selection.json`, requires both to agree, and
writes `selection.json` (schema `boss_preparation_rmatch_347_selection_v1`,
`plannerReps` 8) and `smoke.json` (`plannerReps` 2).

| run seed | act | boss | M source (mcts arm, #417 row) | F source (flat10k arm, #417 row) |
|---|---|---|---|---|
| 48000024 | 2 | CHAMP | `M-48000024-a2`, lost floor 33 | `F-48000024-a2`, won run, 51/80 |
| 48000014 | 3 | DONU_AND_DECA | `M-48000014-a3`, lost floor 50 | `F-48000014-a3`, won run, 50/80 |
| 48000116 | 2 | CHAMP | `M-48000116-a2`, lost floor 33 | `F-48000116-a2`, won run, 75/128 |
| 48000095 | 3 | TIME_EATER | `M-48000095-a3`, lost floor 50 | `F-48000095-a3`, won run, 23/117 |

Expected source fight outcome: M `expectedSourceWon=0`, F `expectedSourceWon=1`.
Smoke (never pooled): the #425 smoke R seed `48000117` (act 3, AWAKENED_ONE),
both arms, two planner reps. No replacement of a frozen source after any
result or validity failure.

## Implementation (smallest compatible extension of #425)

The `bossrescue347` mode accepts a second selection schema. Under the old
schema (`boss_budget_rescue_347_pilot_selection_v1`) nothing changes: 4 reps,
A 10k / B 40k, `boss-rescue-347-planner-v1:{stateId}:{rep}`, source fight must
be lost, and a spec carrying `expectedSourceWon` is refused. Under the new
schema each spec declares `expectedSourceWon` (0 or 1) and the source fight must
equal it (`source_boss_not_lost` / `source_boss_not_won`); replays are
`control` (original planner seed, 10k), `fresh` reps `0..plannerReps-1`
(10k, arm label `10k`), `control_repeat` and `fresh_repeat` (rep 0). The entry
JSON adds `entryDescriptor`: HP/max HP, gold, potions and capacity, deck size,
full deck, upgrade count, relics with counters, act/floor/boss, every
GameContext RNG stream counter plus an RNG digest, and `PathHistory.roomVisits`
(the only path summary the production path already keeps). Capture
(`BossEntryHook`, `VwinBossEntry`, `detachedCounterfactualCopy`), replay
(`vwinRunBossArm`), planner-seed override, budget accounting, digests, trace
parity and the run-row reconstruction checks are the #425 code unchanged.
No OOC decision trace is added; `apps/one_combat/run_trace` is not used.

## Reconstruction and parity (per source)

A source is valid only if:
1. the reconstructed full run (`runFullRunOOC`, same arm env) matches its #417
   row on `won, floor, act, hpEnd, maxHp, fightsLost, deathCombat,
   deathEncounter`;
2. the hook saw the expected boss in the target act, budget 10,000;
3. the source fight outcome equals `expectedSourceWon`;
4. the original-seed 10k `control` reproduces the source outcome, raw terminal
   HP, full action trace, post-exit state digest and simulation count;
5. `control_repeat` and `fresh_repeat` equal `control` and `fresh` rep 0;
6. every row starts from the entry digest and every searched root runs exactly
   10,000 SilverSearcher steps (exact root budgets, so no singleton bypass).

## Planner seeds and pairing

`int(sha256("boss-prep-347-planner-v1:{runSeed}:{act}:{rep}")[:16], 16)`,
rep 0..7. The key excludes the preparation arm and the stateId, so M and F of a
seed get identical search randomness per rep; the analyzer also checks the M
and F rows' seeds are equal. As in #425 the research-only thread-local
`g_nativeSilverPlannerSeedOverride` replaces the game seed only inside each
Silver search root; the live battle and its RNG streams are untouched, no
state is copied between the M and F entries, and no hidden information reaches
the search. Environment futures are **not** paired: each entry carries its
own legitimate RNG state.

## Combat configuration

Native Silver, flat exact 10,000 simulations per searched root
(`STS_SILVER_EXACT_ROOT_BUDGETS=1`), adaptive and learned stopping off, reuse
cap mode `allocated` (32,768, enforced by the mode), the same search constants,
models, potion handling and fair-information boundary in both arms. No OOC
policy runs after capture inside a comparison. No 40k arm.

Cost: 8 reconstructions, 8 controls, 64 fresh continuations, 16 repeat checks.

## Execution

From a checkout of the frozen plan commit, one 4-CPU container, one thread per
process, four workers:

```text
run.sh BIN b9dc45ad12fd6cc75faf4f0c21d488868cfc5451456ca513c9e675a74531de0b \
  5549a16a245e1453d0315d2a19b0265ec3b10692 OUT \
  docs/experiments/evidence/boss_preparation_rmatch_347_20261007/selection.json
python3 docs/experiments/evidence/boss_preparation_rmatch_347_20261007/analyze.py \
  docs/experiments/evidence/boss_preparation_rmatch_347_20261007/selection.json OUT --out report.json
```

Every process goes through `tools/seed_guard.sh`. A failed process is kept and
not retried.

## Analysis and routing (predeclared)

Primary outcome: boss victory under fixed 10k Silver. Pair M/F by run seed +
rep. Per seed: M wins/8, F wins/8, F-only, M-only, net = F-only − M-only, raw
terminal HP and potions where won, and entry descriptor differences (F − M:
HP, max HP, gold, potions, deck and relic multiset differences, upgrades, RNG
counters that differ, room-visit counts). The run seed is the uncertainty
cluster; the 32 comparisons are not 32 independent game seeds. A seed-cluster
bootstrap of mean net per seed (10,000 replicates, seed 20261007) is
descriptive only.

Routing (not a statistical threshold):
- `PREPARATION_HEADROOM_SIGNAL` iff F has >= 8 net additional boss wins over M
  across the 32 comparisons AND positive net on >= 3 of the 4 seeds.
- Otherwise `PREPARATION_HEADROOM_INCONCLUSIVE`.
- Shape: `flat` (no discordant pair), `negative` (net < 0),
  `consistent_positive` (net > 0 and no seed net < 0), else `mixed`.
- Any schema, pairing, digest, budget, planner-seed or determinism failure:
  `EXECUTION_INVALID`. Only reconstruction/parity failures or missing outputs:
  `PARTIAL` (a seed with either source invalid is not compared).

Sanity expectation: original-seed controls reproduce M losses and F wins
exactly. If the M/F difference largely disappears under fresh planner seeds,
that is reported explicitly: the selected #417 outcomes would then be mostly
combat-planner-seed sensitivity, not a robust boss-entry advantage.

## Not in scope

No 40k/100k sweep, new OOC model, CTM or X2-B change, boss heuristic, policy
distillation, tracing infrastructure, synthetic RNG/future matching, full-run
benchmark or win-rate claim. No default or production behavior change.
