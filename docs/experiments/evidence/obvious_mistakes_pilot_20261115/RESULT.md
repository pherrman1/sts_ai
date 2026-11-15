# Obvious-mistakes pilot (issue #1056): 20 G16 + mb4 games, first catalogue

Date: 2026-11-15 (cloud, one container, 4 cores). Ledger: §TBD. Descriptive only: no gate, no default change, no new
seeds. Every finding below is a hypothesis about a decision, not ground truth; known-RNG replays are used for diagnosis
only (ADR-0002), never as a metric.

## Question

Issue #1056 asks for a structured review of "obvious mistakes" in today's strongest games: flag decisions
automatically, render each with state, alternatives (net and search values) and a category (bug, misconception,
defensible), and see whether the flags point to fixable causes. This pilot does that on 20 games.

## Games

20 of §782's 1,024 G16 games (§775 arm: Gumbel root k 16, max backup 4, 16k simulations per root, Heart 40k;
net-0420 out of combat at temperature 0; A20 Ironclad; seeds 111378256-111379279). Strata from §782's own outcomes:
6 Heart kills and 14 deaths spread over Acts 1-4 (Act 1: 3, Act 2: 4, Act 3: 4, Act 4: 3, of them 2 at the Heart), drawn inside each stratum by sha256("issue1056-" + seed). The list is in `results/catalog.json` (field `seed`)
and in the per-game sheets.

## Method

- **Pass 1** (`replay.sh`, binary 112c0f3a = code ebd446b3, the §775/§782 binary): replay each game with §782's env and
  three read-only traces: `STS_OOC_DECISION_TRACE` (state before and after every out-of-combat step, every fight),
  `STS_OOC_HEART1_PPO_TRAJ` (logits, chosen option and critic value at every PPO decision) and
  `STS_SILVER_GUMBEL_STOP_TRACE`. **All 20 traces are identical to §782's own traces** (`analyze.py` checks this), so
  the replays are the same games.
- **Pass 2** (`ladder.sh`, binary 97aec5b5 = code ba705ab4, `one_combat silverazgen` with §775's arm via
  `../budget_ladder_roots_20261112/record_env.sh` and `STS_AZGEN_BUDGET_LADDER=64000`): the same games again (play is
  bit-identical with the ladder on), and at every searched combat root with two or more edges one extra fresh Gumbel
  k 16 + max backup 4 search at 64,000 simulations of the same root. Rows carry the wire state, every root edge (visits,
  max-backed Q, mean q, prior, semantic action), the played pick and the 64k pick. The 64k search's own Q values are
  not recorded, only its pick. About 4.3x a G16 game's CPU. Deaths first; at the time of writing 16 of 20 games are
  done (all 14 deaths, 2 Heart kills); the remaining 4 wins only add R candidates and are appended in a later commit.
- **Flags** (`analyze.py`, thresholds fixed before reading cases):
  - `ooc_drop`: an out-of-combat decision after which the critic falls by >= 0.02 before any fight. Ranked by
    `dv_adj` = drop minus the mean drop of the same screen transition over all 20 games, because the critic is not
    screen-invariant (below).
  - `fight_cost`: a fight that killed the run, or a won fight with HP-loss z >= 1.5 against §782's G16 norm for the
    encounter.
  - `death_chain`: the 8 out-of-combat decisions before each death.
  - `root_64k`: a combat root where the 64k pick differs from the played pick and the played 16k tree's own max-backed Q
    prefers the 64k pick by >= 1 Silver point, both edges with >= 256 visits. Smaller gaps are counted as
    order-equivalent.
  - `cap`: a fight of 20 or more turns or an abort.
- **Top 50** (`build_catalog.py`, selection fixed before reading): every fight that ended a run (D, 14), every
  root_64k (R, 11), the 6 won fights with the highest z >= 2.5 (F), and the 19 largest `dv_adj` drops with at most 2 per
  game (O). Each was then read by hand in its game sheet and given a category and a note (`notes.json`).

Categories: **Bug**, the engine or the search implementation does something the game or the design does not intend;
**Fehlvorstellung (misconception)**, rules are right but the net or the search values something wrong; **vertretbar
(defensible)**, no error on a closer look or not decidable from the trace; **offen (open)**, needs a paired probe.

