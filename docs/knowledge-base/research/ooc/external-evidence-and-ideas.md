# External evidence and candidate ideas for the A20 OOC plateau

Last verified: 2026-10-26 (web research with 3-vote adversarial claim verification, plus read-only checks of this
repository at `8cce22b`; follow-up status checked against main at `93cef2b` on 2026-10-30).

## Purpose / research question

Why has the A20 Ironclad Heart-kill rate plateaued at about 21-25%, and which ideas from published StS bots,
expert-human play and the planning/RL literature are worth testing for the out-of-combat (OOC) model? This page holds
the external evidence and the ranked candidate list. Experiments that test an idea belong in the ledger; this page
records only what the outside evidence says and how it maps onto the project.

Evidence status labels:
- **Verified**: the claim survived a 3-vote adversarial check against its primary source (16 of 25 checked claims did).
- **Extracted**: taken from a primary source with a quote, but not vote-checked.
- **Inference**: reasoning on this page, not stated by a source.

## Current conclusion

- The bot sits at the published frontier for agents that play combat with fair information. The headroom against
  expert humans is real (46-65% Heart kills), and it lies in Acts 2-4, not Act 1.
- The OOC skill is essentially heart1's. Search adds about 2 pp, and every learned attempt to go beyond the prior has
  stalled on signal-to-noise: decision-level effects of about 1 pp, a ~4 pp paired-A/B detection limit, and a leaf
  whose errors look systematic rather than random.
- No verified evidence says larger or equivariant networks, graph map encoders, Stochastic MuZero or distributional
  value heads would lift this bot. New information sources and structural fixes rank higher.

## Follow-up status (2026-10-30)

Each candidate below got its own thread on 2026-10-26. All ten are now tested. Status on main at `93cef2b`:

| # | Idea | Status |
| --- | --- | --- |
| 1 | Key rules A/B | Done, §691: flexible keys beat the rigid rules by +6.1 pp Heart kills [+3.4, +8.6] with student_sel alone (KEYS_EXPLAIN); flexible keys are the default since [ADR-0063](../../../../decisions/0063-flexible-heart-keys-default.md) |
| 2 | Expert audit | Done, §688: elite dose matches experts; the bot rests 3× as often, skips 2.4× less and loses 1.4-3× more HP per elite/boss fight; deviations come from the prior |
| 3 | Expert replay | Done, §694: replaying Baalorlord's OOC decisions on his seeds leaves the Heart rate unchanged, −2.1 pp [−7.9, +3.6] (NOT_SHOWN, 329 seeds); per-type ablations not run |
| 4 | Elite dose at map roots | STOP, §686: no elite deficit; declined elites worth ≤ ~1-2 pp per flipped root |
| 5 | Boss-relic forks | Stage A done, §690: relic choice matters (τ ≈ 11 pp), but student_sel already picks the table's best relic at 74% of roots and a context-free table override loses; STOP before Stage B (Philipp) |
| 6 | AIVAT | Done, §697 + §698: unbiased with fresh fight replays, but the pilot cut the paired SD only to 0.80× (projected 0.71×); almost all of it comes from the Heart; no recommendation |
| 7 | Expert-decision ranker | Done, §696: student_sel fine-tuned toward Baalorlord's choices, −0.7 pp [−3.4, +2.0] (NOT_SHOWN) |
| 8 | HP into the Heart | Done, §687: the policy rests when it can; forced pre-boss Ruby costs ≤ 0.65 pp; no run |
| 9 | Bounded Q tilt | Done, §689 (offline) + §693: Gumbel root with the Muesli Q cap at map roots, 25.2% vs 27.7% Heart kills (NOT_SHOWN) |
| 10 | P300 cross-check | Done, §692: known RNG does not inflate P300's card values; its top-5 cards beat its bottom-5 by +6.0 pp [+3.8, +8.3] under fair Silver too |

