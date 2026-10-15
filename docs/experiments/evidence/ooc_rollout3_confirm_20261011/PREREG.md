# Pre-registration: fresh-seed confirmation of rollout3 at 4096 simulations with broad chance widening (ledger §433)

Written and committed before any cohort seed ran. Philipp's go: 2026-10-11 21:04Z in project thread "OOC MCTS 10-floor
depth feasibility", "yes good idea, lets do that", answering the suggested next step after §427–§430: "a fresh-seed
confirmation of 4096 sims plus more chance outcomes combined".

## Question

On seeds no earlier OOC MCTS screen has seen, does rollout3 with 4096 simulations and broad chance widening win more runs
than MCTS off? Secondary: does it win more than rollout3 at 2048, and does §422's rollout3 gain replicate?

§427 (`s4096`, +3.1 pp vs rollout3) and §429 (`wbroad`, +1.6 pp, +0.72 floors [+0.11, +1.44]) were the best two of the
four one-setting variants on the §422 seeds; neither was shown better than rollout3. The combination is new: it was
never run. Selecting it on the §422 seeds is why this confirmation uses fresh seeds.

## Arms ([arm_env.sh](arm_env.sh)), all run fresh

| arm | setting |
|---|---|
| `combo` | §422 rollout3 environment with `STS_OOC_MCTS_SIMS=4096`, `STS_OOC_MCTS_WIDEN_K=4`, `STS_OOC_MCTS_WIDEN_ALPHA=0.75` |
| `rollout3` | §422 rollout3 environment, unchanged (2048 simulations, `K=2`, `alpha=0.5`, 3 rollout combats, production pathb-r2 CTM) |
| `off` | §422 MCTS off, unchanged (the §411 research base with flat exact-10k Silver, not the production defaults) |

`arm_env.sh` sources §422's `arm_env.sh`; `combo` refuses to run unless each replaced line occurs exactly once.

## Provenance

- Code commit `f82eeadd` ([CODE_COMMIT](CODE_COMMIT)): current main (`07a93e36`, which includes the §431 generator
  policy unification and §432) merged with the §427–§430 code. All three arms run on this binary, so no earlier run is
  reused as a control. The run commit may differ from it only in docs and tools ([worker.sh](worker.sh) refuses
  otherwise). Each worker builds `one_combat` and refuses to run unless its sha256 equals [binary.sha256](binary.sha256)
  (`bab14cd5…`); `oocmctsselftest` passes on it.
- **Seeds 76000000–76000255** (fresh; 256 seeds; block assigned by the coordinator). 8 workers (Philipp chose "8 workers" on
  the decision card, 21:10Z); worker W runs seeds 76000000+32(W−1) .. +31 in all three arms as 96 one-seed units, 4 at a
  time, `combo` first.
- Smoke (planning container, this binary and `run_unit.sh`): `combo` 76009000, `rollout3` 76009001, `off` 76009002, see [SMOKE.md](SMOKE.md).
- Expected cost (**Inference** from §427/§429: 1,784 and 988 s per run; 936 s for rollout3, 57 s for off): about
  1,900 s per `combo` run, so about 2,900 s per seed for all three arms, about 205 CPU-hours, about 6.5 h per 4-CPU worker.
- Per-unit timeout 6 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds drop out
  of the pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/r3c-wNN/out/`). When all 96 are done, the worker uploads
  `/mnt/project-files/ooc-rollout3-confirm/wNN.tar` and then `wNN.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_rollout3_confirm.py](../../../../tools/analyze_rollout3_confirm.py))

Pairs: cohort seeds with a result row in all three arms. **Primary:** Δwin = win(combo) − win(off), paired seed bootstrap
95% CI (10,000 resamples, seed 433).

- **CONFIRMED** if the CI lower bound > 0;
- **WORSE_THAN_OFF** if the CI upper bound < 0;
- otherwise **NOT_CONFIRMED**.

**Secondary (descriptive):** combo − rollout3 and rollout3 − off, each with its CI; exact McNemar p, Δfloor (CI) and
Δ end HP; boss deaths, seconds per run, MCTS CPU, owned and fallback share, support aborts and simulations per run.

**Reading.** On the §422 seeds `s4096` and `wbroad` beat off by +14.1 and +12.5 pp; 256 pairs resolve about ±6 pp against
off, so CONFIRMED is expected if that gain is real. Against rollout3 the expected difference is a few points and 256 pairs
resolve about ±4–5 pp, so that comparison will likely not be shown either way.

## Validity

- All 768 units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained.
- Every MCTS log prints `[ooc-mcts-config]` with `"leafValue":"native"`, `"leafCombats":3`, `"prior":"policy"`, the
  production `combat_model=selfplay/models/combat_transition_deepsets_pathb_r2.native` and the arm's `"simulations"`,
  `"wideningK"` and `"wideningAlpha"`; `off` logs show no OOC MCTS configuration.

## Decision

No default change from this run alone. CONFIRMED would make rollout3 at 4096 simulations with broad widening the
candidate for a default-change proposal (its own decision, with Philipp). Philipp decides what comes next.
