# PPO run policy and a run-aware combat leaf: literature check

Last verified: 2026-11-02 for (A) item 7 (learner review fixes); 2026-11-01 (second web research round, 3-vote adversarial claim verification; read-only checks of
this repository at `336c1f8c`). No seeds were run for this page.

Labels: **Verified** = survived a 3-vote check against the primary source (19 of 24 checked claims did);
**Inference** = reasoning on this page, not stated by a source.

## Purpose / research question

Two questions from Philipp (2026-11-01):
- (A) What does the literature say about the choices in the [A20 PPO plan](a20-ppo-plan.md), and how can our own
  heart1-style PPO policy beat heart1?
- (B) Can the PPO net's value head be used as, or to correct, Silver's combat leaf?

## Current conclusion

- **Coverage is thin.** Only five sources survived: DouZero, VinePPO, PORL, KataGo and one 2026 preprint on paired
  rollouts. There is no surviving evidence on:
  - OpenAI Five, AlphaStar, Honor of Kings, Suphx oracle guiding, Hearthstone/LoCM;
  - PopArt, PPG, distributional critics, RUDDER, shaping pitfalls, asymmetric-critic bias;
  - PBT, quality-diversity and league training, per-episode latent exploration;
  - IMPALA/V-trace/APPO, RL scaling laws;
  - options/HRL terminal values, AlphaGo value/rollout mixing, adversarial leaf exploitation, Sobolev or monotone
    value training, ICM, match equity.
  Statements on those topics in the plan stay Inference.
- **(A)** The evidence supports four plan choices:
  - near-Monte-Carlo targets with the critic used only as a baseline;
  - candidate-token action scoring;
  - critic warm-up with the policy frozen;
  - a KL anchor that decays.
  KataGo's ablation also supports auxiliary heads on a shared trunk (a learning-efficiency gain in Go; the transfer
  is Inference). Forked common-random-number advantages stay low priority: §738 measured why, and the paired-rollout
  preprint is mixed evidence.
- **(B)** No source supports a learned run value as Silver's leaf. The usable template is KataGo's bounded,
  recentred score utility on top of a dominant term. Together with §724 (Incense Burner, +5.9 pp) and §721 (V-derived
  prices ≈ formula), this points to a few targeted, bounded run-aware terms rather than a generic V leaf.
- **B2 on heart1's critic (2026-11-02, §747): FAIL.** heart1's value head prices Fairy (35 HP), max HP (+1.6 HP per
  point) and partly the potion types right. But −3 HP lowers it in only 83% of 20,677 post-fight states, and its 1-HP
  price is noise (p10 −2.9, p90 +4.3 secant units). There is no heart1 leaf and no B3. Rerun on the own A20 PPO critic
  ([evidence](../../experiments/evidence/heart1_value_leaf_teacher_20261102/RESULT.md)).

## (A) Evidence on the PPO plan

1. **Critics fit the level, not sibling differences; keep λ near 1** (Verified, 3-0).
   - VinePPO (ICML 2025, arXiv 2410.01679): PPO value nets "barely outperform a random baseline when comparing
     alternative steps"; Monte Carlo estimates instead of the critic gave better test accuracy.
   - DouZero (ICML 2021, arXiv 2106.06135): "we do not observe a clear benefit of using TD learning … in the sparse
     reward setting".
   - This matches §685, §715 and §727 here.
   - Plan consequence (Inference): GAE λ 0.97 or 1.0, with the critic used only as a variance-reducing baseline. Nothing in the
     loop should rely on the critic to rank card choices.
   - Counterweight (not verified here): PerfectDou reportedly beat DouZero with PPO + GAE and a perfect-information
     critic.
2. **Score candidate actions, not a fixed classifier** (Verified 3-0, single preliminary run). DouZero's actor-critic
   with a masked classifier actor failed, attributed to the actor not generalising across action features. heart1
   already scores candidate tokens; keep that.
3. **Warm up the critic first; decay the anchor** (Verified 2-1 to 3-0; PORL, arXiv 2505.16856, preprint).
   - Fine-tuning from a policy-only start needs critic training with the policy frozen; without it, actor-only
     initialisation does very poorly.
   - A behaviour-cloning anchor removes the early drop but may cap the ceiling. Wolczyk et al. (ICML 2024, not
     verified here) found a KL/BC anchor helped on NetHack, so the effect is setting-dependent.
   - The setting is off-policy SAC on continuous control.
   - Plan consequence (Inference): keep the S1 value warm-up; make the KL arm decaying rather than fixed; expect an
     early-iteration dip.
4. **Agreement with the teacher is not a progress metric** (Verified 2-1). In DouZero, agreement with human moves
   rose and then fell while strength kept rising. DouZero trained from scratch, so this is weak evidence about
   anchoring.
