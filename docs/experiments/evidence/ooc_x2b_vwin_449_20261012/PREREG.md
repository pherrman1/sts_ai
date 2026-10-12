# Pre-registration: rollout3 combo with the public X2-B win model vs B0 v_win (ledger §449)

Written and committed before any cohort seed ran. Philipp's request, 2026-10-12 in the project thread "Audit
models to retrain for §438": "x2-b should be exchanged", then "lets go?" (17:46Z) for the offered paired
rollout3 run of X2-B against `v_win`. The pair and worker count come from his answer to the size card in that
thread ([NPAIRS](NPAIRS)).

## Question

Deep OOC MCTS (§433 `combo`) values each leaf with the process win model `g_winNet` after three simulated combats.
That model is B0 `models/v_win_trees.txt`, which also scores rest and upgrade decisions in the native fallback.
§444 exported a public X2-B (`models/candidates/v_win_x2b_public_trees.txt`, X2-B recipe without `nextEliteId` and
`nextFight0..2`, held-out NLL 0.4236 vs X2-B 0.4226). Does swapping `STS_WIN_NET` to it change how `combo` plays?
Descriptive question; no hypothesis about the sign.

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting |
|---|---|
| `vwin` | §433 `combo` (4096 simulations, `WIDEN_K=4`, `WIDEN_ALPHA=0.75`, `LEAF_COMBATS=3`, native leaf, V4 prior and leaf policy, flat exact-10k Silver, current production CTM `pathb_r2_lizard` with the near-full brew fallback per §435) with `STS_WIN_NET=models/v_win_trees.txt` (the default, pinned) |
| `x2bpub` | the same with `STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt` |

Both arms pin `STS_OOC_PUBLIC_FUTURES=8` (the default since #496/ADR-0028). `arm_env.sh` sources §433's
`arm_env.sh`, checks the combo lines exist exactly once and that §433 sets neither `STS_WIN_NET`,
`STS_OOC_PUBLIC_FUTURES` nor `STS_OOC_MCTS_LEAF_WIN_MODEL`. The two arm environments differ in exactly one line
(`STS_WIN_NET`). Each unit writes its `STS_*` environment to `ARM-SEED.env`.

What `STS_WIN_NET` changes in code: `g_winNet` is loaded from the given path (`apps/one_combat.cpp` ~L3304; an
explicit path that fails to load exits nonzero). It is used by the MCTS native leaf, the native fallback rest and
upgrade scorer, and `vStateWin`. The floor model (`v_rich_trees.txt`) for card, shop and remove is unchanged.
**Inference:** X2-B was trained on MAP rows only, so its rest/upgrade values in the native fallback are
off-distribution; most rest/upgrade decisions are owned by the MCTS in `combo`.

## Provenance

- Code commit `94f78fbb` ([CODE_COMMIT](CODE_COMMIT), main after #497). Each worker builds `one_combat` and refuses to run
  unless its sha256 equals [binary.sha256](binary.sha256). The run commit may differ from it only in docs and tools.
- **Seeds 82000000 .. 82000000+NPAIRS−1**, fresh, both arms on every seed. Worker W runs seeds
  82000000+16(W−1) .. +15 in both arms (32 one-seed units, 4 at a time). Smoke seeds 82009000–82009001 (planning
  container, [SMOKE.md](SMOKE.md)).
- Per-unit timeout 8 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds
  drop out of the pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/x449-wNN/out/`). When all 32 are done the worker uploads
  `/mnt/project-files/ooc-x2b-vwin-449/wNN.tar` and then `wNN.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_ooc_x2b_449.py](../../../../tools/analyze_ooc_x2b_449.py))

Pairs: cohort seeds with a result row in both arms. **Primary:** Δwin = win(x2bpub) − win(vwin), paired seed
bootstrap 95% CI (10,000 resamples, seed 449).

- **BETTER** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary (descriptive):** exact McNemar p, Δfloor (CI), Δ end HP, boss deaths, mean floor, seconds per run, MCTS
CPU, owned and fallback share, support aborts and simulations per run.

**Reading.** §433's combo won 87.5%. 128 pairs resolve about ±7 pp, so only a large difference will be shown.
NOT_SHOWN does not mean equal.

## Validity

- All units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained.
- Every unit's `.env` holds the arm's `STS_WIN_NET` line and `STS_OOC_PUBLIC_FUTURES=8`; every log prints
  `[ooc-mcts-config]` with `"leafValue":"native"`, `"leafCombats":3`, `"simulations":4096`, `"wideningK":4`,
  `"wideningAlpha":0.75`, `"prior":"policy"`, `"leafPolicy":"v4"`, `"leafWinModel":null`.

## Decision

No default change from this run. Philipp decides whether X2-B replaces `v_win` (#397 rule: `v_win_trees.txt`
changes only on his decision).
