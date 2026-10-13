# Pre-registration: greedy vs bundle-planner shops in rollout3 combo leaf rollouts (ledger §459)

Written and committed before any cohort seed ran. Philipp's request, 2026-10-13 in the project thread "Can we
investigate how the shop planner works in the ooc MCTS?": "I think we can just buy the best greedily in the
rollout" (20:08Z), then "Deck size should be on. And yes test on fresh seeds with 8 workers" (20:26Z). Pairs
128, 8 workers ([NPAIRS](NPAIRS)).

## Question

Inside OOC MCTS leaf rollouts, a shop is played by the policy chain: the V4 one-ply shop gate, then
`nativeShopPlan`, which scores every affordable subset of cards and relics (with or without the best removal) and
executes the first item of the best bundle. `STS_OOC_MCTS_ROLLOUT_SHOP=greedy` (#523) instead scores leaving, each
affordable item alone and the best removal alone, and buys the single best one, asking again on the next decision.
Does greedy rollout shopping change how §433 `combo` plays, in wins and in CPU? Descriptive question; no hypothesis
about the sign. **Inference:** greedy is cheaper per rollout shop step (§437/§442 put a large share of rollout
CPU in the bundle planner).

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting |
|---|---|
| `planner` | §433 `combo` (4096 simulations, `WIDEN_K=4`, `WIDEN_ALPHA=0.75`, `LEAF_COMBATS=3`, native leaf, V4 prior and leaf policy, V4 shop gate, flat exact-10k Silver, production CTM) with `STS_OOC_MCTS_ROLLOUT_SHOP=planner` |
| `greedy` | the same with `STS_OOC_MCTS_ROLLOUT_SHOP=greedy` |

Both arms pin the current defaults so a later default change cannot reach this run: `STS_OOC_PUBLIC_FUTURES=8`
(ADR-0028), `STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt` (ADR-0029) and
`STS_OOC_SHOP_DECK_SIZE_FIX=1` (ADR-0030, made default in the same PR on Philipp's word). `arm_env.sh` checks the
§433 combo lines exist exactly once and that §433 sets none of the pinned keys. The two arm environments differ
in exactly one line (`STS_OOC_MCTS_ROLLOUT_SHOP`). Each unit writes its `STS_*` environment to `ARM-SEED.env`.

What the option changes in code: only `nativeShopPlan` calls made while `NativeOocGreedyShopScope` is alive, which
the OOC MCTS leaf continuation step sets when the option is on. Live shop roots (searched by the tree), the live
fallback chain after a root abort, and every other decision type are unchanged.

## Provenance

- Code commit `440cf556` ([CODE_COMMIT](CODE_COMMIT), PR #523 head after the ADR-0030 commit). Each worker builds
  `one_combat` and refuses to run unless its sha256 equals [binary.sha256](binary.sha256). The run commit may
  differ from it only in docs and tools.
- **Seeds 89000000 .. 89000000+NPAIRS−1**, fresh, both arms on every seed. Worker W runs seeds
  89000000+16(W−1) .. +15 in both arms (32 one-seed units, 4 at a time). Smoke seeds 74050003–74050004 (planning
  container, [SMOKE.md](SMOKE.md)).
- Per-unit timeout 8 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds
  drop out of the pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/x459-wNN/out/`). When all 32 are done the worker uploads
  `/mnt/project-files/ooc-greedy-shop-459/wNN.tar` and then `wNN.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_ooc_greedy_shop_459.py](../../../../tools/analyze_ooc_greedy_shop_459.py))

Pairs: cohort seeds with a result row in both arms. **Primary:** Δwin = win(greedy) − win(planner), paired seed
bootstrap 95% CI (10,000 resamples, seed 459).

- **BETTER** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary (descriptive):** exact McNemar p, Δfloor (CI), Δ end HP, boss deaths, mean floor, seconds per run, MCTS
CPU per run, owned and fallback share, support aborts and simulations per run.

**Reading.** `combo` won about 87–89% in §433/§449. 128 pairs resolve about ±7 pp, so only a large win-rate
difference will be shown. NOT_SHOWN does not mean equal. The CPU difference is the other quantity of interest.

## Validity

- All units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained.
- Every unit's `.env` holds `STS_OOC_PUBLIC_FUTURES=8`, the pinned `STS_WIN_NET`, `STS_OOC_SHOP_DECK_SIZE_FIX=1` and
  its arm's `STS_OOC_MCTS_ROLLOUT_SHOP`; every log prints `[ooc-mcts-config]` with `"leafValue":"native"`,
  `"leafCombats":3`, `"simulations":4096`, `"wideningK":4`, `"wideningAlpha":0.75`, `"prior":"policy"`,
  `"leafPolicy":"v4"`, and `[native OOC shop deck-size correction ON]`; `greedy` logs carry `rollout_shop=greedy`
  in the `[live OOC MCTS ON …]` banner, `planner` logs do not.

## Decision

No default change from this run alone. Philipp decides whether greedy becomes the rollout default.
