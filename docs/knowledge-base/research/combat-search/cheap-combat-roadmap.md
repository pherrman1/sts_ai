# Cheap combat for the PPO loop: roadmap to about 40% Heart at a PPO-sized CPU budget

Last verified: 2026-11-11 against main `21a6baf` (ledger through §788), step 0 results added the same day. Research
and planning only: no gameplay seeds were run for this page and nothing here is a run authorization. Labels: **Measured** (cited ledger entry or
artifact), **Inference** (reasoning here), **Unverified** (not checked in code or data).

## Purpose / research question

Philipp asked (2026-11-11 21:31 CET) for a roadmap to keep the about 40% A20 Heart-kill rate of the Gumbel teacher
(§775, G16 + mb4) without paying for its simulations: a combat model strong enough for about 40% and cheap enough
that 100 PPO iterations fit in about 10 hours.

## Current conclusion

- **The target is about 100-140 CPU-s per run, against G16 + mb4's 509 s: a factor of 3.7 to 5.** At that CPU
  today's budget curve gives about 24-30% Heart, not 40% (§779, §781).
- **No tested idea closes that gap.** Every cut to G16's budget so far gave up Heart kills roughly in proportion
  to the CPU saved (§781, §783, §786), and the distilled net added nothing on top of the 16k search (§773, §788).
- **Step 0 (offline, 2026-11-11) moved the main lever.** 86% of G16's CPU is in boss rooms and Act 4, where a
  simulation costs 10-20× a hallway one because those rooms play prior playouts (g7f_E MLP at every playout step;
  ADR-0050, ADR-0060, never gated in whole runs). All Act 1-3 normal and elite fights together cost about 80 s per
  run. **Measured** ([step 0](../../../experiments/evidence/cheap_combat_step0_20261111/README.md)).
- **New rank 1: G16 + mb4 with greedy playouts everywhere** (`STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0`, an existing
  flag, no code change). **Inference:** about 130-200 s per run, if boss simulations then cost 2-4× a hallway one;
  its Heart rate is the open question (section "Track 0"). **Result (§790, 2026-11-11):** WORSE, Heart 35.7% vs
  41.2% (−5.5 pp [−8.1, −2.9]) at 0.27× the CPU (143 s per run); still the best Heart rate per CPU found so far.
- **The narrow Gumbel root is demoted.** Roots have 6.3 legal actions on average, so k 16 already searches almost
  all of them; the distilled net's top 4 holds the teacher's pick in 91.9% of roots (g7f_E 88.6%), below the
  95% rule. **Measured.**
- **One lever has more than 10× headroom but changes what "combat model" means**: a fight-outcome surrogate that
  the PPO actors sample instead of playing fights. It needs Philipp's call (section "Track 4").
- **Inference:** Track 0 plus the Act 4 budget (Track 2) is the most plausible way to the target. Whether it keeps
  about 40% is untested; ADR-0050's fight-level boss gain (+12.6 score, interval through 0) is the risk.

## The CPU target

| quantity | value | source |
|---|---|---|
| games per PPO update | 520 (40 parts of 13) | LONG_C PREREG, **Measured** |
| games in 100 updates | 52,000 | |
| CPU in 10 h on 200 cores | 2,000 core-h | Philipp's budget |
| ceiling per game, no overhead | 138 s | 2,000 core-h / 52,000 |
| learner and transfer per update | about 100 s | LONG_B 3:07 per update at about 27 s per game on 160 lanes, **Inference** |
| realistic per game (160-200 lanes) | about 80-100 s | (360 s − 100 s) × lanes / 520 |
| out-of-combat policy per game | about 8 s | LONG_C actors 27 s vs combat B 19 s, **Inference** |

Two constraints follow, not one:

- **Mean CPU:** about 100 s per run (80-140 s). G16 + mb4 costs 509 s (§775), so 100 updates cost about 7,300
  core-h (37 h on 200 cores).
- **Longest game:** under `--pipeline 1` the actors never run more than one update ahead, so an update lasts at
  least as long as its slowest game (**Unverified** beyond the `ppo_cloud.py` header). A 6-minute update needs
  every game to finish in about 4 minutes. A G16 run that reaches the Heart pays 350-415 s for Act 4 alone (§781).

## What the evidence prices

