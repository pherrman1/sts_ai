# Pre-registration: OOC MCTS without leaf rollout combats at 16384 simulations vs rollout3 at 4096 (ledger §475)

Written and committed before any cohort seed ran. Follow-up to §472 in the same project thread. Philipp,
2026-10-14 17:12Z: "hm, but what if we would use our extra time with more mcts simulations?"; on the proposal
"no rollout at 16,384 simulations against rollout 3 at 4096 on 128 new seeds, same setup as §472", 17:13Z: "yes do
it". Pairs 128 ([NPAIRS](NPAIRS)); workers [NWORKERS](NWORKERS).

## Question

In §472 dropping the leaf combats (`LEAF_COMBATS=0`) lost runs at 4096 simulations (92 vs 108 of 128, −12.5 pp
[−21.9, −3.1], WORSE) at 29% of rollout3's MCTS CPU. Does `LEAF_COMBATS=0` with four times the simulation cap
(16384, roughly matched MCTS CPU) win as many runs as rollout3 at 4096?

Prior evidence that bears on it (not part of the test): more simulations at rollout3 were not shown to help (§427
4096 vs 2048 +3.1 pp, §451 8192 vs 4096 −0.8 pp, both NOT_SHOWN).

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting |
|---|---|
| `rollout3` | the §472 `rollout3` arm unchanged (§433 `combo` with the ADR-0028 to ADR-0032 defaults pinned: 4096 simulations, `LEAF_COMBATS=3`, greedy rollout shop, tree rules, merging, public X2-B win model, 8 public futures, deck-size fix) |
| `r0s16k` | the §472 `rollout0` arm (`LEAF_COMBATS=0`) with `STS_OOC_MCTS_SIMS=16384` |

The arms' environments differ in exactly two lines (`STS_OOC_MCTS_SIMS` and `STS_OOC_MCTS_LEAF_COMBATS`).
Early stop stays on in both (as in §433 and §472). Ascension 0. Both arms write the observation-only decision log.

## Provenance

- Code commit = [CODE_COMMIT](CODE_COMMIT) = `main` `e8410510` (after #542). Its build inputs differ from §472's
  code `aedbd473` by #537 (A20 CTM stack default, ascension 20 only), #529 (opt-in leaf stability probe), #541
  (optional Silver prior MLP tables) and #540 with ADR-0034 (multi-select canonicalization and skipping optional
  Recall on by default), which can change A0 play. So §472 runs are not byte-comparable to this run; the control is
  rerun here on fresh seeds and no §472 data is reused. The arm environments are self-contained (built from the §464
  arm file); the `rollout3` environment is line-for-line the §472 one, and neither arm pins the ADR-0034 switches.
- Each worker builds `one_combat` and refuses to run unless its sha256 equals [binary.sha256](binary.sha256). The run
  commit may differ from the code commit only in docs and tools.
- **Seeds 103000000 .. 103000127**, fresh (assigned by the coordinator), both arms on every seed; seed i goes to
  worker (i mod NWORKERS) + 1; one-seed units, 4 at a time. Smoke seeds 74071100–149 (this thread); reviewer seeds
  74071150–199.
- Per-unit timeout 4 h. Silver stalls caught by `bestbench` (`[bestbench-seed-failure]`) drop that seed. A unit whose
  log stops growing for 60 min is a stall: the worker takes a backtrace into `stall-ARM-SEED.txt` and kills that
  `one_combat`; the seed drops out of the pairs. No seed is rerun or replaced. A container restart reruns an
  interrupted unit whole (deterministic).
- Units write to the worker's local disk (`$HOME/x475-wWW/out/`); at the end the worker uploads
  `/mnt/project-files/ooc-rollout0-sims-475/wWW.tar` and then `wWW.DONE.txt` (with the tar's sha256). The analysis
  thread verifies every tar's sha from its own container before analysis.

## Analysis ([tools/analyze_ooc_rollout0_sims_475.py](../../../../tools/analyze_ooc_rollout0_sims_475.py))

Pairs: cohort seeds with a result row in both arms. **Primary:** Δwin = win(r0s16k) − win(rollout3), paired seed
bootstrap 95% CI (10,000 resamples, seed 475).

- **BETTER** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary:** **NONINFERIOR_AT_10PP** if the CI lower bound > −10 pp. **Descriptive:** exact McNemar p, Δfloor
(CI), Δ end HP, boss deaths, mean floor, seconds and MCTS CPU per run and their r0s16k/rollout3 ratios (the CPU match
is checked here, not assumed), owned and fallback share, support aborts, simulations per run, per-run and per-search
tree depth, pick agreement with the top-prior and top-Q candidate.

**Reading.** 128 pairs resolve about ±7 pp. NOT_SHOWN does not mean equal. A comparison with §472's `rollout0` at
4096 would need the same seeds and is not part of this run.

## Validity

- All units rc=0 apart from listed stall or seed failures; any other nonzero rc, crash or missing seed makes the
  result INVALID until explained.
- Every unit's `.env` holds the §472 pins; `r0s16k` units and only they hold `STS_OOC_MCTS_SIMS=16384` and
  `STS_OOC_MCTS_LEAF_COMBATS=0`; `rollout3` units hold `4096` and `3`. Every log prints `[ooc-mcts-config]` with the
  arm's `"simulations"` and `"leafCombats"`.

## Decision

No default change from this run alone. **BETTER**, or **NOT_SHOWN** with **NONINFERIOR_AT_10PP**, makes no-rollout
search at matched CPU a candidate for the OOC MCTS research configuration (its own decision, with Philipp).
**WORSE** keeps rollout3. Philipp decides what comes next.
