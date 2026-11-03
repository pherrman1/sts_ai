# PPO reward screen, screen 2 (pre-registration, 2026-11-03)

Philipp, 2026-11-02: reward design is a parameter to rethink and test (via the coordinator, 11:57 CET). 2026-11-03
09:29 CET: "mach den reward screen, ich glaube wir haben da schon iwie research gemacht, i.e. es gibt vorschläge
dazu". Proposals: [a20-ppo-plan.md](../../../knowledge-base/research/a20-ppo-plan.md) (V3: 1{Heart} + PBRS; "Reward
is a test axis too"); screen 1 (§748): no recipe change helped, the policy moves (approx-KL ~0.011 per update)
without a measurable gain.

**Question.** Does a different learning signal (shaped reward, potential, or a pre-trained critic) make PPO from
heart1 raise the A20 Heart-kill rate where screen 1's base recipe did not?

**Background (Inference, cited in the plan).** With γ = 1 and Φ(terminal) = 0, potential-based shaping leaves the
objective unchanged: a game's shaped return is 1{Heart} − Φ(s_0) for every policy. Shaping equals initialising the
value function with Φ (Wiewiora 2003), so for PPO it acts through the critic: the learned critic only has to fit
V − Φ. It can help only while the critic is poor. A pre-trained critic tests the same mechanism directly. An act/key
bonus changes the objective; it is judged by Heart kills like every arm.

## Design

**Fixed (as screen 1, §744/§748):**
- Start net heart1 (`1e92f2a6`), extended with zero-init inputs by `ppo_cloud.py init`.
- Combat K15: `actors_frozen.env` is screen 1's file, byte for byte.
- Actors' one_combat `71cfd280`. Build inputs are unchanged since `defaa93`, so the binary comes from the bin cache.
- `STS_OOC_HEART1_PPO=1`, temperature 1, salt = iteration, A20, `--pipeline 1`.
- Base recipe: `ppo_train.py` defaults, i.e. reward `heart`, γ 1, λ 0.97, clip 0.2, 2 epochs, minibatch 192, lr
  1e-5, entropy 0.002, KL 0, 3 value-only warm-up iterations, 512 games per iteration.

**Learner:** current main including the learner-hardening PR (games sorted by seed, fp32 heads). Every arm, the
controls included, runs on that code from iteration 0, on Philipp's PC (RTX 3060 Ti, `--micro-batch 192`,
least-progress-first order).

**Length:** 60 iterations per arm (30,720 games), twice screen 1's length, because no arm rose within 30.

**Arms** (`arms.txt`; one change each from BASE):