Only idea 1 moved the Heart rate. Ideas 3 and 7 point away from OOC choices, and §688's HP-loss finding started a
combat-gap line: §701 (observational: 2-3× more HP lost at matched entry HP and deck size with near-starter decks), §711 (matched expert fight states:
+2.6 HP per acts-1-2 elite/boss fight [+2.0, +3.3], inconclusive; act-2 elites +5.4, Automaton +9.8, Awakened One
+10.7), §716 (act-2 elites are not budget-limited) and §718 (bosses at flat 40k: −0.25 HP, inconclusive).

The audit (§688) refutes the "fewer elites" reading under [Where the gap is](#where-the-gap-is) and corrects two
expert-profile numbers below.

## Benchmark position

| Agent | A20 Ironclad Heart kills | Comparable to this bot? | Status |
| --- | --- | --- | --- |
| This bot, recent campaigns (§621, §661, §683) | 21-25% | — | ledger |
| heart1 (silverbot), fair expectimax combat, 10k iterations | 18.6% ± 2.4% (n = 1,000) | Yes; it is the prior's teacher | Verified |
| GPT-6.1 Sol, Epoch SpireClimb (vision harness, wiki only) | Ironclad 27% (4/15); 20% over 4 characters | Too few runs (exact 90% CI ~10-51%) | Verified |
| destire-mio/sts-ironclad-agent ("P300") | ~50%, self-reported | No: combat search runs on the true RNG and draw order | Verified |
| Baalorlord, 676 auto-logged runs | 62.9% | Real game, human combat; includes abandons | Verified |
| SpireBench expert samples (panacea108, vmService, cheg0) | 65% / 58% / 46% (n ≈ 50 each) | Player-selected blocks | Verified (2-1) |
| XecnaR since 2022 (sts-stats tracker) | ~84% | One player; tracker unvalidated | Extracted |
| Mega Crit 2020 telemetry, 206,082 A20 Ironclad runs | 3.5% | Population, weaker than the bot | Verified |

P300's combat (`fightsim.cpp::resolve_combat4r`, `BattleScumSearcher2` copying the root RNG on every simulation; live
play imports the six combat RNG streams and the draw pile) is the known-RNG regime of
[ADR-0002](../../../../decisions/0002-fair-and-known-rng-are-separate-regimes.md). Its own history says "the
teacher effectively sees the future". Its ~50% is therefore not a fair-information target.

## Where the gap is

Deaths as a share of runs reaching each act. Bot: §661 arm A, 1,024 seeds (deaths 88 / 235 / 284 / 179, 238 kills).
Expert: Baalorlord's 676 Ironclad runs (77 / 81 / 46 / 47 deaths, 425 kills; Verified).

| Act | Bot | Baalorlord |
| --- | ---: | ---: |
| 1 | 8.6% | 11.4% |
| 2 | 25.1% | 13.5% |
| 3 | 40.5% | 8.9% |
| 4 | 42.9% | 10.0% |

- Reaching Act 4: bot ~40%, expert ~70%. Converting an arrival into a kill: bot 53-61%, expert 81-92%. Expert
  conversion at the bot's arrival rate would give ~36% kills, and expert arrival at the bot's conversion ~40%, so the
  two gaps are of similar size (Inference).
- Expert losses: 52% on boss floors (the Heart is the single most frequent killer, 39 of 251), 31% to elites
  (Slavers 17, 3 Sentries 13, Gremlin Nob 9, Shield and Spear 8) (Verified).
- **Inference:** the bot survives Act 1 at expert level and then falls apart, worst in Act 3. That fits a run that
  under-invests early (fewer elites, weaker deck) as well as the rigid key rules below. §688 and §686 later found no
  elite deficit; the key rules explained +6.1 pp (§691, idea 1).

## Expert-play reference profile

For audits and rule priors. Baalorlord's 100 most recent Ironclad runs (Apr 2025 to Mar 2026, 65 wins) unless noted.

- Elites (Verified): winning runs fight a median of 8 elites in Acts 1-3 (IQR 7-9). Act 1 median 3 (§688: 9
  winners fought only one); Act 2 mean 2.4; Act 3 mean 2.5.
