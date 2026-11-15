# A20 loss mining: where production runs die and what is avoidable

Last verified: 2026-10-31 against 2,816 recorded production A20 games (§729, [evidence](../../experiments/evidence/loss_mining_20261031/README.md));
extended 2026-11-01 to 15,363 games of nine campaigns (roadmap X5, §740, [evidence](../../experiments/evidence/loss_clusters_x5_20261101/README.md)).

## Question

Where and why do today's A20 runs die, and which deaths would a different decision plausibly have avoided? Rank the
largest structural gaps by Heart-kill potential and propose a pre-registered gate for each. Offline only (roadmap
item X5 of the one-year roadmap, docs PR #925).

## Data

§727 arm A (1,536 games, Heart kill 25.1%) and the §720 run-1 base games (1,280, 26.3%), both at the A20 default of
their date (flexible keys, student_sel with map-only OOC search, learned-stop Silver, Act 4 strong). Per-fight CTM
rows give entry and exit HP, potions, deck, relics and encounter. Every number below is pooled; each headline
replicates in both sets separately (`results/*.A.txt`, `*.R1.txt`). Observational: lever sizes are upper bounds.

## Where runs die (share of all runs)

| stage | deaths | of which entered with HP < 50% | HP ≥ 50%, no potion | HP ≥ 80% and ≥ 1 potion |
|---|---:|---:|---:|---:|
| Act-3 bosses (A20: two) | 14.5% | 6.2 | 3.7 | 2.2 |
| Heart | 14.3% | 4.8 | 4.1 | 2.8 |
| Act-2 boss | 11.9% | 1.6 | 3.4 | 4.3 |
| Act-1 boss | 8.3% | 1.2 | 1.6 | 1.0 |
| Act-2 elites | 6.5% | 2.5 | 1.6 | 1.1 |
| Act-1 elites | 4.5% | 2.3 | 0.7 | 0.6 |
| Act-3 elites | 4.4% | 1.3 | 1.6 | 0.9 |
| Act-2 hallways | 4.3% | 3.8 | 0.3 | 0.0 |
| other (act-1/3 hallways, S&S, event fights) | 5.6% | | | |

- Bosses kill **49%** of all runs; with elites and the Heart, 9 of 10 deaths are in hard fights.
- 80% of deaths happen in a depleted state (HP < 80% or no potion); 14.6% of all runs die "healthy" (≥ 80% HP
  and a potion).
- Per fight (pooled): Heart 35.8%, **Awakened One 23.1%**, **Collector 21.7%**, Automaton 13.6%, Champ 12.6%,
  Hexaghost 11.3%, Time Eater 10.9%, Slime Boss 8.6%, Donu & Deca 7.2%, Guardian 6.1%, S&S 3.7%. Baalorlord per
  fight (§701): Awakened One 3.0%, Collector 6.6%, Donu & Deca 1.0%, Heart ≈ 8%.
- Entry HP dominates boss deaths: Heart 86 / 60 / 41 / 20% at < 40 / 40-60 / 60-80 / ≥ 80% HP; Awakened One 76 / 59 /
  31 / 11%; Time Eater 49 / 24 / 11 / 3%. Collector and Hexaghost are the exceptions (17% and 7% even at ≥ 80% HP).
- Only 0-3% of boss deaths still hold a potion: dying with unused potions is not a loss source (as §466).

## Exchange rates measured from the deaths

Per-act logistic boss-death models (boss, HP, max HP, potions, deck size, upgrades, curses, Strikes/Defends, relics,
HP lost per earlier hallway/elite fight; `bossreg.py`):

| | act-1 boss | act-2 boss | act-3 bosses | Heart |
|---|---:|---:|---:|---:|
| fight death per entry HP | −0.34 pp | −0.39 pp | −0.36 pp | **−0.71 pp** |
| one potion at entry, in entry HP | 18 | 21 | 12 | 15 |
| P(Heart kill \| survived) | 0.30 | 0.41 | 0.52 / 0.62 | 1 |

The Heart slope (0.71 pp per HP) matches V_H's 0.75 pp per HP (§721, used by the Incense term), and the Heart potion
rate (15 HP) is close to V_H's 12-13 HP, so the observational Heart prices and the Heart-entry value agree.

**The potion rates are observational only.** An attempted instrument (potions offered before the boss) is
**invalid**: the records list a potion offer only when the belt has room (`potions_offered` is built from valid take
actions), so recorded offers depend on how often the bot drank, which tracks deck strength and also drives boss
death (independent review of #926). Its estimates (`iv.py`) are kept for transparency but support no conclusion, and
the potion–death association stays an upper bound, neither confirmed nor refuted. Belt-full waste is **not
measurable** from these records either: about 21% of won hallway/elite fights end with a full belt, and a potion
that drops then is never logged (open: the engine could log dropped potions).

## Checked and small (no gate proposed)

- **Ruby Recall timing:** the policy takes the Recall at the pre-boss campfire in 33% of runs; below 60% HP in 5.0%
  (half of those passed an earlier act-3 campfire at ≥ 60%). Resting there instead is worth ≤ +0.50 pp Heart kills
  before paying for an earlier Recall (A +0.41, R1 +0.62). Confirms §687 (≤ 0.65 pp).
- **Campfires before bosses:** at < 50% HP the bot rests (603 of 709 before the act-1 boss; the smiths are
  mostly Coffee Dripper per §687). Low-HP hallway/elite deaths in acts 1-2 (9.4% of runs) mostly rested at their
  last campfire; 99 of 266 had no campfire yet in that act.
- **A20 double act-3 boss:** the second boss starts at 77% HP with half the potions (0.76 vs 1.54) and kills 15.7% vs
  12.1%. Silver already scores the first boss without the act heal (`actHealFollows`), and the act-3 potion rate
  (12 HP) is near the leaf's 11, so no pricing gap is visible.
- **Boss-conditioned card picks:** student_sel sees the act boss (`obs.fixed_observation[4]`) but its picks do not
  move with it: power pick rate 51 / 51 / 51% for Awakened One / Donu & Deca / Time Eater, AoE 14.5 / 14.9 / 15.1%
  for Collector / Champ / Automaton. The deck signal is weak too: powers raise Awakened One deaths (OR 1.08 per power,
  z +2.1; protective at every other boss), AoE count is unrelated to Collector deaths (OR 1.00). A boss-aware pick
  would move Awakened One deaths by ~2 pp per fight at most (≈ 0.2 pp of runs). Inference.

## Structural gaps, ranked

| # | gap | runs affected | ceiling | plausible | evidence class |
|---|---|---:|---:|---:|---|
| 1 | Awakened One play | 8.2% die there | +2.5 pp (to Time Eater's rate), +4.0 pp (to the expert's) | 0.5-1.5 pp | per-fight 23% vs 3% expert; not deck-explained |
| 2 | Heart entry state (S&S → Heart) | 14.3% die at the Heart | +1.9 pp per +10 HP at Heart entry | ≈ 0.27 pp (Incense, research search) + ≤ 0.5 pp | Heart deaths lost 31 HP at S&S vs 10 for Heart wins |
| 3 | Act-2 bosses at healthy entry | 4.3% die healthy | +2.4 pp (act-2 boss death halved), +0.9 pp (Collector to Champ) | 0.3-1 pp | deck-limited, not budget-limited (§716) |
| 4 | Low-HP attrition in acts 1-2 hallways/elites | 9.4% die below 50% HP | not estimable offline | ≤ 1 pp | §686 routes; HP-loss gap §701 |

### 1. Awakened One

The largest cluster outside the Heart: 8.2% of runs (A 7.8%, R1 8.7%), per fight 20.7% as the first act-3 boss and
25.8% as the second, against 6-12% for Time Eater and Donu & Deca and 3.0% for Baalorlord. At ≥ 80% entry HP it still
kills 11% (Time Eater 3%, Donu 1%). Deck features explain little (above), so **Inference:** play limits it (phase-2
rebirth, Curiosity strength from powers, Silver's one-round tree horizon, §706). Not tested here.

**Gate (diagnostic first, no new seeds):** `one_combat fightreplay` on all 1,001 recorded Awakened One entries of
both sets (rows + `tools/fight_replay_rows.py` context), R = 2 redraws, arms: production vs flat 40k. Cost ≈ 1,001 × 2 ×
(≈ 30 s + ≈ 200 s per copy, from §716's act-2 boss timings) ≈ 130 core-h; a 4-copy smoke fixes the real cost. Decision: if flat 40k cuts per-fight death by ≥ 4 pp (one third of the gap to Time Eater),
the gap is planning-limited and the next step is a priced boss budget (sims allocated by death risk × continuation
value) gated by a whole-run A/B; otherwise Awakened One goes to phase 3/5 (PPO prior, boss playout policy) as a named
target metric.

### 2. Heart entry state

The Heart kills 36% of arrivals. Heart deaths entered at 64% HP with 0.68 potions after losing 31.4 HP at S&S; Heart
wins entered at 87% with 1.29 potions after losing 10.4 (both sets agree within 2 HP). Silver's S&S leaf prices HP
1:1 and potions at 11 HP, close to the Heart's measured 15 HP per potion, so relative prices are not the gap. The one
priced S&S term found so far, the Incense counter (§724), gives **+5.9 pp of Heart kills in S&S states that hold
Incense Burner**; 11.1% of S&S arrivals hold it and 41.5% of runs reach S&S, so **≈ +0.27 pp of all runs**
(Inference; the term is default off; §724 measured it at research Heart search with learned stop, not the
Act-4-strong production budget, so its production size is unverified).

**Gate:** extend §724 from Incense to every relic counter that carries into the Heart (Pen Nib, Nunchaku, Sundial,
Happy Flower, Ink Bottle, …) and to max HP, priced by the Heart-entry perturbation labels of #922 (in flight), on all
1,168 S&S entries of both sets with `act4replay` chain = heart, 2 arms × 4 replicates: ≈ 1,168 × 8 × 54 s (§724's
CPU per S&S + Heart run) ≈ 140 core-h. PASS if the Heart-kill CI lower bound > 0. Making the Incense term default needs no new run (Philipp's call).

### 3. Act-2 bosses at healthy entry

Act-2 bosses kill 15.9% per fight (expert 5.5%, §701), and 4.3% of all runs die there at ≥ 80% HP with a potion
(Collector 17% per fight at ≥ 80% HP). §716 found act-2 bosses not budget-limited (flat 40k −3.3 HP [−6.8, +0.3] at
7.4× CPU). Picks do not react to the boss, and AoE count is unrelated to Collector deaths. **Inference:** general
deck strength and boss play, not a boss-specific rule.

**Gate (offline, free):** add boss × deck interactions (card types, key cards, upgrades) to the act-2 boss death
model and compare seed-grouped CV log loss with the boss-blind model. If the interaction model wins with CI > 0, a
boss-conditioned card value is worth a screen (via the phase-3 PPO prior, not a pick rule); if not, this gap is phase
3/5 work with act-2 boss death per fight as its metric.

### 4. Low-HP attrition deaths in acts 1-2

9.4% of runs die in an act-1/2 hallway or elite fight entered below 50% HP (act-2 hallways 3.8%, median entry 20 HP,
after losing a median 15.5 HP in the fight before). No campfire misuse is visible. Remaining decision lever: the map
route at low HP (§686 measured the elite take rate falling to 0.26-0.55 at 20-59% HP but did not price hallway risk).

**Gate (offline):** on the first-divergence map roots of the existing paired A/Bs (§661, §676, §683, §691) with HP <
50%, compare children by hallway/elite fights before the next campfire; continue to a leaf check (X2-B's HP slope at
low HP against the observed death hazard) only if the safer child shows ≥ +1 pp Heart kills.

## X5: loss clusters on 15,363 games (2026-11-01)

Roadmap X5 on every A20 campaign with per-fight rows: nine campaigns, 18,688 games, primary set 15,363 (arms within
4 pp of their campaign's best; §727 B, §691 R and §712 B-D dropped), plus the 23,503 fights of §698's replay of the §676
guard (4 fresh combat draws per recorded entry state). Offline, no seeds. Rule from the roadmap: a cluster becomes a
gate candidate if it covers ≥ 2% of runs and a replay or counterfactual bound shows ≥ +1 pp Heart-kill potential.

**Clusters ≥ 2% of runs** (share of runs; per-fight death; range of the share over the nine campaigns):
Heart 14.6% (37.0%; 12.5-15.4), Awakened One 8.3% (22.9%; 5.9-9.6), act-2 hallways 4.9% (88% of them entered below
50% HP; 3.9-7.5), Collector 4.7% (18.9%), Hexaghost 3.6%, Automaton 3.5%, Time Eater 3.4%, Donu & Deca 3.0%,
Reptomancer 2.9%, Champ 2.8%, Slavers 2.5%, Gremlin Leader 2.4%, act-3 hallways 2.3%, Slime Boss 2.2%, Book of
Stabbing 2.0%. Same ranking as §729 on more data; the shares hold in every campaign. **Duplicates:** 1,351 of the
15,363 primary games are exact copies (same seed, same config) across §720 base, expert-anchored A and §712 A (878
expanch A = r1 base, 109 equal to both expanch arms and r1, 245 card-rule A = r1 base, one repeated seed each in
expanch and r1), so the primary set holds 6,912 unique seeds and about 7, not 9, independent campaign replications;
the seed bootstrap already clusters them, and without them the bounds move ≤ 0.05 pp (Awakened One +3.08 [+2.76,
+3.40], Reptomancer +0.86, Collector +0.67; independent review of #936).

**Counterfactual bound** (`potential.py`): each boss/elite against its act siblings at the same entry-HP band and
potion count, excess deaths × P(Heart kill | survived it), seed bootstrap:

| cluster | excess deaths (% of runs) | Heart-kill potential | 95% CI | range over 9 campaigns |
|---|---:|---:|---|---|
| Awakened One | 5.29 | **+3.11 pp** | [+2.81, +3.43] | +2.4 to +4.0 |
| Reptomancer | 1.82 | +0.84 pp | [+0.67, +1.01] | +0.6 to +1.2 |
| Collector | 1.59 | +0.64 pp | [+0.47, +0.84] | +0.3 to +1.2 |
| Hexaghost | 1.37 | +0.40 pp | [+0.26, +0.53] | −0.1 to +0.7 |
| Slavers, Gremlin Leader | 0.3, 0.2 | ≤ +0.12 pp | include 0 | |
| all other bosses/elites | < 0 | < 0 | | |

Two caveats on this bound: against the sibling mean the hardest sibling always comes out positive (the excesses within
an act roughly offset), and the pooled P(kill | survived) overstates what marginal survivors, who would leave the
fight at low HP, go on to achieve. The sibling bound also overstates intrinsic-difficulty gaps. Against the expert (§701 / §729: Baalorlord dies per fight at
Awakened One 3.0%, Donu & Deca 1.0%, act-3 bosses 2.3%) our Awakened One rate is 7.6× his, Donu & Deca 8.6×, act-3
bosses overall 6.0×: relative to the expert, Awakened One is no worse than its siblings. Bringing it to the act-3
ratio (18.1% per fight) gives ≈ +1.0 pp, to Donu's ratio 0. **So Awakened One is the only cluster whose bound reaches
+1 pp, between +1.0 (expert-relative, small expert samples) and +3.1 pp (sibling).** The Heart and the act-2 hallways
have no sibling; the Heart is covered by the Heart-entry work (§724, #935), the act-2 hallway deaths are gap 4 below.

**Luck vs state** (`aivat_luck.py`, §676 guard): of the real Awakened One deaths, 69% die again in ≥ 3 of 4 redraws
from the same entry state (Heart 67%, Hexaghost 64%, Time Eater 55%, Collector 51%, Slime Boss 52%, act-2 hallways 37%,
S&S 18%); only 6% of Awakened One and Heart deaths survive all four redraws. Entry-state variance is 68% of Awakened One
outcome variance (Heart 59%, Collector 49%). Inference: Awakened One and Heart deaths are decided by the entry state
under production play; the open question is whether the state is lost (deck/HP) or the play is (a stronger player
would win it), which a replay with a stronger player answers and these data cannot.

**Deck signature** (`decksig.py`, seed-grouped CV): deck and relics predict death beyond entry HP, max HP, potions
and gold at the Heart (log-loss gain +0.069 [+0.059, +0.079], GBM), Hexaghost (+0.044), Awakened One (+0.032), Champ
(+0.051), Collector (+0.024), Time Eater (+0.024); not in hallways or act-2 elites (deaths there are HP only). The
out-of-fold weakest-deck quartile carries 50% of Awakened One deaths (per fight 46% vs 6% in the strongest quartile)
and 61% of Hexaghost deaths. Recurrent signals across bosses: Strikes left in the deck and curses are risky, Dead
Branch, Feel No Pain/Corruption, Demon Form/Inflame and Barricade protective. With ≥ 80% entry HP, Heart death is
16% with 0-1 Strikes vs 27% with 4+ (act-2 bosses 6% vs 12%; `strikes.py`). Observational: a refined deck also marks
a strong run, so this is a hypothesis for the phase-3 prior (removal/transform value), not a rule.

**Gate candidate (only one): Awakened One, play vs state.** Replay recorded Awakened One entries of the two newest
campaigns (§727 A, §720 base; 1,001 entries) with `one_combat fightreplay` under the production environment and under
a flat 40k boss budget (learned stop off), 2 CRN copies per arm. Cost from §698's 51 CPU-s per production copy and
§718's 7.7× at 40k: ≈ 512 entries × 2 × (51 + 390) s ≈ 125 core-h (all 1,001 ≈ 245); a 16-entry smoke fixes the real
cost. Decision: a ≥ 4 pp lower per-fight death at 40k marks it planning-limited (next: priced boss budget, whole-run
A/B); otherwise Awakened One is deck/evaluation-limited and goes to phase 3/5 as a named metric. Prior: §718 found no
gain from 40k on Baalorlord's boss states (Awakened One +2.0 HP, n.s.), so a null result is the more likely outcome;
the replay is on our own, weaker states, which §718 did not cover.

**Result (§743, 304 entries × 3 paired copies, ~128 core-h):** NOT_PLANNING_LIMITED. Flat 40k loses 1.2 pp fewer
Awakened One fights than production (25.0% → 23.8%, CI −2.9 to +0.3 pp) at 7.5× CPU; ≈ +0.26 pp Heart kills per run.
Where production died in all 3 copies, 40k still died in 96%. Awakened One deaths are deck/state-limited
([RESULT](../../experiments/evidence/ao_replay_40k_20261101/RESULT.md)).

**X4 gate sizes** (`x4_power.py`, 12 near-null arm pairs, |ΔHeart| < 3 pp, 11,264 pairs): paired SD per seed pair
0.421 for Heart kill (pairing correlation +0.51), 0.262 for reaching act 2, 0.436 act 3, 0.464 act 4. Pairs for a 95%
half-width of ±1.0 / ±1.5 / ±2.0 pp: 6,821 / 3,032 / 1,706 (Heart). MDE (80% power) 3.7 pp at 1,024 pairs, 1.8 pp at
4,096. The SD falls when arms diverge late: combat-only changes 0.34-0.39 (§676 A-C, §661 M-MS), early OOC changes
0.43-0.48. A change that only touches one fight (e.g. Awakened One play) is far cheaper to gate by fight replay than
by whole runs.

## What this means for the roadmap

The decision-level ("structural") gaps that existing games still show are each ≤ ~1 pp plausible, about 2-4 pp in
total, below the roadmap's +4 to +8 pp for phase 1. Most of the death mass sits at bosses in states depleted by
combat HP loss, which §701/§711 attribute to combat play (1.4-3× the expert's HP loss on the same fights). Inference:
the next large gains are in combat (run-aware leaf, boss planning, phase 3-5); the Awakened One diagnostic is the one
cheap item with a > 2 pp ceiling.

Gate costs use 826 s per production game (§727): a paired whole-run A/B costs ≈ 0.46 core-h per seed pair (1,024
pairs ≈ 470 core-h, MDE ≈ 3.5 pp; 4,096 pairs ≈ 1,880 core-h).

## Obvious-mistakes pilot (2026-11-15, issue #1056, §TBD)

20 of §782's G16 + mb4 games replayed with PPO logits and critic at every out-of-combat decision and a fresh 64k search
at every combat root ([evidence](../../experiments/evidence/obvious_mistakes_pilot_20261115/RESULT.md)). Top 50 flags
read by hand: Bug 2, misconception 20, defensible 17, open 11. The flagged mistakes are mostly out of combat and are
disagreements between the PPO actor and its own critic: Corruption takes (critic -0.039 on average), runic boss relics
(-0.05), smith instead of rest before the Act-1 boss at 59-81 % HP, elites at <= 50 % HP. Combat search leaves a move
its own tree rates >= 1 point better at 11 of 6,897 roots, 10 of them sequential-halving noise; the eleventh is a
design gap (Gumbel candidates ignore inherited visits when legal actions > k). "Differs from a 64k search" alone is no
mistake signal (38 % of roots, almost all order-equivalent). The critic is not screen-invariant and not bounded, so
critic drops need a transition baseline. Open: paired probes for each pattern.

## Open questions

- ~~Is Awakened One planning-limited or deck-limited?~~ Deck/state-limited (§743: 40k −1.2 pp [−2.9, +0.3] per fight).
- Which carried relic counters besides Incense matter at the Heart? (#922 labels, gate 2)
- Are there boss-specific deck needs the prior misses? (gate 3)