Whole runs, net-0420 out of combat, the same 512 seeds (§778, §779, §781; **Measured**):

| combat | Heart | CPU s/run | note |
|---|---|---|---|
| B1 (combat B, flat 1k) | 21.9% | 19 | net-0420's training combat |
| G1 / G2 / G4 / G8 | 22.3 / 27.2 / 29.7 / 31.6% | 18 / 40 / 87 / 166 | Gumbel k 16 + mb4, Act 4 at own budget |
| G1S / G2S / G4S / G8S | 24.4 / 30.7 / 33.4 / 34.4% | 137 / 193 / 250 / 315 | same, Act 4 strong |
| D (A20 default) | 30.9% | 248 | |
| G16 + mb4 | 40.4% | 509 | the teacher; 41.2% on 1,024 seeds |
| G32 / G64 + mb4 | 39.3 / 39.8% | 864 / 1,750 | flat above 16k |

- **Budget, acts 1-3:** about +3.3 pp per doubling from 2k to 16k, flat above (§781). Mean cost is about 41 µs per
  simulation (G8: 4.04 M simulations in 166 s); Awakened One and Time Eater cost 240-305 µs (rollouts to fight end).
- **Act 4 strong:** +2 to +4 pp at every budget for 119-163 s per run, 350-415 s per run that reaches Act 4 (§781).
  **Inference:** at G16 that is about 35-40% of the 509 s.
- **Where the gain is:** Act 1-2 elites, the Act 2 boss and the Heart; normal fights matter through HP carried
  forward (§782, §786).

What did not work as a cheaper substitute (**Measured**):

| idea | result |
|---|---|
| G16 only in elite and boss rooms (§786) | −3.2 pp at 0.85× CPU, WORSE |
| learned stop on the Gumbel root (§783) | −2.3 pp at about 0.76× CPU, INCONCLUSIVE (borderline worse) |
| net root prior at 4k-10k (§773) | NO_GAIN |
| distilled net as tree and wide-root prior at 16k (§788) | −1.4 pp, NOT_SHOWN |
| tuned tree constants c2 (§777), reuse cap up or down (§780, §785) | −4.7, −2.9, −2.7 pp |
| value head as Q-init or leaf (distillation thread, calibration 2026-11-11, §789) | not run: net error 11-49 HP vs rollout noise 13-30 HP per rollout |

Two numbers bound the net-based options:

- **A net forward costs about 60 simulations** (2.5 ms on a cloud core for d 128, 4 layers, against 41 µs;
  `environment-variables.md`, `STS_SILVER_COMBATNET_PRIOR`). At 100 s per run and about 520 roots that is about 75 forwards per root with no rollouts at all.
- **A leaf value must beat 60 rollouts to pay for itself**, that is an error near 13 / √60 ≈ 2 HP in acts 1-2.
  The calibrated head is at 11 HP in Act 1 normal fights and 49 HP at the Heart. **Inference:** value-for-rollout
  is two orders of magnitude (in variance) away; a stronger value net alone does not reach it.
- **Policy-only play is not a candidate.** The net's argmax loses 1.16-1.29 score points per root against the
  teacher's Q, the g7f_E prior 1.38, the teacher 0.28 (§787). No gameplay number exists; **Inference:** well below
  combat B.

## Roadmap, ranked

### Step 0. Offline analyses (done 2026-11-11, no seeds, no workers)

Data, scripts and tables: [step 0 evidence](../../../experiments/evidence/cheap_combat_step0_20261111/README.md).