- Telemetry routes (Verified, associations only; the logs do not record which elites the map offered): within a
  play session (8,745 sessions) each Act-1 elite multiplies the odds of clearing Act 2 by 1.38 (1.34-1.43) and each
  Act-1 rest by 0.85 (0.81-0.89); within the four expert streamers 1.68 and 0.64. Act-2 clear rate is 21/25/32/40/50%
  for 0 to 4+ Act-1 elites. A route profile explains only 17-19% of the streamers' advantage. The "winners take more
  path risk" result (arXiv 2504.03918) is plausibly a survivorship artifact: Act 1, the only act every run enters,
  shows no difference.
- Campfires (Extracted): 67.7% smith, 17.9% rest, 9.9% Ruby, 4.5% other. §688 recomputed 72% smith / 13% rest over
  all 676 runs (acts 1-3). Streamers rest at 9% of Act-1 campfires
  (population 23%) and never at ≥ 70% HP.
- Cards and deck (Extracted): 27.8% of card rewards skipped; final deck median 34 (IQR 30-36) after a median of 4
  removals. Removals go to Strikes (median 0 of 5 left); Defends are kept (median 4 of 4).
- Act-4 entry (Extracted): wins log a median 93.8% of max HP entering Act 4 (8 of 65 below 85%).
- Guides (blogs, Extracted): front-loaded damage first (Gremlin Nob needs ~90 damage in 3 turns), then scaling and
  draw. A Heart deck needs ~100 block over 3 turns, enough draw to play through its status cards, and ~200 damage
  per turn for at least 4 turns. A 4th-energy boss relic is called nearly required on Ironclad. Strike-before-Defend
  removal and taking Corruption are disputed among experts, which makes them good simulator A/B candidates.

## Why the current methods plateau

1. **The prior carries the bot.** Search changes ~6.5% of searched decisions (§661 arm A, §635) and adds +2.4 pp
   (§569). heart1 or student C as tree prior beat V4 by +23-25 pp of Act-3 clears (§486, §488).
