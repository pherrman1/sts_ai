# Long PPO run on combat B with a pre-trained critic (pre-registration, 2026-11-04)

Philipp, 2026-11-04 10:47 CET: "glaube mehr läufe sind wahrscheinlich gut. macht mit crit_pre. und vor allem sollten
wir ein besseres combat model nutzen ... das beste model ..., sodass die zeit zum trainieren gleich lang ist [wie] die
spiele für die nächste iteration", "40 worker", 10:50 CET "ja guter vorschlag, mach das". Sources: §748 (recipe),
§751 (CRIT_PRE PROMISING), §752 (G1 INCONCLUSIVE +0.78 pp), §754 (architecture stays BASE).

**Question.** Does a longer PPO run from heart1, on stronger self-play combat and with a critic pre-trained on that
combat (CRIT_PRE's recipe), produce a net that plays A20 better than heart1?

## Design
- **Start net:** heart1 (`1e92f2a6`), extended with zero-init inputs by `ppo_cloud.py init`. The start net-0000 is
  BASE's net-0000 of screen 2 (`4288d095`), checked at freeze.
- **Combat B** (`actors_frozen.env`) is G0/G1's base: flat Silver 1,000, learned stop off, Act 4 strong off, g7f_E root
  and tree prior, boss prior playouts.
  - **Why B:** it is the strongest setting whose actor time matches the learner. 520 games × ~20 s / 160 lanes ≈ 65-100 s
    per iteration vs ~70-90 s per update.
  - **Why not production combat** (learned stop + Act 4 strong, 25.4% vs 16.8% at §739): it costs ~12× per game. Act 4
    strong only exists under the learned stop, and one 40k Heart fight costs ~4 min (§682).
- **Engine:** binary `ca8db597` (main 520d4e4b), the same as G1, so that G1's heart1 games serve as the evaluation
  control (below). The run commit keeps 520d4e4b's build inputs. `STS_OOC_HEART1_PPO=1`, temperature 1, salt =
  iteration, A20, `--pipeline 1`.
- **One arm, LONG_B** (`arms.txt`): 220 iterations × 520 games in 40 parts of 13 (one part per worker, W = 1..40).
  - **Iterations 0-19 are value-only.** This is CRIT_PRE's pre-training done online: only the value head and its norm
    move, with Monte Carlo targets (`--warmup-lam 1.0`, new learner option, default off). The policy stays heart1's,
    and 10,400 B games calibrate the critic.
  - **Iterations 20-219 are PPO**, with the base recipe of §748 (`ppo_train.py` defaults: λ 0.97, clip 0.2, 2 epochs,
    minibatch 192, lr 1e-5, entropy 0.002), learner seed 0. `--micro-batch 192` runs on the PC.
  - **Why online:** the screen's CRIT_PRE was 60 value-only updates over K15 games. With B the Heart rate is higher
    (16.8% vs 10.9% at G0), so the K15 critic would be miscalibrated again.
- **Learner:** Philipp's PC (RTX 3060 Ti), `ppo_cloud.py serve --micro-batch 192 STORE ~/ppo-longb LONG_B
  --keep-state 70 120 170`.
  - Every net stays local.
  - The checkpoints are net-0070, net-0120, net-0170 and net-0220, i.e. 50/100/150/200 PPO updates.
- **Seeds:** 111540000-111654399 (220 × 520, new: no use on main, in the ledger or in any PREREG). Smoke
  111539900-111539915 (local, 2 iterations × 8 games on a dir store, not analysed): actors and learner ran, warm-up
  return = Monte Carlo, ~105 decisions per game.
- **Stalls:** a stall counts as a loss, as in the screens. On `ca8db597` a stalled combat is a CombatAbort (d3dc5eac):
  bestbench exits 0 and the game's trajectory line is missing. The actor adds a loss game line (no decisions) for each
  missing seed if the missing seeds are exactly the `[bestbench-combat-abort]` seeds (`aborted_game_lines`, added
  for this run after K's pre-launch review); any other missing game stops the actor. At most `max_stalls` = max(1,
  1% of the part) stalls per part, i.e. 1 of 13.

## Amendment 2026-11-05: engine speedup during the pause
Philipp paused the run at update ~157 (11:20 CET, GPU needed) and asked to streamline the process in the meantime.
At 12:05 CET he approved the engine change: "implementiere die erste option. idc. wenn wir die engine in der pause
ändern, mach das einfach."
- **The hangs:** the 17-35 min stalls were single long games. The replay of seed 111595870 (net-0106, salt 107) is an
  Act-3 stalemate that runs to the turn cap. ~97% of its 1,467 s was spent in
  `SilverSearcher::findNodeUpToEquivalentCopy`, which copied and rehashed the state for every pair of equivalent cards.
- **The change, bc33e470 (K PASS):** a pair is skipped when its swapped state's hash (`SwapHasher`, incremental) is in no
  transposition-table slot. Every other pair takes the old path, so the search result is unchanged by construction.
- **Run commit after the pause:** `code_commit` bc33e470, binary `78849fcf` (linux-gcc-release-x86-64-v3, the preset
  of `ca8db597`).
- **Parity:** the replay is identical (trajectory and result, except wall time) and takes 50 s. The 32 G1 sentinel seeds
  (GH, heart1 net-0000, evaluation flags) are 32/32 equal to `sentinel_expected.csv`.
- **Iterations before and after the pause** play the same games. Only the wall time differs.
- **The store keeps the config frozen.** `ppo_cloud.py rebin` writes `LONG_B/rebin` once (old `ca8db597`, new
  `78849fcf`). The actor accepts either binary, and every part's meta records the `one_combat_sha256` it played.
- **The evaluation** stays pinned to `ca8db597` unless its freeze says otherwise.

## Evaluation (primary)
G1's runner and analysis (`../ppo_g1_critpre_20261103/`), frozen there:
- PPO mode at temperature 0, combat B, binary ca8db597.
- G1's seeds 111520000-111522047.
- d = Heart kill GC − GH, gate `sprt_gate.py` gainer (d1 = +2 pp), look 64, cap 2,048, then the fixed-sample fallback.

The arms:
- **GH (control) is reused from G1** (§752, 17.33%): same seeds, binary, flags and net. A sentinel of 32 GH seeds
  (111520000-111520031) is rerun first. It must reproduce G1's GH games exactly (Heart kill, final floor and the `[heart1_ppo]` line's
  `decisions=`), else
  GH is replayed in full.
- **GC = net-0220**, played fresh.

The primary verdict is net-0220 vs heart1. GO / NOT_SHOWN / STOP / INCONCLUSIVE are as in G1's PREREG, and the
failed-game, abort and drop rules are G1's.

The evaluation campaign is a copy of G1's directory with GC's net and sha replaced. It is committed and delta-reviewed
before it plays.

**Secondary:**
- net-0070, net-0120 and net-0170 on the same seeds vs GH, descriptive: D with CI, no gate.
- In-sample per-block Heart rate, approx-KL, entropy, value loss and explained variance (`loop.json`).
- Warm-up: mean value vs mean return per value-only iteration.

**Decision.**
- **GO:** net-0220 becomes the S1 start and the next PPO baseline. Its use as a production prior needs a separate
  production A/B and Philipp's call.
- **Any other verdict:** the result goes to the ledger, and the next step is decided with Philipp.
- No default change in either case.

## Cost
- **Actors:** 114,400 games × ~20-30 s ≈ 640-1,000 core-h on 40 workers.
- **Learner:** 220 updates × ~70-100 s ≈ 5-6 h on the PC. A part of 13 games on 4 lanes takes ~100-130 s (K's
  estimate), so the actors set the pace: ~7-8 h wall.
- **Evaluation:** 4 × 2,048 + 32 games × ~25 s ≈ 57 core-h.
