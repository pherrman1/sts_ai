# Cheap combat for the PPO loop: roadmap to about 40% Heart at a PPO-sized CPU budget

Last verified: 2026-11-11 against main `21a6baf` (ledger through §788). Research and planning only: no gameplay
seeds were run for this page and nothing here is a run authorization. Labels: **Measured** (cited ledger entry or
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
- **Three levers are untested and cheap to test**, in this order: (1) a narrow Gumbel root (k 2-4) whose candidates
  come from the distilled prior, at 2k-4k simulations; (2) the Act 4 budget, which alone costs more than the whole
  target; (3) throughput at identical play.
- **One lever has more than 10× headroom but changes what "combat model" means**: a fight-outcome surrogate that
  the PPO actors sample instead of playing fights. It needs Philipp's call (section "Track 4").
- **Inference:** levers 1-3 together plausibly reach about 37-39% at about 150-200 s per run (100 iterations in
  about 13-17 h). The full target needs lever 1 to work better than a factor of 2, or Track 4.

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
| value head as Q-init or leaf (distillation thread, calibration 2026-11-11, ledger entry pending) | not run: net error 11-49 HP vs rollout noise 13-30 HP per rollout |

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

### Step 0. Two offline analyses (no seeds, no workers, about half a day)

- **0a. CPU map of G16.** Simulations and CPU by act × room × halving phase from §783's stop-trace data (1,024 G16
  runs with per-root rows) and the per-game counters. Output: where the 509 s go, and the share of roots with
  few legal actions.
- **0b. Top-k coverage of the distilled prior.** On T1's 330,542 validation roots (§787): for k = 1..16, how often
  the teacher's final pick is among the net's top k, and the backed-Q regret of the best action inside the top k;
  the same for the g7f_E prior; split by room class. One inference pass over the rows (about 15 CPU-min).
- **Decision rule 0b:** net top-4 holds the teacher's pick at ≥ 95% of roots and top-4 oracle regret ≤ 0.10 →
  Track 1 is live with the net. Only the g7f_E prior passes → Track 1 with the prior, the net is not needed.
  Neither passes at k ≤ 8 → drop Track 1.

### Track 1. Narrow Gumbel root from the prior at low budget (cheapest gameplay test)

- **Hypothesis:** at k 16 and 16k the last two candidates get about 3,750 simulations each. At k 4 and 4k they
  get about 1,500, at k 2 and 4k 2,000. If the prior's top k holds the teacher's pick, a quarter of the budget
  buys most of the final resolution. §776 found k inactive at 16k; at 2k-4k it is untested, and §788 lists
  "lower K" and "the net prior under cheaper combat search" as untested.
- **Experiment E1:** §779's 512 seeds, net-0420 out of combat, G2 / G4 / G16 reused as controls after a 32-seed
  sentinel (ADR-0064). Arms: `K4@4k` with the g7f_E prior, `K4@4k` with the distilled net prior at every root
  (`STS_SILVER_COMBATNET_PRIOR=1`, generalist net), Act 4 at own budget as G4.
- **Cost:** 2 arms × 512 runs × about 90 s ≈ 30 lane-h, under 1 h on 40 workers. No new seeds. Flags exist
  (`STS_SILVER_GUMBEL_ROOT=K`, K 2..64); **Unverified:** that the whole-run path samples the k candidates from the
  net prior without a code change (smoke first).
- **Decision rule:** an arm − G4 ≥ +3 pp with the 95% interval above 0 → budget × k grid (k 2/4/8 at 2k/4k/8k,
  about 150 lane-h) to find the cheapest arm within 3 pp of G16's Act-4 reach. Net arm ≈ prior arm → continue
  with the prior only. Both ≤ G4 → Track 1 is closed and recorded as negative.

### Track 2. Act 4 budget

- **Why:** 350-415 s per Act-4 run exceeds the whole target and the 4-minute game limit. Which part carries the
  +3 pp (Heart at 40k, the 262,144 reuse cap, prior playouts at Shield and Spear) is not separated.
- **Experiment E2:** fixed-state copies (`selffights` / `expertfights`) on the Heart and Shield-and-Spear entry
  states of §775's G16 games (495 Heart arrivals), Heart at 4k / 8k / 16k / 40k, narrow k from Track 1 if it
  passed. Metric: kills per arrival and CPU per fight.
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

### Parked

- **Value net as leaf or Q-init:** revisit only with a forward ≤ 50 µs and an error ≤ about 5 HP (see the bound
  above).
- **Learned stop:** at best about 1.3×; combine after Tracks 1-2 if still needed (§783).
- **Fight-class budgets, more budget, reuse-cap and tree-constant changes:** closed by §775-§786.

## Sequence and totals

1. Step 0 (free) → E1 (about 30 lane-h) → grid (about 150 lane-h) if E1 passes.
2. E2 and the Track 3 profile in parallel with the grid (about 100-150 lane-h and 1 lane-h).
3. Confirmation of the combined cheap combat against G16 + mb4 on §775's 1,024 seeds (control reused, SPRT
   nonregression, about 50 lane-h at 150 s per run).
4. Track 4's offline fit can start any time; its PPO pilot needs its own go.

Every gameplay step needs Philipp's typed go, a PREREG and a prelaunch review. Total before the confirmation:
about 300-350 lane-h, no new seeds.

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