## Flag counts (20 games, 16 with pass 2)

| flag | count |
|---|---:|
| ooc_drop | 292 |
| fight_cost | 43 (14 deaths) |
| death_chain | 65 |
| combat roots with a 64k pick | 7,447 searched roots in pass 2, 6,897 with a ladder search |
| 64k pick differs | 2,618 (38 % of ladder roots) |
| of those, 16k tree prefers the 64k pick by >= 1 | 11 |
| cap (>= 20 turns or abort) | 0 |

38 % of combat roots get a different pick from a 4x larger search, but in 2,607 of 2,618 the played tree's own
max-backed Q does not prefer the 64k pick by a point or more: order-equivalent moves (two Strikes in either order) or
search noise. "Disagrees with 64k" alone is not a mistake signal.

## Catalogue result

50 entries ([CATALOG.md](results/CATALOG.md)): **Bug 2, Fehlvorstellung 20, vertretbar 17, offen 11.**

| group | n | Bug | Fehlvorstellung | vertretbar | offen |
|---|---:|---:|---:|---:|---:|
| D (run-ending fights) | 14 | 0 | 7 | 0 | 7 |
| R (16k tree prefers the 64k pick) | 11 | 1 | 0 | 10 | 0 |
| F (costly won fights) | 6 | 0 | 0 | 4 | 2 |
| O (critic drop after an OOC decision) | 19 | 1 | 13 | 3 | 2 |

### Bug candidates (2)

1. **Gumbel candidate set ignores inherited visits** (R-111378476-F55-T5-d63). An Exhume choice with 19 legal options
   at k = 16: the reused tree already holds Feed with 8,234 visits and the highest max-backed Q (158 vs 149), but the 16
   candidates are drawn from Gumbel noise plus an almost uniform prior and Feed is not among them, so the search can
   never pick it. `SilverSearcher::searchGumbelRoot` ranks candidates by `noise * g + logit` only. Over 7,447 roots
   this is the only case with a gap >= 1 (19 roots had an inherited most-visited edge that was not played; all others
   have gaps <= 0), so the cost is small; the fix would be cheap (always admit the inherited best edge
   when n > k). Needs its own issue and an equal-CPU check before any change.
2. **Match and Keep: all 12 options have identical logits** (O-111378911-105, logit -0.572 for every option). The policy
   cannot tell the cards apart; likely the option encoding does not carry the card under each position. The option
   names in that row come from this pilot's renderer and are wrong for this event. Needs a look at the PPO option
   encoding for this event.

### Patterns behind the misconceptions

- **Smith before the Act-1 boss at middling HP.** At the F15 campfire the net smiths at 59-81 % HP (8 cases with
  44/75 to 59/80) and rests at <= 60 % (51/89, 53/89 and lower). Two of the eight smiths died to the boss (Slime Boss
  from 59/80, Hexaghost from 44/75); the others lost 14-33 HP there (50 -> 29, 50 -> 17, 55 -> 30, 55 -> 34, 44 -> 30,
  48 -> 20). Resting would have added about 20-24 HP. Whether the upgrade is worth that is not visible from the
  trace: this needs a paired probe (forced REST vs. SMITH on these exact states).
- **Elites at <= 50 % HP.** 8 elite fights entered at <= 50 % HP (Lagavulin at 30/89 with p 0.75, Nemesis at
  50/105, Slavers 36 -> 19, Slavers at 30/88, Gremlin Leader at 18/89 with p 0.59 then 8 HP into the Colosseum and dead,
  Slavers at 29/76, Book of Stabbing 35 -> 10, Sentries at 30/82).
- **Corruption: actor and critic disagree.** Over 386 card takes from rewards the critic changes by +0.000 on
  average; after the 15 Corruption takes it falls by 0.039 on average (worst -0.175), and the actor takes it with
  p 0.79-1.00. Reaper looked similar in single cases but is not a pattern (+0.006 over 10 takes).
- **Runic boss relics.** Picks of Runic Dome, Pyramid or Cube lower the critic by about 0.05 on average; other boss
  relics raise it by about 0.01. The actor takes a runic relic in 9 of 30 boss-relic choices. Both Heart deaths had
  Runic Dome; all 4 Heart fights without Dome were won, 2 of 4 with Dome were lost (n = 8: a hint only).
