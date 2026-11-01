# Search and learned value for Heart kills

Last verified: 2026-11-01 against main 6c96c25 (ledger through §728). Literature review and read-only code/record
checks; no gameplay seeds were run.

## Purpose / research question

What does the literature on search plus learned value in long-horizon stochastic games (AlphaZero, MuZero and Stochastic
MuZero, Gumbel roots, chance-node and imperfect-information MCTS, roguelike and deckbuilder agents, value learning under
weak signal, learned simulators under shift, evaluation statistics) imply for four open problems of the A20 Ironclad
agent, and which ideas should be tried first? The problems: (1) a general run-level value model that sees interactions
(Incense Burner phase, relic × encounter) without hand rules; (2) CTM combat-model pessimism on rollout-built states;
(3) Heart and boss fight losses; (4) the noisy-signal / gate-power bottleneck.

Budget: ~200 CPU cores (≈0.9M core-h/yr at the roadmap's 50% utilisation assumption), one RTX 3060 Ti 8 GB, 32 GB RAM,
12 months. Cost anchors: production game ~826 core-s (0.23 core-h; §727 arm A mean over 1,536 games, via the #925 roadmap); paired SD per pair ~0.44; 1,024 pairs ±2.6 pp (~470
core-h); real Silver fight ~5 s at 200 sims, ~14 s at 1,000 sims; production Heart fight ~4 min.

This page extends [External evidence and ideas](ooc/external-evidence-and-ideas.md) (ten ideas, all tested §686-§698)
and the draft one-year roadmap (`one-year-roadmap.md`, PR #925, X1-X7; X1 is running) without repeating them; each idea
states its overlap. Every seed-driving step needs its own pre-registration, the seed-run guard and Philipp's
authorization.

Labels follow the source notes and are never upgraded. **Verified**: read in the primary source this round (one read,
not the earlier review's 3-vote check; it means the source was read, not that the result was reproduced). **Extracted**: abstract, secondary source or summariser pass. **Recall**:
background knowledge, not re-read (the evaluation note's "Background" is filed here). **Inference**: reasoning or
arithmetic, including small simulations of the statistics. Repository facts carry § numbers or file paths; code facts
are read-only checks at 6c96c25.

## Current conclusion

- The literature and the project's record agree. With an exact simulator and a strong prior, extra decision-time search
  adds little, and a learned model inside search adds error: search at evaluation gave a median of about +2 pp with a
  simulator and −4.7 pp at 625 simulations with a learned model (Hamrick et al.; Verified). What transfers is not a new
  search algorithm but three things: **pricing the state a sub-search ignores** (§724's Incense term is the template: +5.9 pp per
  Incense-holding S&S entry at research budget, ≈ +0.3 pp per run), **better chance sampling and playout balance in long fights**, and **cheaper, sequential, better-coupled
  evaluation**.
- The top of the ranking is zero- or near-zero-seed work that decides where 10^3-10^5 core-h go: an SPRT replay on
  recorded campaigns, a control-arm byte-identity smoke (~15 core-h), a re-cut of §709 by imagined-fight depth, three
  value-model gate checks, and a map-root value-of-computation audit from logged decision rows. Together they cost < ~20
  core-h.
- Problem 1: an aggregate BCE gate cannot see an Incense-size interaction (≈0.0015 BCE against a CV half-width of
  ≈0.002; Inference), and outcome-only deck and run models hit Bernoulli-noise ceilings (MTG deck strength: ρ ≈ 0.23
  with ~120k drafts; Verified). Interactions should be found by paired fork probes, priced at fight level and composed
  (the rollout3 structure), not by larger architectures.
- Problem 2: CTM pessimism is most likely a small per-fight bias that compounds over long rollouts (hypothesis; rank 3
  tests it) (MBPO's error term linear in
  rollout length, Talvitie's self-generated inputs; Extracted). It binds full-rollout leaves, referees and CTM-rollout
  labels, not rollout3 map decisions (§709). The "3× act-2/3 boss deaths" figure rests on 2/38 and 5/75 observed deaths
  from 8 roots and is not an established error.
- Problem 3: the best-supported Heart and boss levers are (a) unpriced run state in Silver's fight-end score (a
  code-verified list: counter relics, Ritual Dagger, Lesson Learned, curses), (b) Silver's visit-proportional re-picking
  at the chance cap (§706: ~40 effective of ~240 outcomes), with public-equivalence merging (Hearthstone draw bucketing
  60.1% → 72.3%; Verified), and (c) a balance-trained or online-adapted boss playout (simulation balancing 1367 vs 1159
  Elo; Verified). Each is worth 0 to +2 pp (Inference). Flat budget raises are not (§716, §718).
- Problem 4: cost per pair dominates. Control-arm reuse halves it and, in a 16-candidate simulation, raised the expected
  adopted gain from 3.71 to 5.89 pp at equal core-h. An SPRT with futility saves ≈45-48% of gate compute (both Inference
  (simulation)). Keyed run-level RNG for evaluation is a 1.2-1.7× candidate pending a zero-seed check. CUPED on
  pre-divergence covariates (≤ 1-2%) and importance-sampling OPE from logs (logging is deterministic) should be dropped.
- Drop: Stochastic MuZero-style learned dynamics (it only matched AlphaZero with a perfect simulator at equal
  simulations; Verified), distributional value heads for a Bernoulli objective, ReBeL / Student-of-Games machinery,
  ISMCTS as a fix for a clairvoyance Silver does not have, and further root-allocation schemes (§635, §693, §712).

## Ranked ideas

Ranked by expected Heart-kill gain per unit compute. Zero-seed checks rank high although their direct gain is ~0 pp,
because each decides whether a larger spend is worth it. Gain ranges are Inference (planning ranges, not forecasts); so
are compute figures for production-budget fight tests, which are scaled from §724 (70 CPU-h for 4,736 S&S→Heart units at
research budget) and the ~4-min production Heart fight. Problem column: 1 = general value with interactions, 2 = CTM
pessimism, 3 = Heart/boss losses, 4 = signal and gate power.

| Rank | Idea | Prob. | Evidence (label) | Expected Heart-kill gain | Compute | Cheapest falsifying experiment and decision rule | Overlap with existing work |
|---|---|---|---|---|---|---|---|
| 1 | Sequential gates: gainer SPRT [0, +2 pp] and non-regression SPRT [−1.5, 0 pp], α = β = 0.05, hard cap = inconclusive | 4 | Simulated ASN 52-54% of fixed n at H0 and H1 (Inference (simulation)); chess pentanomial pairs need 1,809 vs 2,191 games (Verified) | 0 pp direct; ≈45-50k core-h/yr saved (≈5% of budget) | ~0 (minutes of CPU) | Replay the stopping rule in pre-registered seed order on §661, §676, §683, §691, §693, §724, §727 (§724: cluster its 4 replicates per state; §683: one pairwise contrast per arm vs control). Drop if the verdict flips in > 1 of 7 or the ASN saving is < 25% | X4 sizes fixed gates; benchmark-protocol open question on alpha spending. New: early stopping with futility |
| 2 | Control-arm reuse: play the default once on a frozen, bit-reproducible seed bank; keep a held-out confirmation bank | 4 | 16-candidate simulation: adopted gain 3.71 → 5.89 pp at equal core-h (Inference (simulation)); cost per pair 0.459 → 0.23 core-h | 0 pp direct; +50-60% expected adopted gain | ~15 core-h smoke | Re-run 32 recorded control seeds of the current default. Any non-identical record → no reuse until determinism is fixed | Roadmap phase 2 (frozen 7,000-pair bank). New: reusing arm A; holdout rotation |
| 3 | Re-cut §709's raw combat rows by imagined-fight index × act; estimate the CTM-vs-Silver outcome correlation ρ from its paired arms | 2 | Diagnostic re-cut: pooled boss/Act-4 fights at index ≥ 10 forecast 18.2% vs observed 10.2% (n = 147), index 3-9 21.1% vs 23.3% (n = 60), but depth is confounded with act (acts 2-3 over-forecast at both depths) (repo; low confidence); MBPO error linear in k (Extracted) | 0 pp direct; gates all CTM repair (rank 13) | 0 core-h (existing share archive) | Boss over-prediction ≥ 2× already at index 0-1 → depth compounding falsified (look for covariate or teacher shift). No trend over indices 0-3 → the long-rollout claim rests on the 8-root diagnostic alone. ρ < 0.5 → PPI/MFMC only as debiasers | §709, §663. New |
| 4 | Price unpriced run state in Silver's fight-end score: counter relics (Pen Nib, Nunchaku, Sundial, Ink Bottle, Happy Flower), Ritual Dagger, Lesson Learned, curses and cards added | 3 (1) | §724 +5.9 pp [+4.1, +7.8] per Incense-holding S&S entry (≈13% of Heart entries, ≈ +0.3 pp per run) from one such term; §723 phase effect +12.0 pp; terminal value should be the outer value at sub-game exit (POLO, ReBeL; Recall) | Σ prevalence × per-state effect: ≈ +0.1-0.5 pp per item that passes (Incense ≈ +0.3), 0 to ~+1.5 pp in total | Prevalence count 0; per item a §723-style probe, ~70 core-h at research budget, ~300-400 at production budget | Count each item in Heart-reaching runs; drop items < 2%. Per item, a forced-state probe on the next fight; drop if its CI includes 0 or the term changes < 1% of root picks. Survivors get a §724-style gate | Roadmap phase 4 waits for a PPO value head; §724's production check is pending. New: hand-priced terms that need no value head |
| 5 | Value-model gate checks: Incense-holder subgroup BCE; 4-point V_A4 learning curve; Bernoulli label-noise ceiling for sibling ranking | 1 | Interaction gain ≈ π·Δ²/(2p(1−p)) ≈ 0.0015 BCE (Inference); MTG ceiling ρ ≈ 0.23 (Verified); §722: BCE 0.538 → 0.516 from 25% to 100% of seeds | 0 pp direct; decides a 10^5-game capture (~23k core-h) | ~0 (CPU-h) | Extrapolated R² < 0.33 at 10^5 entries → no outcome-only capture. Best head within ~0.05 of the simulated ceiling → stop outcome-label value work. Subgroup gain visible but aggregate flat → replace the BCE gate by targeted probes | §722, §700. New |
| 6 | Map-root value-of-computation audit, then a non-regression SPRT of 1,024 vs 4,096 map sims | 4 (3) | Expected computations ≤ VPI/c; VOI root 64% vs UCT in 9×9 Go (Verified); learned model at 625 sims −4.7 pp (Verified); §710: departures at 2-8% of roots, not better in play | 0 pp; map search is ≈80% of game CPU, so a 2-3× cut makes gates ~1.5-2× cheaper | 0 for the audit (decision rows log prior, visits, q and checkpoints); ~470 core-h SPRT | Tabulate sims spent and decision changes by prior-top bin. If roots with prior ≥ 0.98 change > ~3% of decisions or use little CPU, drop. Else SPRT [−1.5, 0] | ADR-0053 learned stop. New |
| 7 | Keyed run-level RNG (card, relic, event, potion streams keyed by seed × floor × room) as an evaluation-only mode | 4 | Run-level streams advance sequentially; combat streams reseed per floor (code read); §685 whole-game sibling ρ 0.49 (§684's 0.68 is a fight-level Heart CRN correlation, not comparable); keyed rollout streams alone 0.638× (§703: WEAK) | 0 pp; 1.2-1.7× effective seeds if post-divergence ρ reaches 0.65-0.70 (an untested target) | 0 for the check; engineering | In §685's 8,510 first-divergence pairs, compare outcome ρ for pairs whose next offers coincide vs not. Drop if the gap is < 0.1 | None; whole-game analogue of §703 |
| 8 | Optimizer's-curse shrinkage: any value-led override uses α·ΔV with α = out-of-sample slope per screen | 1, 4 | Disappointment 0.85 SD with 3 equal options; posterior-mean remedy (Verified); §715 slope 0.16-0.18; §727 −15.0 pp | 0 pp (protective; required before V decides anything) | 0 | On §727 choice logs: if overrides with α·ΔV > 1 pp still lose as much per choice as the rest, the head's sign is wrong, not its scale | External idea 9 (§689/§693). New: empirical-Bayes α. Checked 2026-11-01 (ledger, value chooser shrinkage): only 7.8% of §727 overrides survive α 0.17 / 1 pp; sign at large gaps INCONCLUSIVE (surviving minus rest −4.6 pp [−20.2, +11.1]) |
| 9 | Silver chance nodes in Heart and boss trees: replace visit-proportional re-picking at the cap by the quasi-random rule argmax P(c)/(N(c)+1); merge outcomes by public equivalence (card copies) | 3 | §706: 91% re-picks, ~40 effective of ~240 outcomes; Hearthstone draw bucketing 60.1% → 72.3% (Verified); Stochastic MuZero rule (Verified; effect not isolated) | 0 to +2 pp | ~140 core-h (128 Heart states × 8 × 2 arms at ~4 min) plus §718 boss states | Equal sims, CRN, §681/§682 Heart and §718 boss states. Drop if median tree rounds do not rise, or if boss HP lost is not ≥ 1 lower and ΔHeart ≤ 0 | §706 candidate; roadmap phase 5. §518 (per-category widening) already null |
| 10 | Boss and Heart playout balance: measure playout bias against a reference, then NN-free PPA/MAST-lite adaptation | 3 | Balanced playout 1367 vs strong RL playout 1159 Elo inside search (Verified); MoGo playout 48.6% vs RLGO 9.4% (Verified); PPA 31 W / 1 T / 8 L (Verified); §681 +4.5 HP | 0 to +2 pp | ≤ 10 core-h with stored references; ~100-150 core-h of fight replays | Offline: does balance MSE order greedy vs prior as the §541/§681 HP results do? If not, drop the metric. Replays: drop if HP lost is not ≥ 1 below greedy, or if it loses to prior playouts at equal CPU | Roadmap phase 5. New: balance objective, online adaptation |
| 11 | heart1 vs student_sel as the OOC policy on cheap combat (distillation gap) | 1 | NetHack BC 7,784 vs teacher 17,274 with ~55B samples (Verified); student agrees with heart1 on 61-73% of key/Act-4 states | 0 to +2 pp if the gap is real | ~8-140 core-h (1,024 pairs at 14-240 core-s per game) | Only after X1 is VALID. If the CI excludes heart1 > student by ≥ 2 pp, distillation is not a lever; otherwise distil more before search work | X1, X2 |
| 12 | Heart root-parallel ensemble 4 × 10k (vote) vs 1 × 40k | 3 | Ensemble determinization +9.6 to +13.2 points at 250k sims (Verified); one deep tree beat 40 shallow ones at small budgets (Cowling; Verified) | 0 to +1 pp (plus 4× wall-clock parallelism) | ~140 core-h | §681 Heart states with CRN: drop if ΔHeart ≤ 0 | ADR-0060 budget |
| 13 | CTM depth repair chain: CTM-chain vs Silver-chain decomposition, Silver-labelled deep rollout boss entries, depth/HP-group recalibration, PPI-rectified R_full referee | 2 (1, 4) | DAgger system identification (Extracted); PPI needs 1.2-2.5× fewer labels (Extracted); §663 R_full undershoots by 0.150-0.231; §137 mixture retrain negative | 0 pp direct; a qualified cheap referee and label source | ~17.5 + 70-170 + 20-60 core-h | Only if rank 3 shows drift. If CTM vs observed act-2/3 boss deaths differ < 2× on ≥ 200 deep states, the 3× was an artifact. The PPI-corrected per-act level must lie within ±0.05 of real (§663's gate); otherwise the bias is root-specific | §663, §670, §709 |
| 14 | Paired-difference effect head (X-learner pseudo-outcome) on CRN forks, as a check on or distillation target for V | 1 | X-learner (Verified); an interaction half the main effect needs ~16× the sample (Verified); §726 operator effects +8 to −21 pp | 0 to +2 pp via leaf terms | Hold-out test on re-run §726 controls; ~25k Heart-entry replays ≈ 370 core-h at research budget | Held-out correlation of predicted and observed differences ≤ 0.1 at 4× the pilot size → stop | §726 (and the §728 artifact) |
| 15 | Dense nested labels: hazard (survival-curve) value, λ-mixed act targets, short-horizon targets from real-game search Q | 1 | Multi-threshold Go value net 60.4% vs single-label (Verified); TD error U-shaped in backup length (Verified); EfficientZero target correction 1.475 → 1.943 (Verified) | 0 to +1 pp | Refits only; CPU/GPU hours | Seed-grouped CV: the hazard V must not lose to the direct head (CI excluding −0.005), and some λ ∈ (0, 1) must beat both endpoints | §641, §719, §725. New: hazard as the value, λ-mix |
| 16 | Counter- and potion-aware CTM trained on fight-level labels, composed into a run value | 1, 2 | Fight labels ~10^9 per year from cheap combat (Inference); sample cost has an additive horizon term (Hilton et al.; Extracted); rollout3 is the best ranker | 0 to +2 pp | 0 on existing logs; ~1,400 core-h per 10^6 new 200-sim fights | Train on Heart and S&S fights. If the aligned-vs-wasted Incense phase difference is < +3 pp (vs §723's +12), composition does not find such effects at that scale | §722 counter features (−0.0001 BCE) |
| 17 | Critic-filtered BC of student_sel on logged A20 decisions before on-policy PPO | 1 | Metamon: critic-weighted BC beat pure BC on ~475k battles (Verified) | 0 to +2 pp | A few GPU-h, then a gate | Drop if it changes < 3% of decisions or does not move the §703 sibling-set score | Roadmap open question (AWR vs async PPO); X2 |
| 18 | Map-search noise: swkeyed rollouts inside the search; (k, α) sweep, probability-weighted backups and quasi-random sampling at OOC chance nodes | 4 | §703 0.18-0.21× sibling variance; GNUbg applies luck cancellation by default (Verified); DP-UCT 0.86 → 0.90 (Verified); tuned DPW keeps 2-8 children (Verified) | 0 to +0.5 pp (all search is worth ~+1.4-2.4 pp) | Tens of core-h offline on the 64 #881 roots | Drop each variant if seed-to-seed disagreement (P_self) and agreement with a 16× reference do not improve beyond CI at equal sims | §714/§717 (swkeyed search "triggered, not started") |
| 19 | Fix Silver's shuffle-in known-top leak: fold the inserted card into the unknown region and forbid it on top at draw time | 3 | Code read (`include/combat/CardPile.h`, branch at line 131); the real root is built correctly | 0 to +0.5 pp | Code change plus tens of core-h of fight replays | Fight-level test on Chosen/Hex, Wild Strike and Reckless Charge decks; drop if HP lost and win rate are unchanged within CI | None |

## Problem 1: outcomes cannot teach interactions at this scale

The AlphaZero family offers better targets, not a shortcut around data. Search-derived value targets (root value
"soft-Z", greedy child, greedy leaf) learned faster and ended stronger than the outcome z on Connect-Four and
Breakthrough; numbers are figure-only ([Willemsen et al.](https://ir.cwi.nl/pub/30870/30870.pdf); Verified). KataGo gets
only a "slight" gain from short-horizon heads; its larger gains come inside the search: uncertainty-weighted playouts
with variance-scaled cPUCT (≈ +75 Elo) and subtree bias correction (+30 to +60 Elo) ([KataGo
methods](https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md); Verified). All of this runs on
millions of games. In Hex each 10× of training compute replaced ~15× of test-time compute
([Jones](https://ar5iv.arxiv.org/html/2104.03113); Verified), so rollout3 beating every head trained on 10^3-10^4
independent games is the expected regime. The bootstrapped act-by-act version (§719/§725) and search-target generations
(§621/§643) are already done. With γ = 1 each bootstrap passes its anchor's full error backwards (Kearns & Singh's bias
term; Inference), so V_A1 inherits V_A4's R² 0.28-of-0.43 error.

Interactions are the expensive part. An interaction half the size of a main effect needs ~16× the sample
([Gelman](https://statmodeling.stat.columbia.edu/2018/03/15/need16/); Verified). A perfectly priced interaction of size
Δ on a fraction π of states lowers aggregate BCE by ≈ π·Δ²/(2p(1−p)); for the Incense phase (±12 pp on ~10% of Act-4
entries, half the variance explained) that is ≈0.0015, below §722's CV half-width (~0.002) and consistent with the
observed −0.0001 (Inference). **The BCE gate is blind to such terms whatever the model.** MTG deck strength saturates
near Spearman 0.23, the Bernoulli-noise limit, and a card-level heuristic beat the learned model zero-shot (0.139 vs
0.088) ([Rigaux & Kashima](https://arxiv.org/pdf/2607.04782); Verified); trees beat neural nets on tabular sets of
10,000 samples ([Grinsztajn et al.](https://ar5iv.labs.arxiv.org/html/2207.08815); Verified). Architecture is not the
lever below ~10^5 games (consistent with ledger-03 §86 and §722).

Two routes fit the evidence. A **paired-difference effect head** regresses CRN fork differences on (state, operator),
the X-learner pseudo-outcome ([Künzel et al.](https://arxiv.org/pdf/1706.03461); Verified); its per-row noise is 0.39/√R
against 0.48 for a Bernoulli row (Inference). That also explains §726: 960 perturbed rows appended as outcomes are an
S-learner, and a ~14% data increase predicts only ≈ −0.002 BCE on §722's curve (Inference). **Fight-level composition**
uses 15-55 dense, continuous labels per game, sample cost has an additive horizon term ([Hilton et
al.](https://arxiv.org/pdf/2301.13442); Extracted), and rollout3, the best ranker, already composes. A CTM that sees
relic counters and potions should then rediscover §723's phase effect without a hand rule (rank 16); whether today's CTM
sees counters was not checked in code.

Data scale is a choice: 10^5 production games cost ≈23k core-h (≈2.5% of the year), and a 4-point V_A4 learning curve
decides whether to buy them (rank 5). AlphaGo's value net overfit on many positions per game ([Silver et al.
2016](https://papers.baulab.info/papers/Silver-2016.pdf)), so the effective n is games; retraining the SR head on one
row per source game is a free check.

Using a value in decisions needs shrinkage first. The argmax of noisy estimates is biased (0.85 SD expected
disappointment with three equal options); the fix is a posterior mean with weight α = 1/(1 + σ²_noise/σ²_true) ([Smith &
Winkler](https://Www.Gwern.net/doc/statistics/decision/2006-smith.pdf); Verified). §715's slope of label differences on
head differences (0.16-0.18) is that α, so a 0.02 head gap predicts ≈0.0035 of true gap (Inference), which reproduces
§727. Under shift, temperature scaling often got worse and 5-member ensembles were most robust ([Ovadia et
al.](https://research.google/blog/can-you-trust-your-models-uncertainty/); Verified). Surrogates must pass §713's
within-pair test, since a correlated surrogate can point the wrong way ([Yin et al.](https://arxiv.org/pdf/1607.05454);
Verified). A distributional head adds nothing for a Bernoulli objective; distributional MCTS gains are for
risk-sensitive utilities ([Hayes et al.](https://arxiv.org/pdf/2102.00966); Verified).

For the roadmap's PPO loop (X2, X3) the lessons concern the loop. Critic-weighted BC beat pure BC on ~475k Pokémon
battles ([Metamon](https://arxiv.org/html/2504.04395v2); Verified), supporting rank 17 before asynchronous PPO. OpenAI
Five kept staleness at 0-1 versions and sample reuse at ~1; reuse 2-3 halved speed ([Berner et
al.](https://arxiv.org/pdf/1912.06680); Verified); per-decision KL and clip fraction between X2 checkpoints at lags 1-8
test this at zero seeds. Potential-based shaping equals initialising Q with the potential
([Wiewiora](https://arxiv.org/pdf/1106.5267); Verified), i.e. a critic offset for PPO with γ = 1 (Inference), so
act-value shaping cannot fix credit assignment by itself. On [Craftax](https://arxiv.org/html/2402.16801v1), 10× more
PPO steps "barely" helped past saturation (Verified; the authors note learning-rate decay may explain it).

## Problem 2: CTM pessimism probably compounds with depth, so it binds mainly long-rollout consumers

The measurements are compatible if the error compounds with depth (a hypothesis; rank 3 tests it). §709 (144 roots, 37,215 combats, ≤ 3-4 imagined fights from
real play) found near-calibration: bosses 12.1% forecast vs 11.0% observed (n = 1,675), elites 3.97% vs 3.00%, boss HP
after a win ~4.4 too optimistic, and a cross-fitted regret of the CTM's pick of +0.0010 [−0.0024, +0.0040]. The
2026-10-31 local diagnostic (8 roots in 4 games, 64 full-game rollouts per arm, Act-4 strong off) gives act-2 bosses
0.155 vs 0.053 (n = 38), act-3 0.177 vs 0.067 (n = 75), but act-1 bosses the other way (0.150 vs 0.219, n = 32), act 4
matched (0.249 vs 0.242, n = 62), and all boss and Act-4 fights 19.0% vs 14.0% (1.36×, n = 207). The diagnostic cannot
separate depth from act: its depth 3-9 bucket is mostly act-1 bosses, and within acts 2-3 the over-forecast appears at
both depths (depth 3-9: 3 observed vs 5.9 forecast, n = 28; depth ≥ 10: 4 vs 13.4, n = 85; review re-cut). The CTM arm
also reaches bosses with fewer potions than the Silver arm (act 2: 1.28 vs 1.61; act 3: 0.72 vs 0.99) at similar HP and
deck size, a concrete candidate for self-generated drift. Its Heart-kill gap (CTM 12.5% vs
Silver 28.1%) uses a naive SE over 64 rollouts that are clustered on 8 roots. §663's full-game CTM rollouts undershoot
real Heart rates by 0.150, 0.165, 0.231 and 0.210 from acts 1-4, while act-end rollouts with M0 undershoot act 1 by only
0.054.

The literature names the mechanism. In MBPO's bound the model-error penalty grows linearly with rollout length, and
model error rises as the rollout policy diverges from the data policy ([Janner et
al.](https://arxiv.org/pdf/1906.08253); Extracted). A model trained only on real one-step data never sees its own
samples, so imagined inputs drift and errors compound ([Talvitie](https://arxiv.org/pdf/1612.06018); Extracted). Here
the rollout policy does not read CTM values, so planner exploitation is confined to tree nodes, where §709 measured it
as negligible (Inference). Two mechanisms remain: policy-induced covariate shift (rollout decks differ from production
decks) and self-generated drift (each imagined fight's sampled HP and potions feed the next). Per-fight biases of +1-3
pp over ~15 elite and boss fights can produce the whole level gap with no single dramatic error (Inference). §670's
residual fits too: the calibrated CTM is pessimistic at high HP and optimistic below 20 HP (0.43 predicted vs 0.47
observed in act 3), i.e. its HP slope is too flat, and deep rollouts drift to low HP.

**Consequence:** the bias binds R_full referees (§663), act-value labels built from CTM rollouts (§719/§725), any
no-rollout value trained on them (X6), and full-rollout leaves. It does not bind rollout3 map decisions, which §709
showed to be noise-limited (median sibling gap 0.019 < SE 0.028 at N = 16).

The repair order follows from cost. First, the zero-compute re-cut of §709's rows by the logged `combat` index (rank 3).
Second, a domain classifier separating §670's production rows from rollout rows (AUC ≤ 0.6 rules covariate shift out),
with importance-weighted CV ([Sugiyama et al.](https://www.ism.ac.jp/editsec/aism/pdf/060_4_0699.pdf); Extracted).
Third, if drift is real, the labelled decomposition (rank 13). DAgger-style identification labels the planner's own
state distribution and bounds performance against the best model in class, where batch fitting has an arbitrarily large
mismatch factor ([Ross & Bagnell](https://arxiv.org/pdf/1203.1007); Extracted). But §137 showed that naive mixture
retraining hurt here, so the safer form refits only the calibration layer, with "imagined depth × act × room" and
entry-HP groups: multicalibration over a small identifiable class ([Hébert-Johnson et
al.](https://proceedings.mlr.press/v80/hebert-johnson18a.html); Extracted). Prediction-powered inference gives an
unbiased level correction from many CTM rollouts plus a few Silver-labelled ones, with label savings of 1.2-2.5× in its
examples ([Angelopoulos et al.](https://arxiv.org/pdf/2301.09633); Extracted). Multi-fidelity Monte Carlo arithmetic
says the CTM is a debiaser, not a variance tool, unless its per-trajectory correlation with Silver is high: ρ = 0.5 buys
only 1.3× (Inference from [Peherstorfer et
al.](https://kiwi.oden.utexas.edu/papers/multi-fidelity-monte-carlo-peherstorfer-willcox-gunzburger.pdf)).

Selective Silver per leaf does not pay for map decisions (rollout3 boss fights alone ≈3.4 core-h per decision;
Inference). Only Act 4, where the CTM was never trained, has a clear case: before any A/B of the opt-in
`STS_OOC_MCTS_ACT4_SILVER_SIMS`, compare the ADR-0048 survival model with Silver on §720's 2,337 real Act-4 entries;
within 2 pp there is no level to fix.

## Problem 3: Heart and boss losses come from what the leaf ignores and how chance is sampled

Hidden-information theory points away from where the problem is. Silver is not PIMC: it keeps the draw pile as an
information set (known top and bottom, sorted unknown multiset), samples each card when it is drawn, and reseeds all six
combat streams from a public per-battle seed (`include/combat/CardPile.h`, `src/sim/search/SilverSearcher.cpp`; code
read). PIMC fails mainly at low leaf correlation and slow disambiguation; Skat and Hearts sit at correlation 0.8-1.0 and
disambiguation ≈0.6 and lose only ≈0.1 points per game to equilibrium ([Long et
al.](https://cdn.aaai.org/ojs/7562/7562-13-11092-1-2-20201228.pdf); Verified). StS draws fit that favourable regime
(Inference), which matches S3's particle ISMCTS adding nothing (§115) and belief plus chain switched on together costing −11.3 pp (§124).
ReBeL and Student of Games exist because an opponent conditions on private information; here the draw-order belief is
computable from public pile contents (Inference). BetaZero's small lesson: give the value belief-spread features, as
mean-only inputs were "inadequate" ([Moss et al.](https://arxiv.org/pdf/2306.00249); Verified).

The tree's real weaknesses are in chance sampling. At the first End Turn on the principal line there are 50-250
outcomes. At the widening cap, 91% of visits re-pick an existing outcome in proportion to its visits (a Pólya urn), so
only ~40 of ~240 outcomes are effective. Card-copy identity splits public-equivalent outcomes, and the tree plans a
median of one round (§706). The Hearthstone precedent is direct: grouping draw outcomes into buckets raised the win rate
against Silverfish from 60.1% to 72.3% ([Zhang
2017](https://era.library.ualberta.ca/files/cv979v349b/Zhang_Shuyi_201709_MSc.pdf); Verified). Stochastic MuZero selects
chance codes by argmax P(c)/(N(c)+1), a quasi-random rule that spreads visits over likely outcomes ([Antonoglou et
al.](https://openreview.net/pdf?id=X6D9bAHhBQ1); Verified). Cowling et al. found that at a fixed budget one deep tree
beat many shallow ones by 22.9% ([Cowling et
al.](https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf); Verified), so merging that buys
depth is the right direction. Rank 9 tests this. It differs from §518, which only rescaled the widening constants per
category and was null.

The leaf is the larger lever, and the theory is clean: a sub-search is consistent with the global objective when its
terminal value is the outer value at the sub-game's exit (POLO; ReBeL's subgame leaves; Recall). Silver's
`evaluateEndState` prices HP after post-combat heals, max HP gained, potions (11 each), gold (0.25 per unit),
cheat-death items, turns, Smoke Bomb escapes and Writhing Mass's Parasite. It has no term for relic counters, Ritual
Dagger growth, Lesson Learned or Genetic Algorithm upgrades, or curses and cards added. The Incense term exists only at
Shield & Spear under a research flag that is off by default (code read). Every omitted variable carries an implicit
price of 0, a bias no budget removes. §724's single term gained +5.9 pp per Incense-holding S&S entry (≈ +0.3 pp per
run at ≈13% prevalence); budget levers such as §682's +2.4 pp are measured over all Heart states, so the two are on
different scales. Rank 4 enumerates the
omitted items, probes each the §723 way and gates only the ones that matter. Separately, §724 itself is a PASSed default
candidate whose production-budget check is Philipp's call (≈ +0.3 pp per run if the research-budget effect holds). At the
Heart, `finalFightLeaf` scores every win as winBonus + root max HP, so Heart search quality depends on playouts and loss
shaping, not on HP.

Playouts deserve a different objective. A stronger simulation policy can make Monte Carlo search weaker: in 5×5 Go,
simulation balancing scored 1367 Elo inside search against 1159 for the RL policy that was stronger on its own ([Silver
& Tesauro](https://icml.cc/imls/conferences/2009/papers/500.pdf); Verified). MoGo's handcrafted playout reached 48.6%
against GnuGo, compared with 9.4% for the stronger-head-to-head RLGO playout ([Gelly &
Silver](https://carlo-hamalainen.net/stuff/mdpnotes/papers/387.pdf); Verified). Online playout adaptation won 31 of 40
settings against UCT with random playouts ([Cazenave,
PPA](https://www.lamsade.dauphine.fr/~cazenave/papers/rpagames.pdf); Verified). In boss trees, rollouts supply 70-88% of
simulated actions (§706), and prior playouts gave +4.5 HP at S&S (§681) but −0.72 HP in elites (§716). Rank 10 measures
balance (bias of the mean playout return against a reference) before any distillation, and any distilled playout should
be fitted to reference values, not to Silver's moves. In the longest Pokémon battles a search-free learned policy beat
the best search engine ([Metamon](https://arxiv.org/html/2504.04395v2); Verified).

Learned combat leaves failed here when they regressed an unbounded, per-turn-growing score (§655, §656, §675). The
working card-game precedent predicts a bounded win probability at a turn boundary: a Hearthstone P(win) value net at the
rollout cutoff, together with a greedy attack solver, took the second player from 26.5% to 56.1% against plain MCTS ([Świechowski et
al.](https://ar5iv.arxiv.org/html/1808.04794); Verified). A factorised leaf p_win·(winBonus + E[HP | win]) + (1 −
p_win)·loss score cannot exceed the best terminal score by construction (Inference). Check that offline on §675's
on-policy boss states, then run §638's long-fight check before any A/B. On budget, published decision-time search pays
most at intermediate budgets ([Hay et al.](https://arxiv.org/pdf/1207.5879); Verified), and §716/§718 found bosses and
act-2 elites flat at 40k. The Heart already runs 40k (§682, ADR-0060); a 4 × 10k root-parallel ensemble is the only
budget-shaped idea with outside support (rank 12; [ED-MCTS](https://arxiv.org/pdf/2607.13007); Verified). Turn-level
macro actions stay unranked (Zhang: one vs several searches per turn 51.7% vs 48.3%; turn-beam null, §135b).

## Problem 4: cheaper pairs beat cleverer statistics

The arithmetic is unforgiving. The paired outcome per seed is D ∈ {−1, 0, +1} with Var(D) ≈ q − δ², and a discordant
share q ≈ 0.18-0.21 reproduces the SD of 0.42-0.46. At 80% power and two-sided 5%, a true effect of 1 pp needs 15,178
pairs (≈6,970 core-h), 2 pp 3,795 (≈1,740) and 3 pp 1,686 (≈775). The roadmap's ±1.0-pp gate (~7,000 pairs) has only
≈50% power against a true +1 pp (Inference).

The largest levers lower the cost per pair. **Control-arm reuse** plays the default once per frozen seed and charges
each candidate only for arm B; in a 16-candidate simulation with an assumed effect prior, it raised the expected sum of
adopted effects from 3.71 to 5.89 pp at equal core-h, more than any screening scheme (Inference (simulation)).
**Sequential tests** follow Fishtest practice: SPRT on game pairs with bounds in normalised Elo, pentanomial pair
scoring (1,809 vs 2,191 games in one comparison), and a short-control run before a long-control run ([Fishtest
mathematics](https://github.com/official-stockfish/fishtest/wiki/Fishtest-mathematics);
[vdbergh/pentanomial](https://github.com/vdbergh/pentanomial); Verified). On D, a simulated [0, +2 pp] SPRT stopped
after 2,815-2,929 pairs at the null and at the design effect, against 5,412 for the equivalent fixed test (Inference
(simulation)). A 4-look O'Brien-Fleming design costs ≤ 2.2% extra at the cap and ≈77% of fixed n under the alternative
([SAS](https://support.sas.com/documentation/cdl/en/statug/63347/HTML/default/statug_seqdesign_sect004.htm); Extracted).
Early-stop estimates are biased upward; report effects from a fresh block. Always-valid confidence sequences need ≈85%
more samples for equal power ([vendor
comparison](https://blog.analytics-toolkit.com/2022/comparison-of-the-statistical-power-of-sequential-tests/);
Extracted), so keep them for pooled evidence across PPO checkpoints.

Coupling after divergence is the second lever. The run-level card, relic, event, potion, merchant, treasure and Neow
streams advance sequentially from game start, while combat streams reseed from seed + floor (`src/game/GameContext.cpp`,
`src/combat/BattleContext.cpp`; code read). Paired arms therefore share maps, monster lists and same-floor combat
streams but lose card, relic and event offers at the first difference in draw counts. Raising post-divergence ρ from
0.49 to a hypothetical 0.65-0.70 would cut Var(D | diverged) to 0.59-0.69× (Inference). In simulation optimisation, CRN raised the
probability of correct selection more than it cut sample size ([Chen](https://informs-sim.org/wsc01papers/053.PDF);
Extracted). A keyed mode breaks Java seed parity and must stay out of parity and expert-replay work. For candidates that
act only in Act 4, stage gates already exist: §724's S&S→Heart units cost ~53 s each at research budget (70 CPU-h for
4,736 units) against 826 s per production game. Both arms must be replayed fresh (§726/§728), and a whole-game
confirmation follows. Outside Act 4, forks must replay the prefix, and no per-act CPU profile of the production stack
exists (corrections 7-8); a few `STS_RUN_PROFILE` runs on Heart-reaching seeds would supply it.

Proxies and pre-screens must be validated across contrasts, not on one. X1 replays only §691's +6.1 pp; it cannot show
that the cheap proxy ranks 1-3 pp candidates. The trial-level standard regresses proxy effects on production effects
across ≥ 5-6 contrasts of both signs ([Buyse et al.](https://doi.org/10.1093/biostatistics/1.1.49); Recall): §691
(+6.1), §724 (+5.9), §661 (+2.15), §676, §693 (−2.5). As a control variate the proxy is likely weak (per-seed ρ_c ≈
0.2-0.4, ≤ 4-16% variance; Inference); X1's per-seed output measures it. Two-stage screening (256 pairs each, then
confirmation of the top 6) cut false adoptions about 3× in simulation with almost no change in expected gain; fit the
effect prior from recorded A/Bs by empirical Bayes before choosing.

Three popular tools do not help this gate. CUPED-type adjustment cut variance ≈50% at Bing ([Deng et
al.](https://exp-platform.com/cuped/); Extracted), but seed pairing already is that adjustment. A pre-divergence
covariate is identical in both arms and can remove only effect heterogeneity, ≤ 1-2% of Var(D) (Inference); a
cross-fitted R² of D on start features < 0.02 would confirm it at zero cost. Off-policy evaluation from logs is
unavailable, because recorded play is deterministic (root argmax of visits; play sampling off; the full-budget fraction
is a deterministic hash), so logged propensities are 0 or 1. Doubly robust or SPIBB-style methods need a stochastic
logging run, and even then ESS ≈ N·p^k collapses for whole-run changes (Inference;
[SPIBB](https://ar5iv.labs.arxiv.org/html/1712.06924); Extracted). A Heart surrogate index (predicted kill from Act-4
entry) may screen but never gate: §697's model-only baseline shifted effects by −2.0 to +3.2 pp.

Decision-level noise follows the same logic. A two-SE separation of a sibling gap Δ needs n ≈ 8σ²ρ/Δ² samples per child:
≈280 at Δ = 2 pp at map roots (σ = 0.13, ρ ≈ 0.82, §707) and ≈60 with swkeyed streams (Inference). The 4,096-sim map
search resolves 2 pp gaps but not 1 pp gaps, and 43% of leading pairs are < 1 pp (§707). Per-decision effects of ~0.1 pp
are invisible one at a time but visible pooled at policy level, which is what an outcome-driven PPO gradient does
([Hamrick et al.](https://arxiv.org/pdf/2011.04021): search used only for learning lifted normalised strength from 46.7%
to 68.5%; Verified). At production widening (k = 4, α = 0.75; correction 2) the map tree is near open-loop averaging;
rank 18's variants are cheap offline checks with small stakes.

## Already tested — do not repeat

- Root allocation and Q-led roots: Gumbel sequential halving §619/§635; Q-capped Gumbel §689/§693; uniform-root
  best-mean-Q at card rewards §712; CRN particle root search §680; value chooser §727; forced leaf departures at z > 2
  disagreement roots §710; map-only search kept §683 (ADR-0061).
- Leaf mixing: AlphaGo-style rollout/value blend in Silver §525; SR head and X2-B logit blends at the OOC leaf §636,
  §641, §661 (M0 kept), §715.
- Widening: per-category progressive widening on Silver §518 (NOT_SHOWN; OOC never tested).
- Value targets and heads: outcome labels on first-divergence pairs §685; act-end labels §719; backward act values
  §719/§725; AZ generations §621/§643; auxiliary heads §641; SR data halving §700; swkeyed labels for SR §714; V_A4
  MLP/transformer and relic-counter features §722; deck set transformer ledger-03 §86; V_A4/V_H teacher check §721;
  perturbation rows into V_A4 §726 (in-game artifact §728); encounter marginalization of labels §168/§169; readiness
  surrogate within pairs §713.
- CTM: per-fight calibration on real fights §670/§676 (ADR-0058); survival and HP fine-tunes §672/§679; CTM vs Silver
  leaf combats at map roots §709; R_full referee levels §663; covariate-shift mixture retrain of the in-combat leaf
  §137; Act-4 survival model ADR-0048.
- Combat search: particle ISMCTS and belief filtering §115/§124 (ADR-0019); turn-beam rollout §135b; turn dominance
  §658; last-turn optimality §654; prior playouts §540/§541/§681/§716; Silver budget raises §716 (act-2 elites), §718
  (bosses), §682 (Heart 40k, ADR-0060); learned leaf heads §655/§656/§675; utility-R regression §134; final-fight leaf
  §466/§468/§474 (ADR-0035); victory turn penalty §704; Incense term §723/§724.
- Evaluation: AIVAT fight-replay control variate §697/§698 (SD 0.80×); CTM model-only luck baseline biased §697.
- The earlier review's ten ideas §686-§698: keys §691, expert audit §688, expert replay §694, elite dose §686,
  boss-relic forks §690, AIVAT §697/§698, expert ranker §696, HP into the Heart §687, bounded Q tilt §689/§693, P300
  cross-check §692.

## Corrections to project beliefs

1. **"The CTM predicts 3× too many act-2/3 boss deaths" is not established.** It rests on 2/38 and 5/75 observed deaths
   in a single uncommitted diagnostic (8 roots, 4 games, Act-4 strong off), selected subgroups of 207 boss and Act-4
   fights that pool to 1.36×. Act-1 bosses go the other way, and Act 4 matches. The diagnostic cannot separate depth from
   act. §709 shows near-calibration within ≤ 3 imagined fights. Working hypothesis (to be tested by rank 3): a small
   per-fight bias compounding over long rollouts, relevant to full-rollout leaves, referees and labels, not to rollout3.
2. **OOC widening in production is k = 4, α = 0.75, not the code default k = 2, α = 0.5.** All 37 campaign `run_unit.sh`
   files that set widening, including §683 and §727, and the live advisor use 4 and 0.75
   (env parse `apps/one_combat/ooc_mcts_adapter.cpp:3315-3316`; code default `include/sim/search/OocMctsPlanner.h:80-81`; live advisor
   `apps/one_combat/live_ooc_policy.cpp:438-442`, research stack only, on by default). The cap 4·N^0.75 is at least N up to N = 256, so a
   chance edge samples a fresh particle on every visit up to 256 visits, unless outcomes merge by key (Inference). Two
   source notes reasoned from 2 and 0.5 and reached opposite readings ("too stingy" vs "wide by published standards");
   at production values the widening is wider still against tuned DPW practice (k_o 2-8, α_o 1/100-1/10;
   [POMCPOW](https://arxiv.org/pdf/1709.06196); Verified). §518 concerns Silver, not the OOC planner.
3. **Silver has no general draw-order leak and is not PIMC.** The single exception is a shuffle-in into a pile with no
   known top (Wild Strike, Reckless Charge, the Chosen's Hex Dazed, monster status insertions). There Silver samples an
   unknown card into a known top, a one-card leak until that card is drawn (`CardPile.h`, branch at line 131). ISMCTS or
   "fair re-determinization" proposals have no other target.
4. **Silver's fight-end score does not price** counter relics (Pen Nib, Nunchaku, Sundial, Ink Bottle, Happy Flower),
   Ritual Dagger growth, Lesson Learned or Genetic Algorithm upgrades, or curses and cards added (other than Writhing
   Mass's Parasite). Incense Burner is priced only at S&S under a research flag that is off by default
   (`SilverSearcher.cpp:1233-1323`).
5. **Paired seeds lose common random numbers after the first OOC divergence.** Card, relic, event, potion, merchant,
   treasure, Neow and monster-list streams advance sequentially, while combat streams reseed per floor from seed + floor
   number. Paired-seed variance reduction decays along the run.
6. **Importance-sampling OPE is not available from recorded play.** The behaviour policy is deterministic. MCTS decision
   rows do log prior, visits, q and checkpoints at 128, 256, 512, … simulations, which supports value-of-computation and
   stop-rule studies offline. Combat decisions log no visits or priors.
7. **There is no general mid-run save and restore.** Forks replay the prefix deterministically; on-disk restore covers
   Act 4 (`act4replay`), single fights (`fightreplay`) and combat starts. Fork-gate savings outside Act 4 must include
   the prefix cost.
8. **No per-act CPU breakdown of the current production stack exists.** Plans that assume an Act-4 CPU share (f ≈ 0.75)
   or "OOC search 97-98%" (§533, older stack) should measure first. The four profiled games point to ≈80% OOC search and
   15-20% real combat outside Act 4.
9. **CUPED on pre-divergence covariates cannot help the paired gate much (≤ 1-2%).** Pairing on the seed already removed
   ≈50-57% of variance (§697).
10. **Stochastic MuZero did not beat a perfect simulator.** It matched AlphaZero at equal simulations, and its 2048
    gains flattened beyond about 3-ply because of model error (Verified). The transferable parts are the afterstate
    value and the quasi-random chance rule, not learned dynamics.

## Known limitations / coverage gaps

- Web fetches were rate-limited (100 per hour, shared). Unread or abstract-only: the Balatro RL preprint (arXiv
  2610.39049, the closest new deckbuilder RL result; read it first in any follow-up), Student of Games full text, the
  CATS/PATS paper, Couëtoux et al. 2011 full text, Ng et al. 1999 original, MuZero Reanalyse and Unplugged, the
  OpenBench wiki, Fishtest's resource tables, POMCP 2010, AutoAscend internals and the AgenticSTS paper. Hamrick et al.
  was verified in one note and not re-fetched in the follow-up.
- No published StS agent beats this bot under fair information (the best LLM agent: 4/15 A20 Ironclad Heart kills,
  [Epoch](https://epoch.ai/publications/ai-systems-are-improving-rapidly-at-slay-the-spire-and-its-sequel); Verified).
  No StS, Hearthstone or MTG system reports fair-information boss or Heart search metrics, uses a learned combat-outcome
  model inside a deck-building planner under planner shift, or studies ascension curricula. All mappings to this bot are
  Inference.
- The source notes disagree in places. AlphaGo's per-game overfitting MSE (0.19 vs 0.37 train/test) is Verified in one
  note and "could not be verified" in another; only the overfitting statement is used here. OOC widening was analysed at
  the code default in two notes (corrected above). The evaluation note labels nothing Verified, because none of its
  claims went through a vote check.
- §709's raw rows were not opened (outside the allowed paths); that they carry the imagined-fight index is Medium
  confidence (the field is in the code at that commit). The 8-root diagnostic has no cluster-robust CI.
- Gain ranges are planning numbers. The screening and SPRT simulations use an assumed prior of effects and a plug-in
  variance. The V_A4 data extrapolation assumes a decay rate and an Act-4 reach rate that were not looked up.
- Production-budget costs of fight-level tests are scaled from §724 (research budget) and the ~4-min Heart fight;
  boss-fight costs at production were not measured here.

## Sources

- Search and value: AlphaGo https://papers.baulab.info/papers/Silver-2016.pdf; Stochastic MuZero
  https://openreview.net/pdf?id=X6D9bAHhBQ1; Hamrick et al. https://arxiv.org/pdf/2011.04021; KataGo
  https://github.com/lightvector/KataGo/blob/master/docs/KataGoMethods.md; Willemsen et al.
  https://ir.cwi.nl/pub/30870/30870.pdf; EfficientZero https://ar5iv.labs.arxiv.org/html/2111.00210; Jones
  https://ar5iv.arxiv.org/html/2104.03113; POLO https://arxiv.org/pdf/1811.01848
- Chance nodes and roots: Keller & Helmert https://ai.dmi.unibas.ch/papers/keller-helmert-rldm2013.pdf; GNU Backgammon
  https://www.gnu.org/software/gnubg/manual/html_node/Rollouts-in-GNU-Backgammon.html; Hay et al.
  https://arxiv.org/pdf/1207.5879; POMCPOW https://arxiv.org/pdf/1709.06196; BetaZero https://arxiv.org/pdf/2306.00249
- Imperfect information and card combat: Cowling et al.
  https://eprints.whiterose.ac.uk/id/eprint/75048/1/CowlingPowleyWhitehouse2012.pdf; Long et al.
  https://cdn.aaai.org/ojs/7562/7562-13-11092-1-2-20201228.pdf; ED-MCTS https://arxiv.org/pdf/2607.13007; Zhang 2017
  https://era.library.ualberta.ca/files/cv979v349b/Zhang_Shuyi_201709_MSc.pdf; Świechowski et al.
  https://ar5iv.arxiv.org/html/1808.04794; ReBeL https://arxiv.org/abs/2007.13544; Student of Games
  https://arxiv.org/abs/2112.03178v2
- Playouts: Silver & Tesauro https://icml.cc/imls/conferences/2009/papers/500.pdf; Gelly & Silver
  https://carlo-hamalainen.net/stuff/mdpnotes/papers/387.pdf; PPA
  https://www.lamsade.dauphine.fr/~cazenave/papers/rpagames.pdf
- Value learning: Kearns & Singh https://www.cis.upenn.edu/~mkearns/papers/tdlambda.pdf; Gelman
  https://statmodeling.stat.columbia.edu/2018/03/15/need16/; Künzel et al. https://arxiv.org/pdf/1706.03461; Rigaux &
  Kashima https://arxiv.org/pdf/2607.04782; Grinsztajn et al. https://ar5iv.labs.arxiv.org/html/2207.08815;
  multi-labelled Go nets https://arxiv.org/pdf/1705.10701; Smith & Winkler
  https://Www.Gwern.net/doc/statistics/decision/2006-smith.pdf; Ovadia et al.
  https://research.google/blog/can-you-trust-your-models-uncertainty/; Yin et al. https://arxiv.org/pdf/1607.05454;
  Hilton et al. https://arxiv.org/pdf/2301.13442; Hayes et al. https://arxiv.org/pdf/2102.00966; Wiewiora
  https://arxiv.org/pdf/1106.5267
- Learned simulators: MBPO https://arxiv.org/pdf/1906.08253; Talvitie https://arxiv.org/pdf/1612.06018; Ross & Bagnell
  https://arxiv.org/pdf/1203.1007; Sugiyama et al. https://www.ism.ac.jp/editsec/aism/pdf/060_4_0699.pdf;
  multicalibration https://proceedings.mlr.press/v80/hebert-johnson18a.html; PPI https://arxiv.org/pdf/2301.09633; MFMC
  https://kiwi.oden.utexas.edu/papers/multi-fidelity-monte-carlo-peherstorfer-willcox-gunzburger.pdf
- Evaluation: Fishtest https://github.com/official-stockfish/fishtest/wiki/Fishtest-mathematics; pentanomial
  https://github.com/vdbergh/pentanomial; O'Brien-Fleming
  https://support.sas.com/documentation/cdl/en/statug/63347/HTML/default/statug_seqdesign_sect004.htm; sequential-test
  power https://blog.analytics-toolkit.com/2022/comparison-of-the-statistical-power-of-sequential-tests/; CUPED
  https://exp-platform.com/cuped/; CRN in selection https://informs-sim.org/wsc01papers/053.PDF; SPIBB
  https://ar5iv.labs.arxiv.org/html/1712.06924; Buyse et al. https://doi.org/10.1093/biostatistics/1.1.49
- Game agents: Metamon https://arxiv.org/html/2504.04395v2; NetHack imitation scaling
  https://ar5iv.labs.arxiv.org/html/2307.09423; Craftax https://arxiv.org/html/2402.16801v1; OpenAI Five
  https://arxiv.org/pdf/1912.06680; Epoch SpireClimb
  https://epoch.ai/publications/ai-systems-are-improving-rapidly-at-slay-the-spire-and-its-sequel
- Source notes (not in the repository): `/mnt/project-files/deep-research-20261031/notes/` on the project share, eight
  files, one per strand plus `repo_fact_checks.md` (all code facts). The share is not durable; this page is the record.