2. **Q-led root selection is structurally fragile.** Taking the argmax of noisy estimates is biased toward the
   luckiest option (optimizer's curse, Smith & Winkler 2006; Extracted). Expected disappointment is 0.85 SD with 3
   equal options. Common random numbers should reduce it (0.73 SD falls to 0.41 SD at error correlation 0.5), so the
   CRN particle search's −17 pp (§680) points to leaf bias, not noise. Backgammon rollout practice says the same:
   truncated rollouts carry a systematic error that more trials cannot remove, and it is worst between structurally
   different plays (Extracted).
   **Inference:** rollout3 charges an elite's HP and death cost inside its 3-fight window, while most of the relic
   payoff falls outside it.
3. **The §635 Gumbel loss is partly an implementation artifact.** `OocMctsPlanner.cpp::gumbelSigma` min-max
   normalizes root Q over the visited actions and multiplies by `(gumbelCVisit + max visits) * gumbelCScale`, with
   defaults 50 and 1.0 (`OocMctsPlanner.h`). mctx defaults to `value_scale=0.1` (Verified). At §635's 2,048
   simulations the spread was ~500 logits, so any noise-sized gap beats a 0.99 prior (~4.6 logits). §635 therefore
   tested "argmax of noisy Q", not a prior-anchored Gumbel root. The Gumbel paper itself reports that a large
   `c_scale` "neglects the logits" on a partially observable game (Verified 2-1).
4. **Search-derived policy targets ≈ visit counts at this budget.** Grill et al. (ICML 2020): the regularized target
   beats visit counts mainly at very low budgets (Nsim = 5) and is comparable from Nsim ≈ 24 (Verified; a related
   reading of the same ablation was refuted). This fits AZ generations changing ~3% of decisions for ~0 pp.
5. **Outcome labels cannot rank siblings.** A return decomposes exactly into the agent's advantages plus the luck of
   nature at each chance transition (DAE, arXiv 2402.12874; Extracted). With sibling outcome rho 0.49 (§685), luck
   dominates. The literature's remedies subtract estimated luck: luck-term modelling (off-policy DAE), baselines
   conditioned on action-independent hindsight variables (CCA, arXiv 2011.09464, with the leakage caveat that
   variables downstream of the choice must not be used), and AIVAT-style control variates. None of these is
   quantified for StS.
6. **Count-level run-state features predict poorly.** An Act-1 boss model on HP, max HP, relics, deck size and
   upgrades has McFadden R² 0.05 (SpireBench; Extracted). Whole-run AUC on end-of-run features mostly measures
   progress, and an additive deck model ranks two candidates the same in every deck (hobbyist hypergraph study;
   Extracted, weak). Judge value models by within-decision sibling ranking, as §641-§649 and §685 already do.
7. **Statistical power.** Plausible single-change effects (≲ 1-3 pp) sit below the ~4 pp paired-A/B limit.
   Published comparisons are worse: n = 15 per character cannot resolve differences under ~20 pp.

## Candidate ideas, ranked

Each idea needs its own pre-registration, the seed-run guard and explicit authorization before any seeds run.

1. **Attribute the 17.6% → ~24% jump to key rules (paired A/B).** §566 (main defaults, rigid keys) scored 17.6%
   [14.5, 21.1]. One day later §569 scored 23.4% with student_sel alone and 25.8% with search, under flexible keys
   (`STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask`) plus parity fixes and opt-in fix flags. The
   executable still defaults to `first` for all three (`RunGoal.cpp`): Sapphire at the first chest (gives up that
   relic), Ruby at the first Act-3 campfire at any HP, and Emerald forced in Act 3 if missing. Every recent campaign
   overrides these defaults. Toggle only the key flags on the student_sel-only config (cheap); add `act3` and `hp`
   arms if affordable. If the key rules explain much of the jump, change the default and treat key timing as a
   learned decision.
2. **Zero-seed audit of the bot against the expert profile.** Use the existing `az-gen*-data` and
   `heart-outcome-data` branches. Measure elites per act, rest vs smith by HP, skip rate by act, deck size, removal
   targets, key timing (how often Act 3 starts without Emerald) and death encounter by act. The ledger has no such
   audit. This is the cheapest answer to "what exactly is wrong" in game terms.
3. **Expert-OOC replay on expert seeds (Inference; design, no source).** Expert `.run` files carry their seeds
   (Baalorlord's Spireblight logs, the MaT1g3R/Slay-the-Spire-data archive). Replay each expert's path, picks,
   removals, boss relics and campfires in the simulator with Silver combat, and fall back to student_sel when a
   choice is infeasible. Ablate by decision type. Compared with student_sel on the same seeds, this splits the
   expert gap into OOC choices vs combat and ranks decision types by leverage. First measure how often the
   simulator reproduces the logged offers. Unverified: the exact `.run` fields and replay fidelity. Maps can be
   regenerated from seeds (arXiv 2504.03918 did it with sts_map_oracle).
4. **Elite dose at map roots, only if audit 2 shows a deficit.** *Stopped: no deficit (§686, §688).* Run an exploratory slope of the Heart-kill
   difference on the elite-count difference over §685's first-divergence pairs (its TEST split is consumed, so this
   is exploratory only). Then pre-register a paired A/B of an HP-gated tilt toward elite-reaching children at map
   roots, the only screens where search pays (§683). Falsified if the bot already matches the expert dose or the
   slope is ≤ 0. The associations bound the effect from above; the effect could be negative.
5. **Boss-relic whole-game forks (#856).** P300's one replicated learned gain was a narrow Act-1 boss-relic scorer
   (22 relics + skip) trained on matched complete continuations: 83 → 112 and 92 → 121 Heart kills per 1,024 on two
   cohorts (+40/−11 and +47/−18 discordant pairs; Extracted from its docs; known-RNG combat). Its broader relic and
   card heads did not transfer, and its per-card simulation teacher had score noise 2-6× the option differences, as
   here. Few decisions with large effects can be resolved where single cards cannot (§684).
6. **Lower the detection limit with luck-adjusted evaluation.** AIVAT (AAAI 2018) adds zero-mean corrections at every
   chance event and known-policy decision using any fixed value function. The value function's quality changes only
   the variance, never the bias. Results (Extracted): DeepStack's per-hand SD cut by 85% (~44× fewer games), and a
   single win/loss per match had its 95% CI shrink from ±0.20 to ±0.018 over 28 matches. A deterministic argmax
   policy leaves only chance-node terms.
   - The simulator knows its offer, event and encounter distributions.
   - For fights, the correction stays unbiased only with an independent re-simulation; a CTM expectation would add
     bias.
   - The value function must not be fit on the evaluation seeds.
   - Start zero-seed: estimate the variance reduction on the 1,800-run heart-outcome corpus.
   - Related: a surrogate index of predicted Heart kills from act-boundary states (Athey et al., NBER 2019;
     Extracted). Its validity breaks if the policy optimizes the index's own model (Goodhart).
7. **Expert-decision ranker.** Contextual preference ranking (arXiv 2105.11864, Verified for the method) embeds the
   deck and each candidate in one space and trains on pick-vs-sibling contrasts. A 2024 follow-up on 17lands data
   (arXiv 2407.05898) reports ~66-69% top-1 with a listwise InfoNCE loss slightly ahead. The evidence covers human-pick
   imitation in MTG, not win rate. The project's RankNet sibling loss on model labels (§641-§649) did not play better
   (§661), so the new element here is the label source. First measure where student_sel disagrees with experts by
   screen; blend only there; then run a paired A/B. Expert data is small: Inference ~15-20k card decisions.
8. **HP into the Heart.** About −0.3 pp Heart survival per entry HP (§684: `hp:-16` −4.7 pp, SE 1.9). P300 (known-RNG)
   reports a Heart rate of 68 / 57.5 / 41.8% at full / 75% / 50% HP. Single upgrades are unresolvable. A rest
   restoring ~24 HP is worth roughly +7 pp at the Heart (Inference). Audit late Act-3 and Act-4 campfire choices
   against HP, including the Ruby rule spending a campfire. Test a rest rule with an `act4replay`-style stage replay
   before any run-level A/B.
9. **Bounded Q tilt (protective).** If root Q is used at all, z-score it by the particle SE and clip it, Muesli
   style. The CMPO target π ∝ π_prior · exp(clip(adv, −c, c)) moves at most tanh(c/2) in total variation (0.46 at
   c = 1) for any number of actions (Verified). Alternatively rerun the Gumbel root with `gumbelCScale` ≤ 0.1, as
   §635's RESULT.md suggests. Expect 0 to +1 pp. Its value is a safe channel for a better value signal later. Do not
   sample acted moves from the regularized policy (exploration cost ~5 pp, §640).
10. **Known-RNG cross-check of P300's card values.** P300's Heart table (known-RNG, 8k sims) gives Feel No Pain
    +13.5 pp, Demon Form +10.2, Impervious +10.2 and removing a Strike +10.0. §684 under fair Silver measured
    Impervious at 0.0 pp (SE 3.9), about 2.2 SE apart (Inference across studies). On §684's Heart-entry decks, run
    those four keys under fair Silver and known-RNG search with shared seeds. Predicted if clairvoyance drives P300's
    values: known-RNG ≥ +8 pp on at least 3 keys while fair stays ≤ +3 pp. This does not raise the fair rate; it
    prevents porting values tuned under the wrong regime.

### Deprioritized

- **Architecture upgrades** (bigger/equivariant transformers, graph map nets, Stochastic MuZero, distributional
  heads): no verified supporting evidence. §678 found the mirror flips are near-ties.
- **Imitating the 2020 telemetry:** the population kills the Heart in 3.5% of runs; even runs after an earlier Heart
  kill reach only 15.8%. The telemetry is useful for counterfactual map analysis, not for imitation.
- **More AZ generations as they are.** If continued, use KataGo's design (arXiv 1902.10565; Extracted): noise only
  on recorded full-search turns, forced playouts with policy-target pruning, and playout cap randomization (already
  present as the 25% full-budget roots). KataGo also found auxiliary ownership/score targets were its largest
  single ablation (~1.65× compute), but §641 saw no offline gain from auxiliary heads here.
- **LLM priors:** 4/15 is statistically indistinguishable from the bot.

## Rejected claims

The 3-vote check refuted these; do not rely on them:
- heart1's internals as summarized: it does encode the map DAG (`map_dag_features`), and the summarized two-stage
  training and reward-shaping details are wrong.
- P300's detailed win counts and student-network details as summarized.
- The Grill tracking-theorem inference for this bot, and "Gumbel `gumbel_scale=0` explains §635".
- The Jialeiv REINFORCE A0 agent's win-rate claims as summarized.
- The "unmodded" description of Baalorlord's dataset; the numbers themselves reproduced.
- The contextual-preference-ranking headline comparison against NNetBot.

## Coverage gaps

No claims survived on Bottled AI, spirecomm, Monster Train, Hearthstone Arena, Dominion or Legends of Code and Magic
drafting, nor on ISMCTS, TD(λ), distributional RL, potential-based shaping, CUPED or sequential testing. P300,
SpireBench and the LLM results date from Sept-Oct 2026 and may change.

## Sources

- heart1 / silverbot: https://github.com/daniel-ziegler/sts_lightspeed
- P300: https://github.com/destire-mio/sts-ironclad-agent
- Epoch SpireClimb: https://epoch.ai/publications/ai-systems-are-improving-rapidly-at-slay-the-spire-and-its-sequel
- SpireBench (Lowe & Keemink, preprint): https://arxiv.org/html/2610.12596v1
- Baalorlord run logs: https://baalorlord.tv/runs
- Path entropy in human runs (Bazzaz & Cooper): https://arxiv.org/abs/2504.03918
- Expert guides: https://steamcommunity.com/sharedfiles/filedetails/?id=2429404117,
  https://note.com/fortune2_kyu/n/nff150bf28cfa
- MCTS as regularized policy optimization (Grill et al.): https://arxiv.org/abs/2007.12509
- Gumbel MuZero (Danihelka et al.): https://iclr.cc/virtual/2022/poster/6418; mctx: https://github.com/google-deepmind/mctx
- Muesli (Hessel et al.): https://arxiv.org/abs/2104.06159
- Optimizer's curse (Smith & Winkler): https://scholars.duke.edu/publication/798952
- AIVAT (Burch et al.): https://ojs.aaai.org/index.php/AAAI/article/view/11481
- KataGo (Wu): https://arxiv.org/abs/1902.10565
- Counterfactual credit assignment (Mesnard et al.): https://arxiv.org/abs/2011.09464
- Off-policy direct advantage estimation: https://arxiv.org/abs/2402.12874
- Contextual preference ranking: https://arxiv.org/abs/2105.11864; follow-up https://arxiv.org/abs/2407.05898

## Relationships

- [strategic-policy.md](strategic-policy.md): the learned OOC policy lines these ideas extend.
- [current-research.md](../../evaluation/current-research.md): active routing; promote an idea there when it is
  scheduled.
- [current-baselines.md](../../evaluation/current-baselines.md): the internal reference numbers quoted above.

## Open questions

- ~~Does the bot take fewer elites than experts?~~ Answered: no (§686, §688). Whether more elite exposure causes
  better Act 2-4 outcomes for a Silver-strength fighter stays open.
- ~~How much of the 17.6% → ~24% jump do the key rules explain?~~ Answered: +6.1 pp of it (§691).
- ~~Can expert `.run` files be replayed faithfully enough to split the expert gap into OOC and combat parts?~~
  Answered: yes for 329 vanilla runs; the expert's OOC choices do not lift the bot (§694), and on matched fight
  states Silver loses more HP from act 2 on (§711).
- ~~How much variance would AIVAT-style chance corrections remove from a paired A20 A/B?~~ Measured: paired SD
  0.80× in the §698 pilot, mostly from the Heart.