- **0a. CPU map of G16** (§783's 1,024 stop-trace runs, 574,741 roots, 585 s per run on those machines):

  | rooms | CPU s/run | share | µs per simulation |
  |---|---|---|---|
  | Act 1-3 normal, elite, other | 81 | 14% | 7-19 |
  | Act 1 / 2 / 3 bosses | 35 / 64 / 158 | 6 / 11 / 28% | 74 / 128 / 172 |
  | Shield and Spear (prior playouts, ADR-0060) | 40 | 7% | 130 |
  | Heart (40k) | 191 | 34% | 171 |

  Game CPU: median 457 s, p90 1,318 s, max 4,976 s (the longest-game constraint is the Act 4 tail).
- **0b. Top-k coverage** on T1's 310,371 multi-action validation roots: hit@k (teacher's pick among the top k) and
  regret@k (teacher Q minus the best searched Q inside the top k, score units, teacher's own Q):

  | k | 1 | 2 | 3 | 4 | 6 | 8 |
  |---|---|---|---|---|---|---|
  | g7f_E prior hit / regret | 44.6% / 2.00 | 66.9% / 0.76 | 80.5% / 0.36 | 88.6% / 0.19 | 96.1% / 0.06 | 98.6% / 0.03 |
  | distilled net hit / regret | 49.0% / 1.34 | 72.1% / 0.50 | 84.8% / 0.24 | 91.9% / 0.13 | 97.5% / 0.05 | 99.2% / 0.02 |

  Bosses and Act 4 are hardest (net hit@4 90.5% / 87.2%). The rule "hit@4 ≥ 95% and regret@4 ≤ 0.10" fails for
  both; k 6 passes, but barely narrows a 6.3-action root.

### Track 0. Greedy playouts in G16 (cheapest gameplay test, new rank 1)

- **Hypothesis:** at 16k the Gumbel root and max backup carry the teacher's gain; prior playouts add little on top
  but cost most of the CPU. ADR-0050's evidence was fight-level at 10k with the gen-6 prior (§541: bosses +12.55
  score [−0.87, +26.57], 7.29× CPU per fight); the run-level effect was never gated.
- **Smoke first (needs a go; about 0.5 lane-h):** replay 4 of §775's seeds that reach the Heart with the flag at 0,
  to measure µs per boss simulation and CPU per run. It turns the 130-200 s estimate into a number.
- **Experiment E0:** GP16 = §775's G16 + mb4 with `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0`, on §775's 1,024 seeds,
  G16 reused after a 32-seed sentinel (ADR-0064), SPRT nonregression with a 3 pp margin, CPU co-primary.
- **Cost:** about 1,024 × 150-200 s ≈ 45-60 lane-h, about 1.5 h on 40 workers. No new seeds, no code change.
- **Decision rule:** GP16 within 3 pp of G16 at ≤ 0.4× CPU → GP16 is the cheap-combat candidate, then Track 2
  on top. Worse by more than 3 pp → spend the saved CPU as boss budget instead (GP16 with bosses and Act 4 at
  64k greedy, about equal CPU to today, as a follow-up arm), or keep prior playouts only at the Heart.
