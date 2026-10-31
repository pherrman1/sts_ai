# A20 loss mining: where production runs die and what is avoidable

Last verified: 2026-10-31 against 2,816 recorded production A20 games (§TBD, [evidence](../../experiments/evidence/loss_mining_20261031/README.md)).

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

## What this means for the roadmap

The decision-level ("structural") gaps that existing games still show are each ≤ ~1 pp plausible, about 2-4 pp in
total, below the roadmap's +4 to +8 pp for phase 1. Most of the death mass sits at bosses in states depleted by
combat HP loss, which §701/§711 attribute to combat play (1.4-3× the expert's HP loss on the same fights). Inference:
the next large gains are in combat (run-aware leaf, boss planning, phase 3-5); the Awakened One diagnostic is the one
cheap item with a > 2 pp ceiling.

Gate costs use 826 s per production game (§727): a paired whole-run A/B costs ≈ 0.46 core-h per seed pair (1,024
pairs ≈ 470 core-h, MDE ≈ 3.5 pp; 4,096 pairs ≈ 1,880 core-h).

## Open questions

- Is Awakened One planning-limited or deck-limited? (gate 1)
- Which carried relic counters besides Incense matter at the Heart? (#922 labels, gate 2)
- Are there boss-specific deck needs the prior misses? (gate 3)
