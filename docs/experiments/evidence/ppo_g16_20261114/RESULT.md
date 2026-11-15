# PG16H24 result: net-0420 PPO on the G16 + mb4 stack, 46 updates, evaluated against net-0420

Pre-registration: [PREREG.md](PREREG.md); evaluation addendum [eval/EVAL.md](eval/EVAL.md) (written before any eval
game). Data: `eval/results/result.json` (analyze.py output), `eval/results/claims.txt`,
`eval/results/train_stats-0046.json` (learner stats of all 46 updates), `eval/results/stuck_games.md`.

## Training run
- PPO from net-0420 (LONG_C recipe, 520 games per update, 4 value-only warm-up updates) with the actors on §775's
  G16 + mb4 combat at S&S 16k and the Heart at 24k (`STS_SILVER_ACT4_HEART_BUDGET=24000`, turn cap 100); 40 cloud
  actors, learner on the PC GPU. 2026-11-14 00:25 CET to 2026-11-15 19:18 CET.
- **Stopped after 46 updates** (Philipp, 2026-11-15 19:18 CET, "lets stop the ppo here"), before the preregistered
  48 h boundary. 23,920 games, seeds 112100000-112123919 (used).
- In-sample Heart rate (training stack, sampled policy): warm-up updates 1-4 **39.66%** (2,080 games), PPO updates
  5-46 **36.41%** (21,840), last 10 updates 36.23%. Policy entropy 0.309 → 0.336. In-sample rates are not the gate
  (different Heart budget, temperature and turn cap from the eval).

### Deviations from the PREREG during training
1. **Manual stalls.** Five games ran for hours and blocked their update (pipeline 1). Each was ended by hand with
   `force_stall_part.py`, which counts the game as a loss and records `manual_stall_seed` in the part's meta:
   - iteration 6, W1, seed 112103120 (>4 h, 6.5 GB RSS, deterministic on replay)
   - iteration 7, W9
   - iteration 31, W37
   - iteration 33, W34, seed 112117590
   - iteration 39, W26, seed 112120607

   From 2026-11-15 10:52 CET a 1 h rule applied with Philipp's OK. Seeds, nets and config for a later replay fix are
   in `eval/results/stuck_games.md`. The exact seeds of the iteration 7 and 31 stalls were not recorded at the time, and the learner deleted those parts after consuming them. A duration histogram of 17,680 games shows a 1 h cut affects 0.06% of games.
2. **Pause** on 2026-11-14 from 12:25 to 12:35 CET. It came from a wrong diagnosis: the value-only warm-up does not
   move the policy. The policy did not change during the pause.
3. **Rebin** from 2026-11-14 at about 21:00 CET. Actors moved at part boundaries from one_combat 97aec5b5 (code ba705ab4)
   to dae7894a (code 950b53fc), the exact #1046 / #1047 combat kernel.
   - `rebin_sentinel.txt` shows identical play at about 0.75× time.
   - 38 of 40 workers switched. W18 and W23 kept 97aec5b5.
   - Both binaries play identically, so the data does not depend on the binary.

## Evaluation (primary)
- P46 = net-0046 (sha256 c42c8725…), PPO mode at temperature 0. Combat is exactly §775's G16 + mb4 (16k, Heart 40k,
  turn cap unset). The run used §775's 1,024 seeds 111378256-111379279, binary dae7894a, RUN 68142dfc, and 32 workers.
- **Sentinel 32/32 identical** to §775's G16 games (whole log except timing) = REUSE_VALID. §775's G16 games of
  net-0420 are the control. Machine and binary speed: new / ref CPU on the sentinel is 0.811.
- Units: 1,056 of 1,056 verified (`verify_campaign.py`): 0 missing, 0 bad, 0 duplicates, all on 68142dfc, 32/32 worker
  DONE files. The analysis found 0 bad games, 0 env mismatches, 0 aborts and 0 dropped. The longest game took 39 min.
  Total compute was about 113 lane-hours, from 19:45 to 21:20 CET.

**Result.** Heart kill G16 (net-0420) **41.21%**, P46 (net-0046) **38.18%**.
- d = **−3.03 pp [−6.15, +0.10]**, one-sided 95% [−5.66, −0.39].
- 119 seeds only P46 kills, 150 only G16.
- **Gainer SPRT NOT_SHOWN** (accept H0 at 896 seeds, LLR −3.56) → **STOP**. The nonregression SPRT is at CAP
  (descriptive). Its one-sided upper bound −0.39 pp < 0 would read as WORSE under #1044's nonregression criterion.
- First 512 seeds: −2.54 [−6.84, +1.95].
- Act-4 reach −1.86 pp [−4.98, +1.27].
- Act-4 conversion: G16 422/504 (83.7%), P46 391/485 (80.6%). On the 360 seeds both reach, 87.2% vs 82.5%,
  −4.7 [−9.2, −0.3].
- CPU per run 386 s vs 512 s (0.754× raw, 0.929× after the sentinel's binary/machine correction). P46's games are
  slightly shorter.
- Secondary: P46 − D (§775's default stack) is +6.54 [+3.32, +9.77] at 1.53× CPU. This is the G16 stack's gain, not
  the net's.

**Interpretation (inference).**
- 46 PPO updates on the G16 stack did not improve net-0420. The point estimate is −3 pp, and the one-sided interval
  excludes a gain.
- Where both nets reach Act 4, P46 converts worse. That points to worse Act-4 arrival states or decks rather than
  combat. This is not an isolated contrast, because the seeds are outcome-selected.
- The in-sample drop after the warm-up (39.7 → 36.4%) matches the eval's direction. PPO moved the policy away from
  net-0420 without finding signal. This fits PR #1049's gradient-noise reading: there was no measurable policy
  gradient at about 1k games per step.

**Decision.** STOP: net-0046 is not adopted. net-0420 remains the out-of-combat net. No default change.
