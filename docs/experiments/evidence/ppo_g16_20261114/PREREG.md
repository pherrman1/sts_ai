# PG16H24: PPO of the out-of-combat net on the Gumbel G16 combat stack with the Heart at 24k (pre-registration, 2026-11-14)

Philipp, 2026-11-14 00:02 CET: "started ppo auf dem gumbel 16k mit Max backup 4 stack mit 16k s und s und 40k heart.
Das sollte etwa 40% winrate haben. Go on GPU mit 40 worker sobald g12 fertig ist" (40 cloud workers, learner on the
PC's RTX 3060 Ti). 00:16 CET, after the G12H24 result (§799, `../gumbel_g12_heart24_20261113`: on the 393 seeds where both arms reach
Act 4, Heart conversion 84.2 vs 84.5%, −0.3 pp [−4.1, +3.6]; no conversion loss visible, but this is not an isolated
Heart contrast: outcome-selected seeds, different arrival states, S&S at 12k vs 16k; a loss of a few pp is not
excluded): "Let's go g16 mit heart auf 24k. S und s auch auf 16k".

**Question.** Does PPO of the whole out-of-combat policy (one net, no OOC MCTS), trained on games whose fights are
played by §775's Gumbel teacher G16 + mb4 (Heart at 24k), raise the A20 Heart kill rate of that stack above net-0420's 41.21% (§775)?

