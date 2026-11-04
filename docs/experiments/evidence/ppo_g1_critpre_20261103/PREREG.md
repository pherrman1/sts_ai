# G1: CRIT_PRE's PPO net vs heart1, policy alone (pre-registration, 2026-11-03)

Philipp, 2026-11-03 20:16 CET: "Ja Spiel gegen Heart1 auf 8 workern." Plan: [a20-ppo-plan.md](../../../knowledge-base/research/a20-ppo-plan.md)
(row G1). Source: reward screen 2 (§751), where CRIT_PRE was PROMISING (+0.74 pp [+0.18, +1.32] vs the control, in-sample
at temperature 1, K15 combat). Its last-third rate (8.77%) vs heart1's warm-up rate (8.91%) left open whether it
improves on heart1 or only declines less than the controls.

**Question.** Does CRIT_PRE's final net (net-0060) play A20 better than its start net heart1, policy alone, on fresh
paired seeds?

**Arms** (paired per seed, same seed, order rotated by seed):
- **GH:** heart1 as the PPO actors loaded it: BASE's `net-0000.bin` sha256 `4288d095…eab6` (heart1.bin `1e92f2a6`
  extended with zero-init inputs by `ppo_cloud.py init`; policy identical to heart1).
- **GC:** CRIT_PRE's `net-0060.bin` sha256 `1575c27e…c786` (recorded in CRIT_PRE's `loop.json` as the last update's
  `next_sha256`; saved on the PC before the store was cleaned).

Both nets came to the cloud via the single-commit ref `ppo-xfer/g1-nets` (6d5a2ade) and sit in
`/mnt/project-files/ppo-g1-critpre/`; `campaign.manifest` hash-checks them.

**Runner** (`run_unit.sh`): `bestbench 1000 1 20 SEED` through `tools/seed_guard.sh`.
- **Engine:** current main (`520d4e4b`, binary `ca8db597`, linux-gcc-release-x86-64-v3), including the default-on
  rule fixes #970/#976. The screen's actors played on `71cfd280` (defaa930); G1 measures real play on today's engine,
  and both arms share it.
- **Out of combat:** `STS_OOC_HEART1_PPO=1`, so the net makes every out-of-combat decision, keys included, as in
  training. `STS_OOC_HEART1_TEMPERATURE=0` (argmax, the eval policy). `STS_OOC_MCTS=0`.
- **Combat:** G0's base B: flat Silver 1,000, learned stop off, Act 4 strong off, g7f_E root and tree prior, boss
  prior playouts. This is the plan's G1 combat, not the K15 self-play combat.
- **Flags:** every flag is in `run_unit.sh`. Each game checks, from its log, the binary and the net shas, the loaded
  net, the seed/ascension/sims line, flat budget, the root prior and the `[heart1_ppo]` game line.

**Seeds.** 111520000-111522047 (2,048, new: no use on main, in the ledger or in any PREREG; clear of the arch screen's
111440000-111460001). Smokes 111529990-111529991, local, not analysed. Both smokes ran rc 0 for both arms, first on `71cfd280` and then on
`ca8db597`, with 0 fallbacks and 7-24 s per game. The four games end on the same floors on both binaries.

**Primary analysis** (`analyze.py`, frozen here):
- **Failed games:** a game counts if it finished rc 0, with all its log checks passing. A combat stall (bestbench's
  CombatAbort, `[bestbench-combat-abort] seed=N`) ends the game as a loss with rc 0 before the `[heart1_ppo]` line;
  `run_unit.sh` accepts the abort line in its place, and the game counts as a loss (as the screens' stall = loss).
  Aborted games are listed in `result.json` and do not count toward the drop cap. A game with rc ≠ 0 or a missing
  game is rerun once by the lead, locally, with the same unit. A seed that still lacks a valid game in either arm is
  dropped from both arms and listed in `result.json`; dropped seeds are never imputed. More than 1% dropped
  (> 20 seeds) = **INCOMPLETE**, no verdict.
- The gate gets the analysed seeds without gaps (key = rank in ascending seed order), so a dropped seed cannot hold
  it at PARTIAL. `analyze.py --self-test` covers two dropped seeds in the middle. A failing gate subprocess raises.
- d = Heart kill GC − GH per seed.
- **Standard sequential gate:** `tools/sprt_gate.py`, variant gainer (d0 = 0, d1 = +2 pp, α = β = 0.05), look 64,
  cap 2,048, consumed in ascending seed order.
- **Verdicts:**
  - **GO** if the gate gives PASS.
  - **NOT_SHOWN** if the gate gives NOT_SHOWN, i.e. the data favour no gain of 2 pp.
  - At **CAP**, the fixed-sample reading over all 2,048 seeds decides, with a 95% seed bootstrap (10,000 resamples):
    GO if the CI lower bound > 0, STOP if D ≤ 0, INCONCLUSIVE otherwise.
- **Power (Inference):** the screen's effect (~0.7 pp) is well below the gate's d1 = 2 pp. On 2,048 pairs the CI
  half-width is ~±1.5 pp (G0: ±1.75), so a true +0.7 pp is most likely NOT_SHOWN or INCONCLUSIVE. This G1 tests
  whether CRIT_PRE's net is a clear gain (≥ ~1.5-2 pp) over heart1, not whether it is +0.7 pp.

**Secondary** (descriptive, paired, same bootstrap):
- Act-3 clears (final floor ≥ 52).
- Mean floor.
- CPU seconds per game.

**Decision.**
- **GO:** CRIT_PRE's critic setup becomes the S1 pilot's start. It still needs no default change, since PPO nets are
  not in production.
- **Any other verdict:** CRIT_PRE stays a screen-level result. Its net is not used, and the next PPO step is decided
  with Philipp: longer runs, more games per update, or the architecture screen.

**Cost.** 4,096 games × ~15-25 s ≈ 20-30 core-h. 8 workers × 4 lanes (`campaign.manifest`), ~1 h.
