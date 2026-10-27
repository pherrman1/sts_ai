# Combat HP-loss gap vs Baalorlord: existing-data diagnostic (issue #889, 2026-10-27)

Question: why does the A20 bot lose more HP than Baalorlord in elite and boss fights (#865 §688), and is potion
management a plausible contributor, or is it deck/resources, encounter mix, or combat decisions? Existing data only:
no new games, no code or default change. Base `ed2dcb2` (main).

## Data and provenance

- **Bot:** §683 MAP arm (today's map-only OOC default, run commit `772df240`, pre-§682 Act 4 with the learned stop),
  1,024 seeds, the unit tars on the share `ooc-map-only-search/units/*.tar`, `MAP-<seed>.ctm.jsonl.gz`: one
  `combat_transition_v1` row per real fight, 24,017 fights, 769 combat deaths (of 771 lost runs).
- **Expert:** the 676 Baalorlord A20 Ironclad `.run` files of #865 (share `expert-replay/baalorlord_ironclad_raw/`);
  all 676 SHA-256 match `../expert_play_audit_20261026/baalorlord_raw.sha256`. 17,356 logged fights
  (`damage_taken`), 246 deaths. Builds 2020-12-13 to 2026; 327 runs use the RNG Fix mod (fine here: real games).
- **#868 replay:** the 329 X/B unit tars on the share `expert-replay-ab/units/*.tar` (run commit `84d2f15d`).

Scripts (all `python3 -I`): `bot_fights.py <units_root> <repo> bot_fights.jsonl` and `expert_fights.py <raw_dir>
expert_fights.jsonl` (one row per fight), `analyze.py bot_fights.jsonl expert_fights.jsonl result.json` (all tables;
markdown in [tables.md](tables.md)), `replay_deaths.py <xr_units> expert_fights.jsonl <repo> replay_deaths.json`.

**Measure.** Net HP lost per *won* fight = entry HP − HP after the fight. Bot: ctm `pre.curHp − post.curHp`
(post is after end-of-combat heals such as Burning Blood, before rewards). Expert: `current_hp_per_floor` of the
previous floor minus this floor, with fruit relics picked up on that floor (Strawberry 7, Pear 10, Mango 14) added
back. Not the expert's `damage_taken.damage`: reconciling it with per-floor HP shows it is damage *received*
(in-combat heals not netted, before Burning Blood), so it is not comparable. Deaths are reported separately as
death per fight. CIs: run-clustered bootstrap of bot − expert (1,000 resamples).

## 1. Observability audit

| quantity | expert `.run` | bot ctm row |
|---|---|---|
| potion uses per floor (count) | `potions_floor_usage`, all 676 runs; 5,401 uses, 98.7% on floors with a logged fight | lower bound `held at entry − held after` (39 fights gained a potion mid-combat: Alchemize / Entropic Brew) |
| which potion was used | `potion_use_per_floor` (Run History Plus), 538 runs; per-floor counts agree with the vanilla field in 484 | potion ids before/after |
| turn / timing / target of a use | **not logged** | not in the row (search records only) |
| discards | `potion_discard_per_floor`, 538 runs | not in the row |
| potions held at combat entry | **reconstructed**: obtained + alchemize/brew + shop − used − discarded, slot cap 2 (+2 Potion Belt); consistent in 488 of 538 runs (never negative or above cap), unknown in the other 188 | exact |
| fight identity, turns | `damage_taken.enemies`, `.turns` | encounter id; turns not in the row |
| entry HP / max HP | previous floor's HP (floor 1: not logged) | exact |
| deck, upgrades, relics at entry | **not logged per floor**; deck size proxy from picks + shop + events − purges, upgrades from smiths + events (proxy − final deck: median 0, within ±1 in 74% of runs; Neow cards, transforms, bottled cards missing); relic counters not logged | exact |

Potion gains and discards are never counted as uses. Expert "uses" can include a few out-of-combat drinks on
fight floors (72 of 5,401 uses are on non-fight floors, so these are rare).

## 2. HP loss and deaths by act and room (acts 1–4)

| act-room | fights bot / exp | death per fight bot / exp | net HP per won fight bot / exp | bot − exp [95% CI] | entry HP / max |
|---|---|---|---|---|---|
| 1 hallway | 6,082 / 3,771 | 0.002 / 0.003 | 0.2 / 0.6 | −0.4 [−0.7, −0.2] | 0.80 / 0.73 |
| 1 elite | 2,502 / 1,715 | 0.016 / 0.014 | 13.0 / 9.5 | +3.5 [2.7, 4.1] | 0.78 / 0.68 |
| 1 boss | 968 / 638 | 0.084 / 0.060 | 19.3 / 11.3 | +8.0 [6.5, 9.5] | 0.72 / 0.55 |
| 2 hallway | 4,401 / 2,976 | 0.010 / 0.005 | 2.6 / 1.7 | +0.9 [0.4, 1.4] | 0.78 / 0.75 |
| 2 elite | 1,769 / 1,371 | 0.036 / 0.022 | 10.1 / 5.6 | +4.5 [3.4, 5.7] | 0.83 / 0.73 |
| 2 boss | 771 / 548 | 0.143 / 0.055 | 23.6 / 11.2 | +12.4 [10.1, 14.7] | 0.87 / 0.74 |
| 3 hallway | 3,290 / 2,643 | 0.008 / 0.002 | 0.1 / −0.9 | +1.0 [0.5, 1.6] | 0.86 / 0.88 |
| 3 elite | 1,593 / 1,363 | 0.031 / 0.011 | 6.1 / 2.2 | +3.9 [2.7, 5.1] | 0.87 / 0.86 |
| 3 boss | 1,099 / 980 | 0.128 / 0.023 | 13.0 / 8.8 | +4.2 [2.3, 5.9] | 0.83 / 0.84 |
| 4 Shield & Spear | 441 / 472 | 0.034 / 0.017 | 20.0 / 9.3 | +10.7 [8.1, 13.4] | 0.99 / 0.98 |
| 4 Heart | 426 / 464 | 0.406 / 0.084 | 41.3 / 20.1 | +21.2 [16.9, 25.3] | 0.77 / 0.88 |

Death-per-fight differences (bot − exp, 95% CI): act-2 boss +0.087 [0.058, 0.121], act-3 boss +0.105 [0.083, 0.128],
Heart +0.32 [0.27, 0.38]; act-1 elites and bosses are within noise.

**Every** elite and boss encounter shows the gap ([tables.md](tables.md), second table): per won fight, bot − exp:
Nob +4.1, Lagavulin +2.7, Sentries +3.6, Hexaghost +8.8, Slime Boss +6.3, Guardian +9.5, Book +2.2, Gremlin Leader
+6.5, Slavers +4.9, Automaton +13.7, Champ +10.5, Collector +13.7, Giant Head +3.5, Nemesis +3.8, Reptomancer +4.3,
Awakened One +6.1, Donu & Deca +2.3 (CI [−0.7, 5.1]), Time Eater +4.4. Per-fight death rates are highest relative to
the expert at Awakened One (0.225 vs 0.030), Collector (0.214 vs 0.066), Donu & Deca (0.079 vs 0.010) and the Heart.

**Act-2 boss:** not one encounter (Automaton, Champ and Collector all +10 to +14), not encounter mix (bot per-boss means
reweighted to the expert's boss mix: 23.9 vs unweighted 23.6; expert 11.2), not entry HP (the bot enters healthier,
0.87 vs 0.74 of max).

## 3. Potions (availability and use, as far as observable)

| | act-1 boss | act-2 boss | act-3 boss | act-3 elite | Heart |
|---|---|---|---|---|---|
| potions used per fight bot / exp | 0.96 / 0.57 | 0.89 / 0.47 | 0.59 / 0.12 | 0.52 / 0.27 | 0.86 / 1.94 |
| carries ≥ 1 potion at entry bot / exp | 0.88 / 0.95 | 0.86 / 0.97 | 0.71 / 0.99 | 0.84 / 0.98 | 0.66 / 0.99 |
| uses ≥ 1 if carrying bot / exp | 0.78 / 0.52 | 0.74 / 0.41 | 0.62 / 0.10 | 0.49 / 0.23 | 0.94 / 0.95 |

Bot counts are lower bounds; expert inventory is from the 488 consistent runs. Potions held entering the Heart:
bot 0.97 of 2.38 slots, expert 2.19 of 2.47. Within carriers, the HP gap stays (elites 9.4 vs 6.2, bosses 17.5 vs
9.8 per won fight).

So the bot does **not** under-use potions in elite and boss fights: it drinks more per fight in every act-1-3
category and still loses more HP. The expert drinks rarely through act 3 (one boss fight in ten) and arrives at the
Heart with two potions, then drinks ~2 there. What the logs cannot show is *how well* each potion was used (turn,
target, which of several), so potion timing quality is not identifiable from these data.

## 4. Entry-state proxies and narrow strata

- **Entry HP:** the bot enters elites and bosses healthier in acts 1-2 (it rests more, §688). Within entry-HP bins the
  gap stays: at 85-100% HP, elites 11.7 vs 6.4, bosses 19.4 vs 10.7; at 70-85%, 10.6 vs 7.3 and 20.2 vs 10.5. Below
  50% HP net loss is equal (survivors only) but the bot dies 3-4x as often (elites 0.17 vs 0.06, bosses 0.37 vs 0.10).
- **Deck size (expert: proxy):** the gap does not shrink with deck size in any act (e.g. act-2 bosses at 21-25 cards
  26.6 vs 12.0, at 26-30 23.8 vs 11.9; act-3 elites at 31+ cards 5.7 vs 1.1).
- **Near-starter decks:** act-1 elites on floor ≤ 8 with ≤ 13 cards (11 starting incl. Ascender's Bane) and ≤ 1
  upgrade: Nob 16.4 vs 5.7 (n 32 / 23, diff CI [3.3, 17.9]), Lagavulin 25.0 vs 11.1 ([7.7, 20.3]), Sentries 27.4
  vs 11.5 ([6.0, 24.6]). With nearly the same cards the bot loses 2-3x the HP. Caveat: the expert proxy misses Neow
  cards, and both sides select which early elites to fight.
- **Not recoverable for the expert:** card identity quality at entry beyond the proxy, relic counters (Pen Nib, Nunchaku,
  Sundial ...), bottled cards, potion inventory in the 188 runs without consistent logs, and anything turn-level.

## 5. #868 replay deaths (same seed, the expert's exact deck)

In #868's X arm the bot replays the expert's out-of-combat decisions on his seed while every offer matches, so up
to the death floor it holds his exact deck, relics and potion rewards, and faces the same encounter; it plays its own
combats (own HP and potion use since floor 1). Of the 116 X games with no replay stop, 22 died on the same floor
where the expert died, and 6 are Emerald-key-defect games that ended alive. **88 died on a floor the expert
survived** (`replay_deaths.json`): 3 in events, 85 in fights (acts 1/2/3 = 54/27/4). Fights: Lagavulin 13,
Guardian 11, Hexaghost 10, Slime Boss 6, Nob 6, Slavers 5, other act-2 elites 8, hallways 14.

The expert entered those 85 fights at a median 59% of max HP (20 of them below 40%) and lost a median 13 HP net
(24 received), used a potion in 48 of them, and received damage ≥ 50% of max HP (damage_taken, not net HP lost) in only 16. Representative cases:
- act-1 Lagavulin, run 1665608474 floor 7: the expert entered at 28/75 HP, drank one potion and lost 3; run
  1632257093 floor 10: entered at 17/75, two potions, lost 7 net (15 received).
- act-1 Guardian, run 1693933695 floor 16: the expert entered at 21/75, two potions, lost 8 net (29 received); the
  27 act-1 boss deaths (Hexaghost 10, Guardian 11, Slime Boss 6) had expert entries of 18-65 HP.
- act-2 Book of Stabbing, runs 1644527044 and 1637095905 floor 23: the expert entered at 35/89 and 40/75 and lost
  8 and 13 net.
B (the bot alone) on these 88 seeds killed the Heart 20 times and died at or before that floor 18 times.

Attribution limits: replay fidelity is not the cause up to these floors (the replay stops at the first offer that
differs, so the deck is the expert's), and the encounter is the same (vanilla seeds reproduce 100% of encounters,
#868). The X games did not write per-fight records, so the bot's entry HP and potions at the death fight are unknown:
"entered lower because earlier fights cost more" and "lost more in this fight" cannot be separated, but both are
combat. Changed combat RNG (the bot's different play earlier) and engine fight mechanics cannot be excluded case by case.

## Ranked explanations (by evidence)

1. **Combat play, potions included, loses more HP on the same kind of fight.** Supported by: the gap on all 18
   act-1-3 elite/boss encounters; it persists at matched entry HP and deck-size strata; 2-3x with near-starter decks;
   85 combat deaths holding the expert's exact deck on fights he survived, often from lower HP.
2. **Deck/resource quality:** plausible part of the act-2/3 gap (expert skips more, 34-card decks), but it does not
   explain the act-1 near-starter gap or the deck-size strata; its share is not identifiable from these logs.
3. **Potion under-use: refuted** as a cause (the bot drinks more per elite/boss fight). Potion **allocation** across
   the run differs: the bot spends through act 3 and enters the Heart with half the potions; plausible contributor to
   Heart losses only. Potion use quality is not observable.
4. **Encounter mix and entry HP: ruled out** as explanations of the per-fight gap.
5. **Engine fidelity of fight mechanics:** not testable here (expert combat actions are not logged). Hallway fights
   are about equal (act 1 bot better), which argues against a large global simulator bias, not against
   elite/boss-specific mismatches.
6. **Survivor selection:** net loss is over won fights only; the bot loses more fights, which removes its worst
   outcomes, so the won-fight gap, if anything, understates the difference.

## Is a paired combat experiment warranted?

Yes: existing data point at combat, but cannot size it on identical states. **Cheapest discriminating design
(not run; needs Philipp's go and a pre-registration):** matched expert combat-entry replay on the 347 vanilla-RNG
seeds. Extend `expertreplay` to (a) sync HP, max HP and the potion inventory to the log at each combat entry inside
the exact-replay prefix (the probe already syncs HP and gold per floor; potions from `potion_use_per_floor` where
consistent, else unknown -> skip the fight), and (b) write one per-fight record (entry state, net HP, death, potions
used). Silver (today's default) plays each acts-1-2 elite and boss fight K = 4 times from the synced entry: replicate
0 with the logged combat seed (the expert's deal; the search sees only public information under `STS_FAIR=1`),
replicates 1-3 with redrawn combat streams; the run continues on the log's next-floor HP. Compare mean net HP and
death with the expert's single outcome, clustered by run, by encounter. Size: vanilla runs have 879 + 327 act-1 and
659 + 270 act-2 elite/boss fights before fidelity truncation (~85% / ~60% replayable), so ~1,600 fights x 4 ≈ 6,400
Silver fights. Optional decomposition arm: the same entries with potions removed (bot and expert inventory), to size
the potion share. Irreconstructible: relic counters, bottled cards, Neow sub-choices in old logs, and RNG Fix runs.

**Minimal missing instrumentation** (useful even without the new run): `expertreplay` writes no per-fight records,
so the 329 existing X games cannot show entry HP or HP lost per fight; heartoutcomegen's ctm row has the right
fields.

Seeds: none (existing games only).
Knowledge impact: ledger entry only; no code, model or default change.
