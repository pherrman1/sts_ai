# Pre-registration: OOC MCTS without leaf rollout combats vs rollout3 on the current live defaults (ledger §472)

Written and committed before any cohort seed ran. Philipp's request, 2026-10-14 14:59Z, in the project thread
"With the new ooc MCTS, we explore deeper. Maybe we don't need the rollouts anymore. Can we test on 128 seeds
rollout 3 vs no rollout?". Pairs 128 ([NPAIRS](NPAIRS)); workers [NWORKERS](NWORKERS) (Philipp's pick).

## Question

Since ADR-0031 and ADR-0032 the live OOC MCTS applies the tree rules, merges equivalent outcomes and uses the greedy
rollout shop. With rules and merging the median per-search maximum tree depth rose from 2 to 4 (§464). Each leaf then
still plays three surrogate combats (`STS_OOC_MCTS_LEAF_COMBATS=3`) with the V4 leaf policy before the native win
model values it. Does dropping those leaf combats (`LEAF_COMBATS=0`) lose runs at Ironclad A0, and what does it save?

Prior evidence: §277 (2026-09-15, old V2 stack, 2048 simulations, 32 seeds) had rollout0 and rollout3 at 26 and 28
of 32, not separated. Nothing has compared them since the tree rules, outcome merging, public win model, Lizard CTM
or §433 settings.

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting |
|---|---|
| `rollout3` | the §464 `rulesmerge` arm with `STS_OOC_MCTS_ROLLOUT_SHOP=greedy`: §433 `combo` (4096 simulations, `WIDEN_K=4`, `WIDEN_ALPHA=0.75`, `LEAF_COMBATS=3`, native leaf, V4 prior and leaf policy, cpuct 1.5, visit-lock early stop) plus `STS_OOC_PUBLIC_FUTURES=8`, `STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt`, `STS_OOC_SHOP_DECK_SIZE_FIX=1`, `STS_OOC_MCTS_TREE_RULES=1`, `STS_OOC_MCTS_MERGE_OUTCOMES=1` (the ADR-0028 to ADR-0032 defaults, pinned explicitly) |
| `rollout0` | the same with `STS_OOC_MCTS_LEAF_COMBATS=0` |

The two arms' environments differ in exactly that one line. (`LEAF_COMBATS` itself defaults to 0 in code; §433 and every later
comparison set it to 3.) What `LEAF_COMBATS=0` does
(`OocGameContextModel` leaf evaluation in `apps/one_combat/ooc_mcts_adapter.cpp`): a leaf already on the map screen is
valued by the native win model at once; any other leaf is advanced by the same V4 leaf policy (and, if it stands in a
combat, one CTM combat) only to the next map screen and valued there. With `LEAF_COMBATS=3` the leaf instead plays on
until three more combats are resolved and is valued at the following map screen. So "no rollout" means no extra
combats, not literally zero continuation steps. Everything else (simulations, early stop, tree rules, merging,
real Silver combat, V4 fallback) is unchanged.

Both arms set `STS_OOC_MCTS_DECISION_LOG=ARM-SEED.decisions.jsonl` (observation only, §464). Each unit writes its
`STS_*` environment to `ARM-SEED.env`. Ascension 0 (the §433 configuration is A0, and every §459–§464 comparison was
A0).

## Provenance

- Code commit = [CODE_COMMIT](CODE_COMMIT) = `main` after #534. Each worker builds `one_combat` and refuses to run
  unless its sha256 equals [binary.sha256](binary.sha256). The run commit may differ from it only in docs and tools.
  Both arms run on this binary.
- **Seeds 101000000 .. 101000127**, fresh (assigned by the coordinator), both arms on every seed. Seed i goes to
  worker (i mod NWORKERS) + 1; one-seed units, 4 at a time. Smoke seed 74070600 (planning container,
  [SMOKE.md](SMOKE.md)); seeds 74070601–649 stay with this thread, 74070650–699 belong to the pre-launch reviewer.
- Per-unit timeout 4 h. Silver stalls caught by `bestbench` (`[bestbench-seed-failure]`) drop that seed. A unit whose
  log stops growing for 60 min is a stall: the worker takes a backtrace into `stall-ARM-SEED.txt` and kills that
  `one_combat`; the seed drops out of the pairs. No seed is rerun or replaced. A container restart reruns an
  interrupted unit whole (deterministic).
- Units write to the worker's local disk (`$HOME/x472-wWW/out/`). When all are done the worker uploads
  `/mnt/project-files/ooc-rollout0-472/wWW.tar` and then `wWW.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_ooc_rollout0_472.py](../../../../tools/analyze_ooc_rollout0_472.py))

Pairs: cohort seeds with a result row in both arms. **Primary:** Δwin = win(rollout0) − win(rollout3), paired seed
bootstrap 95% CI (10,000 resamples, seed 472).

- **BETTER** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary:** **NONINFERIOR_AT_10PP** if the CI lower bound > −10 pp, else NOT_NONINFERIOR_AT_10PP (the §412
margin). **Descriptive:** exact McNemar p, Δfloor (CI), Δ end HP, boss deaths, mean floor, seconds and MCTS CPU per
run and their rollout0/rollout3 ratios, owned and fallback share, support aborts, simulations per run, per-run and
per-search tree depth, and the share of searched roots whose pick equals the top-prior or top-Q candidate.

**Reading.** 128 pairs resolve about ±7 pp. NOT_SHOWN does not mean equal; a 10 pp non-inferiority margin is wide
and does not show the arms equal either.

## Validity

- All units rc=0 apart from listed stall or seed failures; any other nonzero rc, crash or missing seed makes the
  result INVALID until explained.
- Every unit's `.env` holds the pinned public futures, X2-B win net, greedy rollout shop, deck-size fix 1, tree
  rules 1, merging 1 and the decision-log path; `rollout0` units and only they hold `STS_OOC_MCTS_LEAF_COMBATS=0`,
  `rollout3` units hold `=3`. Every log prints `[ooc-mcts-config]` with `"simulations":4096` and the arm's
  `"leafCombats"`.

## Decision

No default change from this run alone; the rollout depth is a research setting of the opt-in OOC MCTS
(`STS_OOC_MCTS` stays off by default, ADR-0027). **BETTER**, or **NOT_SHOWN** with **NONINFERIOR_AT_10PP** and
clearly lower CPU, makes rollout0 a candidate for the OOC MCTS research configuration (its own decision, with
Philipp). **WORSE** keeps rollout3. Philipp decides what comes next.