## Baseline and evidence
- §775: net-0420 (LONG_C's final net, sha 8c0bd16c, the PPO baseline since 2026-11-07) as the whole OOC policy at
  temperature 0 with G16 + mb4 in every fight: **41.21%** Heart on 1,024 seeds (111378256-111379279), 512 CPU-s/run,
  max wall 3,036 s. §785 notes the draw may be slightly favourable.
- LONG_B/LONG_C (§756, §760): PPO with combat B (flat Silver 1,000, ~27 CPU-s/run) took heart1 from 17.3% to 24.0%
  in 220 updates (+6.7 pp), then +1.5 pp [−0.7, +3.7] in 200 more. net-0420 was trained under combat B: its OOC play
  is tuned to a much weaker fighter. G16 wins more fights, so taking more fights / elites / harder paths should pay
  more under G16 than under combat B; that is the hypothesis this run tests.
- Competing hypotheses: (H0) net-0420's OOC play is already near what PPO can find with 1{Heart} at this sample size
  (~50k games), and the gain is within ±2 pp; (H1) the stronger combat shifts the OOC optimum and PPO finds part of it.

## Design (one conceptual change against LONG_C: the actors' combat is G16H24 instead of combat B)
- **Start:** `--init net-0420.bin` (8c0bd16c…, `/mnt/project-files/ppo-long-c/nets/net-0420.bin` = PC
  `~/ppo-longb/LONG_C/net-0420.bin`). The shared value head comes with the net; Adam moments start fresh. Value
  warm-up: the first **4** updates are value-only with Monte Carlo targets (`--warmup-lam 1.0`), because net-0420's value
  head was fitted to combat B's ~20% Heart rate.
- **Recipe = LONG_B/LONG_C's:** reward 1{Heart} (`--reward heart`), γ 1, λ 0.97, clip 0.2, 2 epochs, minibatch 192,
  lr 1e-5, value coef 0.5, entropy 0.002, no KL anchor, bf16 autocast, `--seed 0`, serve `--micro-batch 192`,
  pipeline 1 (iteration i is played by net-(i−1)), 520 games per update in 40 parts of 13 (one part per worker).
- **Actors:** [actors_frozen.env](actors_frozen.env) = §775's G16 arm (`run_unit.sh` COMMON + `STS_SILVER_GUMBEL_ROOT=16
  STS_SILVER_GUMBEL_ROOT_MAX_BACKUP=4`, bestbench SIMS 16000, Act 4 strong default on: S&S 16k with prior playouts)
  with the Heart at 24k (`STS_SILVER_ACT4_HEART_BUDGET=24000`, the research option of PR #1044, as G12H24), sampling at temperature 1 (PPO mode), plus `STS_COMBAT_TURN_CAP=100` as LONG_C's iterations 272-419
  (one 500-turn stalemate under 16k-sim search would hold a whole update for hours).
- **Binary:** one_combat `97aec5b5` (code ba705ab4 = main c0a8fed2 + the research option STS_SILVER_ACT4_HEART_BUDGET,
  PR #1044, not yet merged; in the bin-cache; the G12H24 campaign's 32 G16 sentinel games reproduce §775's games on it
  and its G12H24 arm ran the Heart at 24k on it). Build inputs of the run commit = ba705ab4 (worker setup checks). The run
  commit sits on this branch, which is based on #1044's run commit 495d4d66; a later change to #1044 does not change
  the frozen candidate.
- **Iterations:** cap 100 (52,000 games). Wall-time limit: the run is stopped by the author at the first update
  boundary after **48 h** from launch unless Philipp extends it; the last published net is the run's final net
  (net-N). Kept states: `serve --keep-state 20 40 60 80`.
- **Seeds:** 112100000-112151999 (100 × 520; iteration i plays 112100000 + 520·i …; new: no use on main, in the
  ledger or a PREREG, checked 2026-11-14). Smoke seeds 112199990-112199999 (999 = one direct G16 check game at 16k, 146 s, Gumbel roots 363). Every game goes through
  `tools/seed_guard.sh` (ppo_loop.start_actors).
- **Stalls/aborts:** ppo_cloud's rules (max 1 per part of 13; a stall or combat abort counts as a loss).
- **Store:** `ppo-xfer/pg16h24` (new), smoke `ppo-xfer/pg16-smoke`. Learner on the PC (`~/ppo-pg16`, checkout at the run
  commit, system python3 with torch 2.5.1+cu121). No other GPU job during the run.

## Expected cost
- Actors: 520 × ~470 CPU-s (§775 G16 512 s, less the Heart's 40k → 24k) ≈ 68 core-h per update; 160 lanes (40 workers × 4) → ~28 min if perfectly packed. Each
  part (13 games on 4 threads) ends with its slowest game (G16 max 3,036 s in §775), so ~35-50 min per update,
  ~60-80 updates in 48 h. Learner ~90 s per update (LONG_C 87 s).
- A container reset replays the lost part from its first game (the actor resumes per part); expected delay up to one
  part per reset.

## Smoke (before the review; no gameplay gate)
Store `ppo-xfer/pg16-smoke`, arm SMOKE ([smoke/arms.txt](smoke/arms.txt)): the env before the Heart-24k line was added
(frozen 2026-11-14 00:11 CET, otherwise identical) at sims 1,000, 3 iterations ×
3 games, 1 part, warm-up 1, seeds 112199990-112199998; one cloud actor, learner `serve` on the PC GPU. Pass = 3
iterations trained (it 0 value-only, 1-2 PPO), net-0003 published, every game line carries the Gumbel banner count
(`[silver] whole-run Gumbel roots=N`, N > 0) and the turn cap, the actor recorded one_combat 97aec5b5.

## Monitoring (pause rule, no verdict)
Per update: in-sample Heart rate (temperature 1), act reach, mean floor, stalls, actor and learn time, approx_kl,
explained variance (dashboard). The author pauses the learner and asks Philipp when (a) the Heart rate over the
last 10 updates is more than 5 pp below the mean of the 4 warm-up updates (policy unchanged then; SE ≈ 1.0 pp and
0.7 pp), or (b) approx_kl > 0.05 on 3 consecutive updates, or (c) > 3 stalls in one update.

## Evaluation (primary; needs Philipp's go and worker count when the run ends)
- Arm: the final net-N, PPO mode at **temperature 0**, combat exactly §775's G16 (§775 `run_unit.sh` G16 environment:
  Heart 40k, turn cap unset = 500), binary 97aec5b5, §775's 1,024 seeds 111378256-111379279. The evaluation compares
  nets on §775's stack, so the control can be reused; the training stack differs from it only in the Heart's budget.
- **Control = §775's G16 games of net-0420, reused** after a sentinel: the G12H24 campaign's 32 G16 sentinel games
  (111378256-111378287, binary 97aec5b5) must reproduce §775 (Heart kill, final floor, decisions); else net-0420 is
  replayed in full.
- d = Heart kill net-N − net-0420 per seed. `tools/sprt_gate.py` gainer (d0 0, d1 +2 pp), alpha 0.05, beta 0.05,
  look 64, cap 1,024; at CAP the 95% seed bootstrap decides GO (lo > 0) / STOP (mean ≤ 0) / INCONCLUSIVE.
  Failed-game, abort and drop rules as §775.
- Secondary (descriptive): kept checkpoints at 20/40/60/80 on the first 256 seeds; Act-4 reach, Act-4 conversion,
  Act-1/2/3 deaths; in-sample curves.

**Decision.** GO: net-N becomes the PPO baseline for the G16 stack and the candidate start net of the AZ loop; a
production change needs its own A/B and Philipp's call. Otherwise ledger entry, next step with Philipp. No default
changes in any case.