- **The critic is not screen-invariant.** With deck, relics, potions, HP and gold unchanged, the value still moves
  with the screen: REST -> CARD_SELECT -0.011 (n 51), EVENT -> MAP -0.018, REWARDS -> CARD_SELECT -0.038,
  BOSS_RELIC -> MAP across an act change -0.0115 (n 30). It is also not bounded to [0, 1] (values from -0.04 to 1.18
  occur). Critic drops must therefore be read net of the transition mean (done here) and are weak evidence on their
  own.
- **Potions.** One run-ending Nob fight drank Speed Potion and then played no Defend (the dex was wasted; 16k tree
  44.9 for drinking vs 44.7 for Bash, the 64k search picked Strike); one fight lost 30 HP with Essence of Steel unused.

### What did not show up

- No combat aborts, no fight at the 20-turn cap, no non-reproduced game.
- No engine bug in the 14 deaths. Two apparent ones were checked and are correct: Lizard Tail had already fired on
  F25 in the Giant Head death; a Flame Barrier status shown across turns was a rendering artefact (the status map keeps
  stale amounts after removal; the bits are the truth, now used).
- In 7 of 14 deaths no single combat decision stands out: the 16k tree's best lines are within a few points of each
  other and the state was already lost a turn earlier (Reptomancer: about 100 damage incoming at T1 with Snecko Eye, all
  lines below 2 points; Awakened One left at 2/320). The levers there are out of combat (deck, relics, route) or
  need paired probes with more search.

## Interpretation (inference)

- The "obvious mistakes" are mostly out of combat and are disagreements between the PPO actor and its own critic
  (Corruption, runic relics, smith before the boss, elites at low HP), not engine bugs. Which head is right is not
  decidable from the trace; each pattern is a candidate for a paired probe.
- Combat search rarely leaves a clearly better move on the table by its own values (11 of 6,897 roots), and 10 of
  those 11 are the expected noise of sequential halving (the higher Q sits on an edge eliminated early with fewer
  visits and an optimistic max backup). The one structural case is the candidate set ignoring inherited visits.
- With 20 games every frequency here has wide uncertainty; the patterns are hypotheses for targeted tests, not
  estimates.

## Follow-ups (each needs Philipp's go)

1. Paired probe REST vs. SMITH at the Act-1 boss campfire on the 8 smith states (and the §782 games with the same
   situation), with several continuations per state.
2. Issue: admit the inherited best edge into the Gumbel candidate set when legal actions > k; equal-CPU check.
3. Issue: Match and Keep option encoding in the PPO observation.
4. Paired probe Runic Dome vs. the alternative relic at the boss-relic screens (§782 has about 1,000 such screens).
5. Corruption: forced skip vs. take on the 15 states.
6. Run the same pipeline on more games once the probes say which flags carry signal.

## Files

- `replay.sh`, `ladder.sh` (passes 1 and 2), `analyze.py` (flags, sheets), `build_catalog.py` (top 50), `notes.json`
  (hand categories and notes).
- `results/CATALOG.md` (top 50 rendered), `results/catalog.json`, `results/candidates.json.gz` (all flags),
  `results/sheets/SEED.md` (each game in order: every out-of-combat decision with options, p and critic value; every
  fight with its played line and, where pass 2 exists, the 64k pick and both edges' 16k max-backed Q).
- Commands:
  `bash replay.sh BIN_DIR SRC_DIR OUT_DIR SEED` (SRC = §782's G16 files);
  `bash ladder.sh BIN_DIR OUT_DIR SEED`;
  `python3 -I analyze.py REP LAD SRC OUT` and `python3 -I build_catalog.py REP LAD SRC OUT notes.json`.
- Raw traces (12 MB gzipped) are not committed; they are on the project share under
  `obvious-mistakes-1056/` (`rep/` pass 1, `lad/` pass 2) and reproducible from the commands.

Cost: pass 1 about 2.5 core-hours (17:18-17:55 CET), pass 2 about 13 core-hours so far (from 17:56 CET, 4 cores).