| Arm | Change |
|---|---|
| BASE | base recipe, learner seed 0 |
| BASE_S1 | learner seed 1. Together with BASE it forms the control, and BASE_S1 − BASE is the run-to-run noise |
| PBRS_FLOOR | `--reward heart_phi` with Φ = `phi_floor.json`: P(Heart kill \| the game reached floor f), from screen 1's 291,840 games (all arms; 0.078 at floor 0, 0.086 at 16, 0.140 at 33, 0.257 at 50, 0.515 at 56). Computed from each decision's floor (`ppo_phi.py`) |
| PBRS_STATE | `--reward heart_phi` with Φ = `phi_state.json`: L2 logistic regression of the Heart kill on public run state (logit of the floor table, HP fraction, max HP, gold, keys, deck size, relics, potions, act; `ppo_phi.FEATURES`). Fit by `ppo_phi_fit.py logistic` on every 4th game (by seed) of screen 1's BASE trajectories and scored on BASE_S1's. Admitted only if its hold-out log-loss is below the floor table's; otherwise the arm is dropped before launch and RESULT says so. **Fit (PC, 2026-11-03):** 395,058 fit and 396,674 hold-out decisions, hold-out log-loss 0.3528 (state) vs 0.3664 (floor table) vs 0.3855 (constant), so the arm is **admitted**. `phi_state.json` sha256 `8e345898…c262` |
| CRIT_PRE | start net = heart1 with its critic pre-trained by `ppo_critic_pretrain.py`: 1 pass of value-only updates (base hparams except λ = 1, i.e. Monte Carlo targets that do not bootstrap from heart1's miscalibrated critic; reward `heart`) over screen 1's BASE and BASE_S1 trajectories (60 recorded iterations, 30,720 games). Only the value head and its norm move, so the policy is heart1's bit for bit (checked at freeze) |
| ACT_BONUS | `--reward heart_act`: 1{Heart} + 0.1 per act cleared (final floor ≥ 17 / 34 / 51) + 0.05 per key, at game end |

The original's reward (floor/190 + keys + Heart) was screen 1's REW_ORIG (NOT_SHOWN, +0.02 pp) and is not repeated.

**Seeds:** all arms play the same block, 111470000-111500719 (new, clear of #974's 111440000-111460001). Iteration i
plays 111470000 + 512·i ..., in 4 parts of 128 games. That gives 24 actor workers (W = 1..24 in `arms.txt` order).

## Analysis (`analyze.py`, frozen here)

- **Primary metric.** Heart-kill rate over iterations 40-59 (seeds 111490480-111500719, 10,240 games, identical in
  every arm), paired by seed against the control C = (BASE + BASE_S1)/2. D = arm − C, with a 95% seed bootstrap
  (10,000 resamples).
- **Verdicts.**
  - **PROMISING** if the CI lower bound > 0 and D > (√3/2)·|BASE_S1 − BASE| ≈ 0.87·|BASE_S1 − BASE|. With a
    run-to-run sd σ per run, |BASE_S1 − BASE| estimates √2σ and D = arm − C has run sd √(1 + 1/2)σ, so the bar
    is one run-noise sd of D, as screen 1's bar was one sd of its D (review K).
  - **WORSE** if the CI upper bound < 0.
  - **NOT_SHOWN** otherwise.
- **Futility look** (one, at iteration 30, when every arm has trained iteration 29). Same statistic over iterations
  20-29 (`analyze.py --futility`). An arm with a CI upper bound < 0 is stopped and reported **FUTILE**; the learner
  restarts without it and its workers are released. There is no early stop for success.
- **Stalls (as screen 1, #965/#966).** A combat over 1,000 decisions counts as a loss, capped at ⌊1%⌋ of a part (1
  per 128-game part); above the cap the arm is INCOMPLETE. RESULT lists stalls per arm and a sensitivity D without
  any stalled seed of the window; a sensitivity D that changes a verdict is named. If BASE or BASE_S1 is
  INCOMPLETE, there are no verdicts. `analyze.py` reports the sensitivity D with its own CI and verdict, and arms
  stopped at the futility look as FUTILE (from the look's `futility.json`).
- **Smoke.** No actor smoke and no smoke seeds: the actors, binary and env are screen 1's. The new code is
  learner-only; before launch, one learner update per new reward runs on recorded screen-1 trajectories on the PC
  (no new games).
- **Secondary.** Per-iteration Heart rate, approx-KL, entropy, value loss and explained variance of the critic
  (`loop.json`). For PBRS arms, the mean |V − (return − Φ)| per iteration. For CRIT_PRE, the pre-training log.

**Decision.** A PROMISING arm becomes the next pilot's reward or critic setup, confirmed by G1 (2,048 fresh paired
seeds, policy alone, Silver 1,000) before anything uses its net. No default changes.

**Cost.**
- Actors: 6 × 30,720 = 184,320 games at ~4 core-s ≈ 210 core-h, 24 cloud workers.
- Learner: 360 updates at ~70 s ≈ 7 h on the PC.
- Pre-training on the PC before launch: ~1 h CRIT_PRE plus the Φ fit.
- Total wall time ~9-10 h.

**Launch steps (author).**
1. Fit `phi_state.json` and `critpre.bin` on the PC from `~/ppo-screen1` and commit them with their logs. Commit
   `critpre.bin`'s sha256 and the check that its policy tensors equal heart1's.
2. Re-review (delta) of the fitted files.
3. `make_arms.sh` writes the six arms into `git:https://github.com/pherrman1/sts_ai#ppo-xfer/screen2`.
4. Start the PC serve and the 24 workers (`ppo_cloud_worker.sh`, as screen 1).
5. At the end, `ppo_cloud.py cleanup` on the PC.