5. **Forked advantages depend on shared randomness** (Verified 3-0 for VinePPO's mechanism).
   - VinePPO needs cheap resets and uses K = 9 rollouts per state. It was up to 3.0× faster in wall-clock (1.5× at
     7B), but each iteration was 2-5× slower.
   - A 2026 preprint (arXiv 2609.24144, "Luck Is Not Skill"; preprint, LLM agents, group-relative RL, 3 seeds) is
     **mixed evidence**. Its constructed one-step bandit counterexample (§4.3, App. A.1) has pairing lower the
     reward-contrast variance by ~9% while raising gradient variance ~2.2×, which shows a gain is not guaranteed. Its
     real gradient probe, however, found pairing **lowered** gradient-covariance traces at every checkpoint, by 21-30%
     (grader flips) and 40-63% (tool faults). Transfer to our whole-game forks is Inference.
   - Our numbers (Inference): at rho 0.49, about 480 paired forks give a standard error of ≈ 2 pp on a sibling
     difference (1σ); resolving a 2 pp difference at 95% needs ≈ 1,900. K = 9
     forks are noise per decision and can only help as an aggregate gradient term.
   - **Correction to the research synthesis:** it proposed a training-only per-floor RNG reseed as "the real
     enabler". §738 measured the ceiling of exactly that keying: overall rho 0.488 → ≈ 0.506, ≈ 1.04× effective
     seeds, with a map-root gap of −0.004. Event-keyed streams do help inside OOC rollouts (§703: 0.18-0.21× sibling
     variance with survival weighting), but that is a rollout estimator, not whole-game forks.
   - Plan consequence (Inference): V4 (forked CRN advantages) is low priority unless an offline gradient-variance
     probe on stored states shows a gain. This rests on §738 and our rho; the preprint supports neither side strongly.
6. **Unsupported plan items.**
   - Per-game coordinated exploration (V8): no surviving evidence either way. Our only measurement is the 5 pp cost
     of per-decision noise in self-play (§640), and that came from a different design.
   - Asymmetric critic (V6): PerfectDou is the only hint, unverified; the bias question is open, and the critic
     touches ADR-0002.
   - Auxiliary heads: **Verified** in KataGo (arXiv 1902.10565): §4.1 "these auxiliary targets noticeably improve the
     efficiency of learning", and the §5.2 ablation shows a noticeable drop in learning efficiency without the
     ownership and score targets. That is Go; whether CTM/value heads on our shared trunk give a similar gain is
     Inference. (Corrected after review K, 2026-11-02: the earlier "refuted 1-2" vote was wrong.)
7. **Learner implementation review (2026-11-02, read-only, our code, not literature).** Four findings in
   `tools/heart1/ppo_train.py` / `ppo_model.py`, fixed after the recipe screen (its arms kept the reviewed code):
   - Game order followed `one_combat bestbench`'s OpenMP completion order, so the per-update shuffle (which permutes
     positions, not games) made minibatch composition depend on thread timing: a replayed part could give a
     different net. `load_games` now sorts games by seed (steps by idx), tested on the same games in two line orders.
   - `load_games` keyed games by (file, seed): the same seed in two files counted twice, silently. Now an error;
     `update --expect-games N` fails on a count mismatch (a file cut at a line boundary loses games without a parse
     error; the cloud runner already checked counts and sha256).
   - The choice-logit and value Linears ran inside the bf16 autocast region, so the learner's log-probs carried bf16
     rounding against the fp32 behaviour log-probs the actor records (final-layer rounding alone: |Δlogp| p99
     1.5e-2, max 3.5e-2 on the S0 smoke records; `max_dlogp_behaviour` in each arm's `loop.json`). Both heads now
     run in fp32; the trunk stays bf16, so its rounding remains (review of #973, CPU bf16-autocast proxy on heart1.bin: mean |Δlogp| against full fp32 0.013 → 0.008, max ~0.095 from the trunk). The CUDA-side drop in `max_dlogp_behaviour` is **Unverified** (no CUDA
     machine in the fixing session); on CPU the heads are bitwise the fp32 heads.
   - `--reward heart_pbrs` read Φ from a `phi` field no actor writes, so it equalled `heart`. Chosen fix: the
     learner refuses `heart_pbrs` when no decision line carries `phi`; exporting Φ from `ppoStep` stays open (plan
     row V3).

### Ranked experiments for (A)

| # | Experiment | Cost class | Falsified if |
| ---: | --- | --- | --- |
| A1 | Critic warm-up (policy frozen) then PPO with a decaying KL to the start net, vs no warm-up and vs a fixed KL | short PPO arms (~15k games each) + SPRT gate | warm-up arm shows the same early drop and no better final gate |
| A2 | GAE λ 1.0 vs 0.97 | short PPO arm | no difference in the in-sample A20 curve or the gate |
| A3 | 512 vs 2,048 games per iteration at a fixed game budget | short PPO arm | the larger batch is not better per game |
| A4 | Offline gradient-variance probe on ~200 stored mid-run states: GAE, critic baseline, prefix-replay forks | offline | fork gradients are not lower-variance per core-s than GAE; then drop V4 |

## (B) Evidence on a run-aware Silver leaf

- **KataGo's utility** (Wu 2019, arXiv 1902.10565; Verified 3-0 and 2-1):
  `u = u_win + c_score · (2/π) · arctan((x − x0) / b)`.
  - x0 is recentred each search on the net's predicted mean score at the root.
  - The term is an expectation over a predicted score distribution (an implementation detail, not in the paper).
  - c_score is hand-set, 0.5 then 0.4.
  - The saturating shape rewards likely small gains and does not chase unlikely large ones.
  - In KataGo the term serves analysis and handicap play more than strength, so the transfer is about form, not
    measured gain.
- **No source supports V(s) as a raw inner-planner leaf.** Our own record agrees: the learned leaf heads (§655,
  §656, §664, §675) drew fights out and were worse in elites and bosses.
- **The finite-difference "exchange rate" idea is already partly tested.** The research synthesis proposed V-derived
  per-fight prices (HP, potion, max HP, gold), shrunk toward the formula and sign-clipped. §721 did that check with
  V_A4 and V_H:
  - potions came out within 2-3 HP of the formula's 11;
  - max HP had the wrong sign;
  - 1-3 HP steps were mostly unresolved.
  A PPO value head trained on far more games could pass where V_A4 failed, but the §736 learning curve (R² ≈ 0.33 at
  10⁵ entries) says level accuracy improves slowly. Whether paired finite differences cancel enough of the level
  error is open.
- **What has worked is targeted.** §724 priced one state variable Silver ignores, the Incense Burner phase, and won
  +5.9 pp. The combat-search architecture page lists other unpriced fight-end state: counter relics (Pen Nib,
  Nunchaku, Sundial, Ink Bottle, Happy Flower), Ritual Dagger growth, Lesson Learned and Genetic Algorithm upgrades,
  and curses added.

### Ranked experiments for (B)

| # | Experiment | Cost class | Falsified if |
| ---: | --- | --- | --- |
| B1 | Targeted terms first: for each unpriced fight-end variable, a causal paired probe as in §723 (force the variable, play on) to measure its Heart-kill price; price only those that clear their CI, in Silver's leaf as in §724 | offline probes + fight-level gate | no variable beyond Incense shows a price outside its CI |
| B2 | When the PPO critic exists: §721's teacher check repeated on it; heart1's critic FAILED (2026-11-02, §747), rerun on our own critic. Checks: signs, SE of the 1-HP price ≤ ⅓ of the formula's, max HP ≥ 0 | offline | it fails the same checks as V_A4/V_H |
| B3 | Only if B2 passes: shrunk, clipped V-prices set at elite/boss fight start vs the formula, paired fight-level gate, then a run A/B | gate | SPRT NOT_WORSE/WORSE |
| B4 | KataGo-style bounded arctan term on fight-end HP, recentred on the root's expected HP, weight grid {0.1, 0.25, 0.5} | fight-level gate | no weight beats the formula |

## Refuted in this round (do not cite)

- CRN across a group "removes between-schedule variance exactly" with an exact replicate saving (1-2).
- "MC variance under luck is best handled by sample volume" (actor-scaling claim, 1-2).
- "An online critic beats an offline-pretrained critic as initialisation" (1-2). Whether to warm-start the critic
  from our supervised value models stays open.
- "PORL needs a competent prior" (1-2).

## Sources

- VinePPO: https://arxiv.org/abs/2410.01679
- DouZero: https://arxiv.org/abs/2106.06135
- PORL: https://arxiv.org/html/2505.16856v1
- Paired rollouts ("Luck Is Not Skill", preprint): https://arxiv.org/pdf/2609.24144
- KataGo: https://arxiv.org/pdf/1902.10565

## Relationships

- [A20 PPO plan](a20-ppo-plan.md): the plan this page critiques.
- [Search and learned value](search-and-value-literature.md) and
  [external evidence](ooc/external-evidence-and-ideas.md): the earlier literature rounds.
- [One-year roadmap](one-year-roadmap.md): phase 4 (run-aware combat leaf).

## Open questions

- Does a PPO critic trained on ~10⁶ A20 games resolve 1-HP prices that V_A4 could not?
- Does per-game coordinated exploration discover multi-pick builds without §640's cost?
- Is a privileged critic's bias acceptable in single-agent stochastic card RL?
