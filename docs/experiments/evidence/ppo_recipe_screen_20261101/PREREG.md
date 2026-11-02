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
- **Launch (§744, 2026-11-02): start net heart1 (G0: −0.24 pp [−2.00, +1.51] → HEART1), combat K15** (200 hallway
  sims, no learned Silver prior; `actors_frozen.env`). Actors' binary `71cfd280` built at main `defaa93` (includes
  #957's CombatReward fix after the f17d898 smoke binary).

**Runner.** `tools/heart1/ppo_cloud.py`: cloud actor containers (4 game threads each; 2 per arm, 4 for G_1024) play
the games; one learner process on Philipp's PC (RTX 3060 Ti, bf16) trains every arm, oldest iteration first. They
exchange games and nets through git refs `refs/heads/ppo-xfer/screen1/<ARM>/...` of this repository (actors only
create refs; the PC deletes every consumed ref). `--pipeline 1` (iteration i played by net_{i-1}, PPO ratio against
the recorded log-probs). `STS_OOC_HEART1_PPO=1`: the net makes every out-of-combat decision
(gold automatic), sampled at temperature 1 with salt = iteration. Ascension 20. Binary: current main's `one_combat`
(sha in `screen.manifest`; main 336c1f8, not the cost campaign's 6c96c25 binary, so the chosen combat setting
transfers approximately; all arms share it). With `STS_OOC_HEART1_PPO=1` the net decides before any rule, so the
`STS_OOC_STRATEGIC_*` and key flags of the cost campaign's env are absent from `actors_base.env` on purpose.

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
arm with G games per iteration plays 111400000 + G i …, split into its parts. Smokes 111419990-111420001 (smoke1 used 111419990-997, smoke2 111419990-111420001).

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

**Transport volume** (git refs under `refs/heads/ppo-xfer/screen1/`, deleted after use; per stored file ≤ 64 MB):
585 nets (17 × 31 + 61 + 16) × 24.2 MB with heart1 ≈ 14 GB pushed (student_sel: 1.4 MB, ≈ 0.8 GB); trajectories
≈ 12.5 KB per game × 292k games ≈ 3.6 GB. Live at any time: the newest two nets per arm (≈ 0.9 GB with heart1) plus
unconsumed parts. After the screen `ppo_cloud.py cleanup` deletes every ref; all nets stay on the PC.

**Workers.** Exactly 40 actor workers (one per part); the screen starts after the cost-arm campaign has released its
24. A worker whose container resets re-runs `setup` and `start` (the actor resumes; at most one part is replayed).

**Amendments during the run (2026-11-02, before any arm reached iteration 20, the first iteration of the primary
metric; review K).**
- Learner (no effect on the arms' math): #963 reloads each arm's learner from `state.pt` per update (the 8 GB GPU ran
  out of memory with all 19 arms resident; K: nets, stats and Adam moments byte-identical to the resident learner).
  #964 adds `--micro-batch`; the PC serve runs with `--micro-batch 192` from 09:02 CET, which only changes MB_512
  (minibatch 512 does not fit the card): gradient accumulation over chunks of ≤ 192 decisions with minibatch-wide
  denominators, one step per minibatch, so MB_512's update equals the unchunked one up to rounding (K: ≤ 2.9e-6 in the
  parameters). MB_512 used it from its iteration 0; every other arm (minibatch 192) is bitwise unchanged.
- **Combat stalls count as losses** (#965, worker RUN_COMMIT f32c9a96, build inputs and binary unchanged). A sampled
  policy can build a deck whose fight never ends; the native Silver backend then stops the game at 1,000 combat
  decisions ("stall"), and the game's trajectory is lost. First case: WU_10 iteration 7, seed 111403638 (floor 45).
  Such a game counts as no Heart kill (a game line with no decisions: no training signal). Cap: at most ⌊1% of one
  actor part⌋ (2 of a 256-game part, i.e. every arm but G_256; 1 of G_256's 128-game parts); a part above the cap stops its
  actor as any other failure does. The arm then stops at that iteration and is reported **INCOMPLETE** (no verdict;
  its games up to then are listed), not continued with a raised cap.
- **Analysis additions.** RESULT lists the stalled games per arm (from the actor parts' meta `"stalled"` and the
  stalled game lines kept in the PC's `parts/`; `games-NNNN.csv` is unchanged), and reports, next to the primary D,
  a sensitivity D that drops every seed on which any arm stalled (in any iteration of the last third). The verdict
  uses the primary D; a sensitivity D that changes a verdict is named in RESULT.
