# PPO training-recipe screen (pre-registration, 2026-11-01)

Philipp, 2026-11-01: "16 worker für prior share lauf, 8 fpr ppo s1 pilot. aber maybe erste der rezept screen" (22:02Z,
via the coordinator), "du kriegst dann actually 40 worker" (22:11Z), "masch einfach alles go, ich approve den ganzen
run" (22:17Z). Plan: [a20-ppo-plan.md](../../../knowledge-base/research/a20-ppo-plan.md), "Training recipe".

**Question.** Which PPO hyperparameters, changed one at a time from a base recipe, give the fastest rise of the A20
Heart-kill rate in short runs of our own engine?

**Fixed before launch, by earlier pre-registered decisions** (not by this screen's data):
- Start net: G0 of `ppo_cost_arms_g0_20261101` (HEART1 → `heart1.bin` `1e92f2a6`; STUDENT_SEL → student_sel
  `cf6bf7fb`), extended with zero-init inputs by `ppo_cloud.py init`.
- Combat: the same campaign's chosen cost arm (B, K1, K4, K5 or K15), applied to `actors_base.env` by `make_arms.sh`.

**Runner.** `tools/heart1/ppo_cloud.py`: cloud actor containers (4 game threads each; 2 per arm, 4 for G_1024) play
the games; one learner process on Philipp's PC (RTX 3060 Ti, bf16) trains every arm, oldest iteration first. They
exchange games and nets through git refs `refs/heads/ppo-xfer/screen1/<ARM>/...` of this repository (actors only
create refs; the PC deletes every consumed ref). `--pipeline 1` (iteration i played by net_{i-1}, PPO ratio against
the recorded log-probs). `STS_OOC_HEART1_PPO=1`: the net makes every out-of-combat decision
(gold automatic), sampled at temperature 1 with salt = iteration. Ascension 20. Binary: current main's `one_combat`
(sha in `screen.manifest`).

**Base recipe** (`ppo_train.py` defaults unless named): reward `heart` (1 for a Heart kill, else 0), γ 1, GAE λ 0.97,
clip 0.2, 2 epochs, minibatch 192, lr 1e-5, value-lr multiplier 1, value coefficient 0.5, entropy 0.002, KL to the
start net 0, grad-norm 1, per-update advantage normalisation; 3 value-only warm-up iterations; 512 games per
iteration, 30 iterations (15,360 games).

**Arms** (`arms.txt`; one change each): BASE; BASE_S1 (learner seed 1: the noise floor of the comparison); REW_ORIG
(the original's reward); LR 3e-6 / 3e-5; entropy 0.01 / 0.0007; KL anchor 0.01 / 0.1 / 0.1 decaying linearly to 0 at
update 15 (`--kl-decay-iters`, new); warm-up 0 / 10 (value-only iterations: the policy is frozen); epochs 1 / 4;
minibatch 512; λ 1.0; clip 0.1; games per iteration at the same total of 15,360 games: 256 × 60 (warm-up 6) and
1,024 × 15 (warm-up 2). 19 arms, 40 actor workers (plan revision #959: decaying KL, frozen-policy warm-up and the fixed
total budget are priority 1; λ only 0.97 / 1.0).

**Seeds.** All arms play the same block 111400000-111415359 (new; no use on main or in the ledger): iteration i of an
arm with G games per iteration plays 111400000 + G i …, split into its parts. Smokes 111419990-111419999.

**Primary metric.** Per arm, the Heart-kill rate of its last third of games (seeds 111410240-111415359, 5,120 games:
iterations 20-29 at 512, 40-59 at 256, 10-14 at 1,024; identical seeds in every arm), paired by seed against BASE: D = arm − BASE with a 95% seed bootstrap
(10,000 resamples). BASE_S1 − BASE measures the seed-to-seed noise of a whole run. An arm is **PROMISING** if its D CI
lower bound > 0 and D > |BASE_S1 − BASE|; **WORSE** if its CI upper bound < 0; otherwise NOT_SHOWN.
Secondary: the per-iteration Heart curve (games are sampled, so in-sample rates include exploration), approx-KL,
clip fraction, entropy, value loss per iteration.

**Decision.** S1's recipe = base with every PROMISING change (one combined run confirms it; changes on the same
parameter: the larger D). A PROMISING arm is a hypothesis for S1, not an adopted default; the final net still passes
G1 (2,048 fresh paired seeds, policy alone, Silver 1,000) before anything else uses it.

**Cost.** Per round of all arms ~20-25 min on the GPU (~60-70 s per 512-game update incl. featurising; epochs 4 and
1,024 games ~2×); actors ~20 min per 512 games on 2 containers at Silver 1,000. ~30 rounds ≈ 12-14 h wall.
19 × 15,360 games ≈ 290k games ≈ 1,600 core-h of play at ~20 s per game (less with a cheaper admitted cost arm).
A CPU learner would take ~1 h per 512-game update (measured 463 s for 32 games on 2 contended threads), hence the GPU.
