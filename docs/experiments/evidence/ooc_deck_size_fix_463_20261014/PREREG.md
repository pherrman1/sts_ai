# Pre-registration: corrected vs legacy shop deck-size accounting in §433 `combo` (ledger §463)

Written and committed before any cohort seed ran. Philipp's request, 2026-10-14 06:33Z, in the project thread "Can we
investigate how the shop planner works in the ooc MCTS?": he picked "Paired check" on the card "Test the deck-size
default on/off before keeping it, or revert it now?" (option text: fresh 128 seeds, combo with the deck-size fix on vs
off on the same seeds, 8 workers). Pairs 128, 8 workers ([NPAIRS](NPAIRS)).

## Question

ADR-0030 (#523) made `STS_OOC_SHOP_DECK_SIZE_FIX` on by default: the native shop planner counts only purchased cards
in deck size and subtracts one for a planned removal. Its playing strength was never measured. After §459 the
independent reviewer noticed (post hoc) that the §459 `planner` arm won 101/128 while §449's `x2bpub` arm won 114/128
on other seeds (82M) in what is otherwise the same `combo` environment; Fisher p = 0.04, pooled with §451's `combo`
arm p = 0.002. Different seeds and binaries, so this is a suspicion, not evidence. Does the corrected accounting
change how §433 `combo` plays, on the same seeds?

## Arms ([arm_env.sh](arm_env.sh))

| arm | setting |
|---|---|
| `fixon` | the §459 `planner` arm exactly: §433 `combo`, `STS_OOC_PUBLIC_FUTURES=8`, `STS_WIN_NET=models/candidates/v_win_x2b_public_trees.txt`, `STS_OOC_MCTS_ROLLOUT_SHOP=planner`, `STS_OOC_SHOP_DECK_SIZE_FIX=1` |
| `fixoff` | the same with `STS_OOC_SHOP_DECK_SIZE_FIX=0` (legacy accounting) |

`arm_env.sh` builds both from the §459 `planner` environment and changes exactly one line. Each unit writes its `STS_*`
environment to `ARM-SEED.env`.

What the flag changes in code: the deck-size feature edits in `nativeShopPlan` (`ooc_native_fallback.cpp`), which run
wherever the bundle planner runs: OOC MCTS leaf rollouts and the live fallback chain after a root abort. Live shop
roots searched by the tree do not call it.

## Provenance

- Code commit = [CODE_COMMIT](CODE_COMMIT) (main after #528). Each worker builds `one_combat` and refuses to run
  unless its sha256 equals [binary.sha256](binary.sha256). The run commit may differ from it only in docs and tools.
  **Note:** this binary carries the #522 Silver loop guard and the #526 opt-in leaf capture that the §459 binary
  (`440cf556`) did not; both arms share it.
- **Seeds 92000000 .. 92000000+NPAIRS−1**, fresh, both arms on every seed. Worker W runs seeds
  92000000+16(W−1) .. +15 in both arms (32 one-seed units, 4 at a time). Smoke seeds 74063000–74063001 (planning
  container, [SMOKE.md](SMOKE.md)).
- Per-unit timeout 8 h. Silver stalls are caught per seed by `bestbench` (`[bestbench-seed-failure]`); such seeds
  drop out of the pairs. No seed is rerun or replaced.
- Units write to the worker's local disk (`$HOME/x463-wNN/out/`). When all 32 are done the worker uploads
  `/mnt/project-files/ooc-deck-size-463/wNN.tar` and then `wNN.DONE.txt` (with the tar's sha256).

## Analysis ([tools/analyze_ooc_deck_size_463.py](../../../../tools/analyze_ooc_deck_size_463.py))

Pairs: cohort seeds with a result row in both arms. **Primary:** Δwin = win(fixon) − win(fixoff), paired seed
bootstrap 95% CI (10,000 resamples, seed 463).

- **BETTER** if the CI lower bound > 0;
- **WORSE** if the CI upper bound < 0;
- otherwise **NOT_SHOWN**.

**Secondary (descriptive):** exact McNemar p, Δfloor (CI), Δ end HP, boss deaths, mean floor, seconds per run, MCTS
CPU per run, owned and fallback share, support aborts and simulations per run.

**Reading.** 128 pairs resolve about ±7 pp; the gap that motivated this run was about 10 pp. NOT_SHOWN does not mean
equal.

## Validity

- All units rc=0 apart from listed stall failures; any other nonzero rc, crash or missing seed makes the result
  INVALID until explained.
- Every unit's `.env` holds `STS_OOC_PUBLIC_FUTURES=8`, the pinned `STS_WIN_NET`, `STS_OOC_MCTS_ROLLOUT_SHOP=planner`
  and its arm's `STS_OOC_SHOP_DECK_SIZE_FIX` (1 or 0); every log prints `[ooc-mcts-config]` with
  `"simulations":4096` and `"leafCombats":3`; `fixon` logs print `[native OOC shop deck-size correction ON]` and
  `fixoff` logs do not.

## Decision

- **WORSE:** recommend reverting the ADR-0030 default (a new ADR superseding it); Philipp decides.
- **BETTER** or **NOT_SHOWN:** the default stays; the §449/§459 gap is then not attributed to the flag by this run.