- **Result (§790):** WORSE, −5.47 pp [−8.11, −2.93] at 0.27× CPU; about half of the loss is the Act-4 conversion
  ([RESULT](../../../experiments/evidence/greedy_playouts_g16_20261111/RESULT.md)). Next: per-encounter budgets
  (prior playouts and simulations per encounter class; Philipp's go 2026-11-11 23:43 CET) and the narrow root on
  G16 (Philipp's choice, 23:47 CET).

### Per-encounter budget (after E0; Philipp's go 2026-11-11 23:43 CET)

- **Result (§792, 2026-11-12):** whole runs against E0's GP16 on §775's seeds
  ([RESULT](../../../experiments/evidence/encounter_budget_wholerun_20261112/RESULT.md)).
  - H4 (4,000 simulations in Act 1-3 hallway fights): +0.39 pp [−2.54, +3.22], NOT_WORSE_3PP, at 0.82× CPU (117 s per run).
  - A4P (prior playouts only in Act 4): +1.56 pp [+0.10, +3.12], PASS, at 2.07× CPU (297 s).
  - A4P − G16: −3.91 pp. G16's lead over GP16 is about 1.6 pp from Act-4 and 3.9 pp from Act 1-3 prior playouts.
  - Hallway simulations are cheap, so H4 saves only about 27 s per run.
- **Next:** the proven-win stop (Heart CPU), then Act 1-3 boss prior playouts at a lower budget and Act-4 budgets on
  top of A4P.

### Plan commitment (Philipp's idea, 2026-11-12 08:33 CET)

- **Idea:** at a root reached without a chance event since the previous root, play the reused tree's plan edge
  without a new search (`STS_SILVER_PLAN_COMMIT`).
- **Result (§793, 2026-11-12):** whole runs against §792's A4P on §775's seeds
  ([RESULT](../../../experiments/evidence/plan_commit_wholerun_20261112/RESULT.md)).
  - PCH (always): −3.91 pp [−6.74, −1.07], WORSE, at 0.54× CPU (161 s per run).
  - PCS (plan edge ≥ 90% of the inherited visits): −0.20 pp [−2.83, +2.54], NOT_WORSE_3PP, at 0.81× CPU (240 s).
- **Result on the cheap stack (§795, 2026-11-12):** HPS = H4 + PCS against §792's H4: −3.71 pp [−6.54, −0.88], WORSE,
  at 0.73× CPU (85 s per run) ([RESULT](../../../experiments/evidence/pcs_cheap_stack_20261112/RESULT.md)). H4 stays
  the cheap candidate; plan commitment helps only on a strong tree (A4P and up).

### Track 1. Narrow Gumbel root (demoted by step 0)

- **Result (§791, 2026-11-12):** k 4 without noise at 8k on G16 + mb4: P4 (g7f_E top 4) −8.40 pp [−11.43, −5.37],
  N4 (net top 4) −7.32 pp [−10.16, −4.39], both WORSE at about 0.6× CPU; N4 − P4 +1.07 [−1.86, +4.10]
  ([RESULT](../../../experiments/evidence/narrow_gumbel_root_20261111/RESULT.md)). Track closed.
- **Turn-plan root filter (#1058, offline, 2026-11-15, Measured):** a cross-fitted plan scorer on deterministic
  turn plans keeps G16's pick slightly more often than the prior at equal width but loses more Q than the freed root
  budget is worth under every rule (best net −0.033 Q at recall 97.8 %); NOT_PURSUED
  ([RESULT](../../../experiments/evidence/turn_plan_root_filter_20261115/RESULT.md)).

- k 16 already covers almost every root, so a narrower k saves little. With the net at k 4, 8.1% of roots lose the
  teacher's pick (regret 0.13 on average). Only worth a test at low budgets (2k-4k), and only after Track 0.

### Track 2. Act 4 budget

- **Why:** 350-415 s per Act-4 run exceeds the whole target and the 4-minute game limit. Which part carries the
  +3 pp (Heart at 40k, the 262,144 reuse cap, prior playouts at Shield and Spear) is not separated.
- **Experiment E2:** fixed-state copies (`selffights` / `expertfights`) on the Heart and Shield-and-Spear entry
  states of §775's G16 games (495 Heart arrivals), Heart at 4k / 8k / 16k / 40k, with greedy playouts if Track 0
  passed (prior playouts otherwise). Metric: kills per arrival and CPU per fight.
- **Cost:** about 100-150 lane-h (the 40k arm dominates; it can reuse §775's own outcome as a descriptive
  reference to halve this). No new seeds.
- **Decision rule:** the cheapest setting within 2 pp kills per arrival of the 40k arm becomes the Act 4 setting
  of the cheap combat.

### Track 3. Throughput at identical play

- **Why:** the 2026-10-21 profile had 83% of combat CPU in playouts and 54% in the rollout policy's MLP; three
  bit-identical PRs then gained about 1.5×. No profile of the Gumbel configuration exists.
- **Step:** profile G16 on 3-4 already used §775 seeds (about 1 lane-h, replays), list items worth ≥ 10% each,
  implement only those, verify by exact replay of §775 games.
- **Expectation (Inference):** 1.2-1.5×. Rollout length in Awakened One and Time Eater (6-15× the mean cost per
  simulation) is the obvious item, but a cap changes play and needs its own gate.

### Track 4. Fight-outcome surrogate for the PPO actors (Philipp's call)

- **Idea:** the actors do not play fights; they sample the outcome (death, HP, potions, max HP, gold and the other
  post-fight fields) from a model fitted on G16's fights. Hybrid version: surrogate in normal fights (12.6 of
  about 20 fights per run, rarely fatal), real search in elites, bosses and Act 4.
- **What exists:** the CTM machinery (0.6 ms per fight; post-fight HP RMSE 9.1-11.7 against Silver, §408-§410);
  134,858 G16 fights from D2 (§787), 46,932 traced fights (§782), 1,024 runs of stop data (§783).
- **Why it could fail:** PPO optimises against the model's errors (the leaf-exploitation pattern of §656 / §675);
  whole runs played through the CTM drifted to 24.7% against 31.9% Heart from small resource errors over about 17
  fights (2026-11-01 audit, project notes, not in the ledger).
- **First step (offline, no seeds):** fit the outcome model on G16 fights, check calibration by encounter, entry HP
  and deck features on held-out runs. **Decision rule:** death calibration within 1 pp per encounter class and
  HP bias within 1 HP → propose a PPO pilot whose resulting net is evaluated with real G16 combat against net-0420.
- **Note:** this delivers G16-strength training signal at near-zero CPU, not a cheap combat player. net-0420 was
  trained under combat B (22%) and still reaches 41% under G16, so whether stronger actor combat improves the
  out-of-combat policy at all is itself open.

- **Playout prior retrained on G16 targets (issue #1053, Measured offline, ledger §804 on PR #1060, 2026-11-15):**
  g7f_E is still G16's playout policy (T2 / §788 replaced only the root and tree prior). A net of g7f_E's size and
  roughly its cost per call, trained on D2/D2b G16 + mb4 visit shares, lowers the argmax's root regret in playout
  rooms from 2.449 to 1.884 max-backed Q, and it is lower in every boss. Completed-Q targets and aux heads do worse.
  Whether that carries to playout states is open. The next step is §798's harness (arms at 4k against asplayed),
  which needs a go. With §798's finding that a near-copy of g7f_E (KL 0.023) already costs +0.24 Q at equal sims,
  the playout policy's quality is a steep lever (**Inference**).
  **Stage 2 (Measured, ledger §807, 2026-11-15): WORSE.** In §798's harness V loses +0.29 Q against g7f_E at 4k and
  +0.34 at 16k (V at 16k ≈ g7f_E at 2-4k), in every boss; the boss fine-tune X-B too. Root regret on G16's own
  path does not carry to playout states, and mixing in g7f_E's Silver data hurts G16-root regret. Next step, if
  any: label captured playout states with short searches (DAgger-style). Stage 3 (V in all four roles, whole-run
  gate) runs on its own go.

### Parked

- **Proven-win stop (next candidate; Philipp OK'd as a candidate 2026-11-12 00:58 CET):**
  at the Heart every win scores the same, so Silver could stop once `exact_combat_solver` proves a win this turn
  (draws enumerated). CPU only, no win-rate gain expected. First step offline on recorded Heart roots (§783/§775
  traces): how often a proven win exists and what share of Heart simulations is spent after it. Needs a go.
- **Value net as leaf or Q-init:** revisit only with a forward ≤ 50 µs and an error ≤ about 5 HP (see the bound
  above). §789 measured the boss case: net error 26-49 HP against one prior-playout rollout's 13-30 HP, so a boss
  value net in place of prior playouts (AlphaStS-style, suggested 2026-11-12) stays parked.
- **Learned stop:** at best about 1.3×; combine after Tracks 1-2 if still needed (§783).
- **Fight-class budgets, more budget, reuse-cap and tree-constant changes:** closed by §775-§786.

## Sequence and totals

1. Step 0: done (offline).
2. Track 0 smoke (about 0.5 lane-h) → E0 (about 45-60 lane-h) on §775's seeds.
3. Track 2 (Act 4 budget, about 100-150 lane-h) on top of the E0 winner; Track 3 profile in parallel (1 lane-h).
4. Confirmation of the combined cheap combat on fresh seeds in the PPO actors' setting.
5. Track 4's offline fit can start any time; its PPO pilot needs its own go.

Every gameplay step needs Philipp's typed go, a PREREG and a prelaunch review. No new seeds until step 4.

## Open questions

- Does PPO need 520 games per update under a stronger, less noisy combat? Halving it doubles the CPU target.
- How much cheaper are sampled training games (temperature 1, in-sample Heart about 20% under combat B) than
  evaluation games under Gumbel combat? Not measured.
- Is the one-update lag the only coupling between actors and learner, or can slow games be carried over?

## Sources

- Ledger §773, §775-§788 in [ledger-06](../../../experiments/ledger-06.md).
- [LONG_C PREREG](../../../experiments/evidence/ppo_long_c_20261106/PREREG.md) (iteration size, wall per update).
- [Act-4-strong budget curve](../../../experiments/evidence/gumbel_act4strong_1k8k_20261110/RESULT.md) (per-arm table).
- [Leaf evaluation](leaf-evaluation.md), [A20 PPO plan](../a20-ppo-plan.md).
