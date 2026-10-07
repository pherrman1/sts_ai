# #347 boss-entry budget rescue on #417 sources (plan, 2026-10-07)

Status: draft for independent pre-run review. Nothing below the smoke has run.

## Question and decision

Does raising native Silver's flat per-root budget from 10,000 to 40,000
simulations win boss fights that 10k lost, starting from the **identical**
boss-entry states that the #417 pilot policies produced?

- Repeated rescues make combat-search/decision diagnosis the next priority.
- Little rescue makes a preparation counterfactual the next investigation.
- Failure to rescue does not show bad preparation or an unwinnable fight.

This is a small, failure-enriched diagnostic, not a win-rate qualification.
It does not estimate full-run improvement or how much of the #417 MCTS
regression is caused by combat.

## Sources (frozen before any challenger run)

`select.py` reads only the historical #417 rows (evidence ref `10e56bd8`,
`run/flat10k*.csv` and `run/mcts*.csv`) and writes `selection.json`: the boss-loss
census, the complete eligibility lists and the eight selected sources.

- Boss identity comes from each row's recorded `deathEncounter` (enum values
  parsed from `include/constants/MonsterEncounters.h`), not the death floor.
  Census: flat10k 24/28 losses at a boss (act 1/2/3: 2/10/12), mcts 44/56
  (3/14/27), matching the #417 README.
- Stratum R: mcts boss loss where the same seed's flat10k run won (31 eligible).
  Stratum C: flat10k boss loss, seed not selected into R (24 eligible).
- Within a stratum, round-robin over acts 1, 2, 3 skipping empty buckets;
  within a bucket ascending `sha256("boss-loss-347-pilot-v1:{stratum}:{seed}:{act}")`.
  R has no act-1 candidate (no act-1 mcts boss loss had a flat10k win).
- No shortfall. No replacement of a selected entry after any replay result or
  validity failure.

| stateId | source arm | boss | historical floor |
|---|---|---|---|
| R1-48000024-a2 | mcts | CHAMP | 33 |
| R2-48000014-a3 | mcts | DONU_AND_DECA | 50 |
| R3-48000116-a2 | mcts | CHAMP | 33 |
| R4-48000095-a3 | mcts | TIME_EATER | 50 |
| C1-48000062-a1 | flat10k | SLIME_BOSS | 16 |
| C2-48000039-a2 | flat10k | COLLECTOR | 33 |
| C3-48000055-a3 | flat10k | DONU_AND_DECA | 50 |
| C4-48000050-a1 | flat10k | SLIME_BOSS | 16 |

Smoke (`smoke_select.py`, never pooled): per stratum the unselected eligible
candidate with the lowest rank key: `smokeR-48000117-a3` (mcts, AWAKENED_ONE)
and `smokeC-48000109-a3` (flat10k, DONU_AND_DECA).

## Capture and reconstruction

No replayable checkpoint exists for these runs, so each selected source is
reconstructed. The old `bossheadroom347gen` collector (`runCombatEvalGenSeed`)
calls only `runFullRunOocPolicyStep`; it never calls `oocMctsPolicyStep`, so it
cannot produce an MCTS source even with `STS_OOC_MCTS=1`.

`one_combat bossrescue347 1 SELECTION STATE_ID OUT_PREFIX` therefore calls the
ordinary `runFullRunOOC` (the `bestbench` path, live OOC MCTS when the arm
enables it) under the source's recorded #417 arm environment (`arm_env.sh` at
`10e56bd8`, SHA-256 checked by `run.sh`). A research-only `t_bossEntryHook`
in `run_driver.cpp` runs at each boss battle after the budget is set and before
Silver initializes the battle, and again after the battle exits. At the
selected act's boss it keeps a `VwinBossEntry`: a `detachedCounterfactualCopy`
of the `GameContext` (all RNG streams), the path, a copy of the
`ScumSearchAgent2` (budget, agent RNG) and the OOC policy thread state. It turns
on action recording for that fight only, which changes no decision.

Historical fidelity: #420 (Necronomicurse) and #421 (act 2/3 first-strong
exclusions) changed run mechanics after the #417 baseline `5e9583cc`; their
`src/` diff touches only `Deck::remove`, `obtainRelic` and
`populateFirstStrongEnemy`, not combat. The diagnostic build is therefore the
research change applied to `5e9583cc`: commit `e6b6122a` (parent `5e9583cc`,
same patch as `dbf6f573` on `main`), merged into the task branch. Both
reconstruction and every replay arm run this one binary. Models are identical
between `5e9583cc` and `main` and are hash-listed below.

A source is **reproduced** only if the reconstructed run matches its
historical row exactly (`won, floor, act, hpEnd, maxHp, fightsLost,
deathCombat, deathEncounter`), the hook saw the expected boss, the captured
budget is 10,000 and that fight was lost. Otherwise the entry is a
reproduction failure; it is kept and reported, never replaced.

## Replays

Every replay is `vwinRunBossArm` on a fresh detached copy of the entry and a
fresh copy of the entry agent: native Silver, flat exact root budget,
`STS_SILVER_EXACT_ROOT_BUDGETS=1`, learned stopping and adaptive budgeting off,
reuse cap 32,768 in all arms (the mode refuses anything else), the same fair
information boundary, models, terminal scoring and potion handling. No OOC
decision is rerun inside a combat comparison. Per entry, in this order:

1. `control`: original planner seed, 10k. Must reproduce the source fight:
   outcome, raw terminal HP, full action trace, post-exit state digest
   (HP, max HP, gold, potions, relic counters, deck, all GameContext RNG
   streams) and simulation count.
2. Four planner repeats `rep = 0..3`, A (10k) and B (40k) with the same fresh
   planner seed, order A,B for even and B,A for odd reps.
3. `control_repeat` (original seed, 10k) and `A_repeat` (rep 0, 10k): must equal
   the first `control` and `A` rep 0. Arm order cannot leak into a replay.

Planner seeds: `int(sha256("boss-rescue-347-planner-v1:{stateId}:{rep}")[:16], 16)`,
a domain separate from selection. Native Silver seeds its search from
`nativeSilverBattleSeed` of the game seed (search-view RNG streams) and its
rollout RNG from the root state's seed. The research-only thread-local
`g_nativeSilverPlannerSeedOverride` replaces the game seed in each search root
only, so both are reseeded; the live battle and its RNG streams, which decide
the real future, are untouched, and no hidden state reaches the search.
These are planner repeats on one fixed environment, not four independent game
futures.

Budget check: native Silver now counts SilverSearcher steps per searched root
(`searchSteps`, `minRootSteps`, `maxRootSteps`). Every row must have
`minRootSteps == maxRootSteps == budget`. Exact root budgets search every root,
including one-action roots, so no singleton fast path applies; reroot and fresh-
root counts are reported because the 32,768-node reuse cap discards reuse more
often at 40k (same cap in both arms, by design).

Total cost: 8 reconstructions (4 mcts, 4 flat10k runs to the boss), 8 control
replays, 64 comparison continuations, 16 repeat checks.

## Execution

From a checkout of the frozen plan commit, on one 4-CPU container, one thread
per process, four workers:

```text
run.sh BIN BIN_SHA256 e6b6122a013e4ab781c780e25a44d2006454e150 OUT \
  docs/experiments/evidence/boss_budget_rescue_347_pilot_20261007/selection.json
python3 docs/experiments/evidence/boss_budget_rescue_347_pilot_20261007/analyze.py \
  docs/experiments/evidence/boss_budget_rescue_347_pilot_20261007/selection.json OUT --out report.json
```

Each command goes through `tools/seed_guard.sh`. A failed process is kept and
not retried.

## Analysis and routing (predeclared)

`analyze.py` validates every entry: all expected rows present exactly once,
planner seeds re-derived, A/B pairs share the seed, budgets 10k/40k, all start
digests equal the entry digest, budgets spent at every root, repeats identical,
control equals source, and the rows file hash matches the entry manifest.

Primary outcome: boss victory, paired by entry and planner seed. Per entry:
A and B wins of 4, rescues (A loses, B wins), regressions (A wins, B loses),
first differing action of each A/B pair with trace pointers, raw terminal HP
before act-transition healing (and post-exit HP), potions left, simulations
and CPU. Paired HP differences are reported only where both arms win and are
not an overall benefit. Strata R, C and both together; the entry is the
cluster; the entry bootstrap (10,000 replicates, seed 20261007) is descriptive.

Routing rule (not a statistical gate):
- `COMBAT_HEADROOM_SIGNAL`: net additional B wins >= 4 over the 32 pairs and
  positive net rescue in >= 3 distinct entries.
- Otherwise `BUDGET_HEADROOM_INCONCLUSIVE`, with shape `negative` (net < 0),
  `flat` (no discordant pair) or `mixed`.
- Any schema, pairing, digest, budget or determinism failure:
  `EXECUTION_INVALID`. Only reproduction/parity failures or missing entries:
  `PARTIAL`. Affected rows are kept; no clean eight-state verdict is announced.

A negative result does not exclude combat weaknesses that more search cannot
fix. Preparation is not named as the cause without a preparation intervention.

## Provenance

- Starting `main`: `46153506`. Research change: `dbf6f573`. Diagnostic build
  source: `e6b6122a` (parent `5e9583cc`). Binary: `linux-gcc-release`,
  target `one_combat`, GCC 13.3; SHA-256 recorded in README at freeze.
- Models (SHA-256 prefix, unchanged since `5e9583cc`):
  `selfplay/models/ooc_strategic_tok_final.native` `e62abd833fc8cb90`,
  `models/v_win_trees.txt` `fc52c14cb7239a33`,
  `models/candidates/v_win_x2b_trees.txt` `a251b33d4f71c1aa`,
  `models/candidates/screen_leaf_gbm_v1.trees` `8e2f9dc78cb31de3`,
  `selfplay/models/combat_transition_deepsets_lizard_t2.native` `abb2a9ead6efd6b9`,
  `selfplay/models/combat_transition_near_full_except_smoke_v2.native` `e9a18951710fdfe9`,
  `models/v_rich_trees.txt` `3a3420469b1d648e`.
- Seeds: #417 pilot seeds only (`48000014`, `24`, `39`, `50`, `55`, `62`, `95`,
  `116`; smoke `48000109`, `48000117`). Selftest: #417 smoke seed `48009000`.
- RNG regime: project fair (`STS_FAIR=1`), Ironclad A0, keys off,
  `STS_STOP_AFTER_ACT=3`.

## Not in scope

No cohort expansion, budget sweep, other seeds, preparation counterfactual,
model or default change.
