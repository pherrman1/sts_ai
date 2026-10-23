# Value-head plan stages 1–2: X2-B-free referee and leaf-compare replay at A20 (pre-registration)

Written 2026-10-23 before any game of this campaign ran and before any outcome of the stage-3 A/B
(`../value_level_ab_20261023/`, running since 2026-10-22 23:07Z) was looked at. Stages 1 and 2 of the value-head
research plan ([doc](https://claude.ai/artifact/MoLmbWb4QXdLTEsDVYgt4a), sections 6–7).

**Authorization:** Philipp, 2026-10-22 21:44Z, in the research thread: "keep going with the plan, you can use 32
workers if you want to, just do it, i allow it." The coordinator launches the workers from the frozen brief.

## Question
1. **Referee (stage 1).** Is there a cheap judge of OOC decisions that never reads X2-B and whose level matches real
   outcomes in every act? Two candidates come from the same rollouts:
   - **R_full:** heart1 greedy rollouts with CTM combats played to the end of the game; a death scores 0, a Heart
     kill 1 (`STS_OOC_MCTS_LEAF_COMPARE_REFEREE`).
   - **R_act** (the plan's fallback): the same rollout stopped at the first map state past the root's act and valued
     there by M0's calibrated X2-B, σ(a_act + b · logit X2-B); a death or kill before that is its own value
     (`STS_OOC_REFEREE_ACT_END`). From an act-4 root R_act equals R_full.
2. **Leaf-compare replay (stage 2).** At every searched root of real play, the same search (config, seed, budget,
   stops) runs once per candidate leaf. Where a leaf's pick differs from the played action, the referee values both
   with paired rollouts. Summed over a game and averaged over games, these advantages predict the leaf's change in
   Heart rate (performance difference lemma, first order). Does that prediction reproduce the three past A20 leaf
   A/Bs (§504, §522, §615), and what does it predict for the stage-3 arms?

## Background
- **Stage 0** (§TBD in PR #817): X2-B over-prices a death 3.3× (act 1) to 7.7× (act 3) relative to the calibrated
  Heart value; rollouts die more often than the real runs over the same horizon (real / rollout 0.59–0.85).
- **Pilot** (seed 111349994, 7 arms, n 16; see "Pilot and smoke" below): about 40 ms of CPU per full-game referee
  rollout; R_full looked far below real play (one Heart kill in the first 32 rollouts from floor 0). That is why
  R_act rides along.
- **Why not concordance:** concordance with rollout3 labels pointed the wrong way in both A20 leaf tests that have
  both numbers (§504, §615).

## Design (`run_unit.sh` is the source of truth)
- **Play:** the stage-3 control arm A exactly (`../value_level_ab_20261023/run_unit.sh` COMMON): student_sel OOC
  prior and rollout net, OOC MCTS 4096 sims, rollout3 X2-B leaf, learned OOC stop 0.99, 25% full-budget roots, fast
  roots capped at 1024, learned Silver stop with exact root budgets, g7f_E root table and prior, boss-only prior
  playouts, keys on, CTM rows on. Full games, Heart objective.
- **Leaf compare:** `STS_OOC_MCTS_LEAF_COMPARE` with seven arms. Each arm searches on a fresh model with this root's
  config, search seed and budget (fast-root cap, full-root budget, learned stop and its features unchanged):
  | Arm | Leaf | Source |
  | --- | --- | --- |
  | M0 | calibrated X2-B, `-2.5384,-2.9227,-3.6523,-3.6334:1.0535` | stage-3 arm M |
  | S | SR_w1 value head blended at w 0.1 (`sr_w1.bin` 146a4512…) | stage-3 arm S |
  | MS | both | stage-3 arm MS |
  | G1B | gen 1b value head at w 1 (`gen1b.bin` e6aa044c…) | §615 arm B |
  | STU | §494 rollout student (`student494.bin` 653db96e…) | §504 arm S |
  | TD2 | Heart leaf td2 (`models/candidates/heart_leaf_td2/heart_leaf.json`, 1b1ad13e…) | §522 arm H |
  | NULL | no leaf change, search seed salted (`seed_salt=7`) | noise control |
- **Referee:** n = 64 rollouts from the played action and from every differing pick at every searched root
  (singleton roots excluded), rollout i of every action sharing one random stream; R_act noted on the same rollouts.
- **Play is unchanged** by construction: side searches run on fresh models, each from the thread's OOC policy state
  as the real search found it, and the real run gets back the state the real search left; the referee runs in a
  forked child. Checked before launch on smoke seed 111369991 (full games; heartoutcomegen runs only full games):
  the decision sequence of the compare game equals the same binary's game without the compare, and that equals the
  frozen stage-3 binary's arm-A game.
- One unit is one seed (one game). The stage-3 A/B's own games cannot carry this (their binary is frozen).

## Definitions (`analyze_compare.py`)
- **Valid game:** rc 0 with a `complete`, `integrityPassed` footer. Invalid games are reported, not replaced.
- **Referee value** of an action at a root: the mean of its usable rollouts (no error; for R_full, terminal).
- **Flip:** an arm's search returned a pick, did not abort or fail, and picked an action other than the played one.
- **Advantage** Â at a flip: mean_i [ref(arm pick, i) − ref(played, i)] over the rollouts usable for both.
- **Predicted Δ Heart rate** of an arm: the mean over valid games of D_g, the sum of Â over the game's flips (0 for a
  game without flips); 95% interval from a seed bootstrap (2,000 resamples, RNG 20261023).
- **Level by act** k: over the searched roots in act k, the mean referee value of the played action against the
  mean real outcome (1 = this game killed the Heart); bootstrap over games.

## Gates
**Stage 1, referee.** A referee qualifies when both hold (the plan's stage-1 gate):
1. Level: |level − real| ≤ 0.05 in each of acts 1–4 (point estimates).
2. Precision: the SE of M0's mean advantage over its flips is ≤ 0.002, and the referee CPU attributable to M0 (2n
   rollouts per M0 flip at the measured CPU per rollout) is ≤ 10 core-hours.

R_full is used if it qualifies, else R_act; if neither does, stage 2 has no qualified referee, its numbers are
reported under both as exploratory, and the metric is **NOT QUALIFIED**. The same SE and cost are reported for every
arm. An arm whose search failed at more than 1% of its roots is flagged (a failed root counts as no flip).

**Stage 2, qualification** under the qualified referee. **QUALIFIED** only if all hold:
1. STU (§504: reached Act 4 −10.9 pp [−20.3, −1.6], Heart kills 12 vs 20 of 128): the upper 95% bound of STU's
   predicted Δ is below 0.
2. TD2 (§522: Heart kills −0.8 pp [−3.5, +2.1]): TD2's predicted Δ lies in [−3.5, +2.1] pp.
3. G1B (§615: Heart kills +3.1 pp [−1.0, +7.2]): G1B's predicted Δ lies in [−1.0, +7.2] pp.
4. NULL: its 95% interval contains 0.

The replays run on today's stack (student_sel, 4096 simulations, learned stop), not on the stacks of §504, §522 and
§615, so these check direction and size, not exact numbers. Three retrospective points are thin; the metric stays
provisional until prospective points accumulate.

**Prospective (stage 3).** Predicted Δ for M0, S and MS against arm A, the M0 main effect (Δ_M0 + Δ_MS − Δ_S) / 2
and the blend main effect (Δ_S + Δ_MS − Δ_M0) / 2, each with its interval (joint bootstrap). They become the first
row of the predicted-vs-observed table. The method is frozen here, before any stage-3 outcome is looked at; this
campaign runs after the A/B finishes, so the A/B's result may be known first, but nothing in this file, the scripts
or the binary changes after that.

## Descriptive outputs
Flip rates per arm and act; arm search CPU per root; referee CPU per rollout; mean paired variance v; split-half
predictions (seed parity); errored, non-terminal and missing rollouts; arm errors; the level table for both
referees; R_full against R_act predictions side by side.

## Not in this campaign
- **Headroom** (the plan's replay with the referee itself as the leaf). With the pilot's paired variance
  (v ≈ 0.18 for R_full), a headroom summed over the roughly 70 searched roots of a game has a standard error of
  several pp at 256 games, too wide for the plan's "below about 2 pp" rule, and the referee-leaf searches would
  double the cost. It gets its own design once this campaign has measured v for both referees.
- **Re-scoring the existing heads** (plan stage 1): G1B and S are the existing heads; the replay scores them where
  they change a pick, which is the score the metric needs.

## Seeds, workers, cost
- Seeds 111360000–111360255 (256 games, assigned by the coordinator 2026-10-22 23:14Z; unused in the repo).
  Smokes 111369990–111369999. The pilot used 111349994–111349995 (from the stage-3 smoke range).
- 32 workers × 4 lanes, `schedule queue`, 8 h timeout per unit (rc 124).
- Cost (pilot and smoke): the seven side searches take about 40 s of CPU per searched root (about 150 s at a
  full-budget root, 17 s at a fast one), a referee rollout 22–40 ms (1.4–2.6 s per action at n = 64). With 25–80
  compare rows per game that is about 1 core-hour per game, about 260 core-hours in all, about 3 h of wall on 32
  workers.

## Pilot and smoke
- **Pilot** (seed 111349994, n = 16, an earlier build of this code without the act-end value and the policy-state
  hand-back): with the compare on, every record after the header and every CTM row equal the same build's game
  without it (110 decisions, 54 compare rows). Side searches 37 s of CPU per root on average; referee about 40 ms
  per rollout on a loaded machine; mean paired variance of R_full at the first six flipped actions about 0.18.
- **Smoke** (seed 111369991, campaign binary `41b26423…`, the committed `run_unit.sh`):
  - Without the compare, the game (192 decisions, 108 searched, Act 4, no Heart kill) is byte-identical to the frozen
    stage-3 binary's arm-A game (`56b29bf8`): every record after the header, the CTM rows and the log.
  - With the compare: rc 0 with every banner check, and every record after the header and every CTM row equal the
    game without it. 79 compare rows (26/26/17/10 in acts 1–4), 6,016 referee rollouts, none errored or
    non-terminal, no arm error; 68 min of wall. `analyze_compare.py` runs on it.
  - Flips in this one game: M0 7, MS 7, STU 8, TD2 6, NULL 5, G1B 3, S 2. Mean paired variance at the flips: R_act
    0.003–0.016, R_full 0.02–0.09.
  - A first smoke on the binary before the hand-back (`1abc300e`, code `c9b40943`) gave the same byte-identity
    without the compare; a container restart cut its compare game.

## Before launch
1. Freeze: RUN_COMMIT, code commit, binary sha256 in `campaign.manifest` and the brief.
2. Smoke on the frozen binary: the identity checks above, and one full compare game rc 0 with the banner checks.
3. Independent pre-launch review.

## Decision
None by itself: the metric informs which leaf to A/B next; defaults still need an A/B and Philipp's call.
