# Bot runs vs expert play (offline audit, 2026-10-26)

Experiment 2 of the 2026-10-26 deep-research report: describe, in game terms, where the A20 bot's out-of-combat
play deviates from an expert's, using existing games only. No new seeds, no code or default change.

## Data

- **Bot:** §683 (`ooc_map_only_search_20261024`), run commit `772df240`, 1,024 paired seeds × 3 arms, all complete.
  MAP (OOC MCTS at map roots only) is the arm that became the A20 default in #858; D searches every screen, OFF is
  student_sel behind the rule chain. Source: the verified unit tars on the share
  (`ooc-map-only-search/units/*.tar`), records `{arm}-{seed}.jsonl.gz` (heart1 public records per decision state)
  and `.ctm.jsonl.gz` (one row per real fight). Pre-§682 Act 4 (learned stop), so Act-4 numbers are not current.
- **Expert:** Baalorlord's run archive, profile 0 ("BaalorA20"), all 676 Ironclad A20 runs (2020-12 to 2026),
  raw `.run` JSON from `https://baalorlord.tv/runs/<id>/raw` (Spireblight route `run_raw_json`), fetched
  2026-10-26 ~20:50Z. Run ids in `baalorlord_ironclad_a20_run_ids.txt`, file hashes in `baalorlord_raw.sha256`
  (raw files not committed: third-party data). 675 of 676 played unchosen seeds; 5 runs abandoned.

Scripts: `bot_extract.py` (per-run metrics from the records), `expert_extract.py` (same from `.run`),
`compare.py` → `summary.json`, `cards.py` → `cards.json` (pick rate per card, acts 1-3, ≥100 bot / ≥40 expert
offers), `hploss.py` → `hploss.json`. Rerun: extract the §683 tars, then
`python3 -I bot_extract.py <tars_root> <repo> bot683.jsonl`, `python3 -I expert_extract.py <raw_dir> expert.jsonl`,
`python3 -I compare.py bot683.jsonl expert.jsonl summary.json`, `python3 -I cards.py ...`,
`python3 -I hploss.py <tars_root> <raw_dir> hploss.json`.

## Definitions

- Elites: map ELITE rooms fought (burning elite included, `?` rooms that turn into fights excluded); expert
  `path_per_floor == 'E'`. Per act, over runs that cleared that act; and over Heart-kill runs.
- Campfire choice: bot REST state followed by an UPGRADE select (smith), REMOVE select (Toke), else by the next
  state: ruby key gained (recall), HP up (rest), upgrades up (smith), relic count up (dig), else lift/other.
  Expert `campfire_choices.key`. HP = HP on arriving at the campfire (expert `current_hp_per_floor[floor-2]`).
  Acts 1-3 only.
- Card reward skip: one reward = consecutive REWARDS states with the same offer; skipped if no offered card id
  was added to the deck by the next state. Expert `card_choices.picked == SKIP` (Singing Bowl counts as skip).
- Removals: deck shrinks between consecutive states (shop purge, events, Toke, Empty Cage ...); expert
  `items_purged`.
- Killer: the fight a lost run died in (`ctm` row with combatOutcome 2, else last fight); expert `killed_by`.

## Result (bot = MAP arm; D and OFF agree within ~1 pp on every row below)

| | Bot MAP | Expert | Verdict |
|---|---|---|---|
| Heart kill | 24.7% (253/1,024) | 62.9% (425/676) | |
| Death by act (of runs reaching it) 1/2/3/4 | 13.4 / 25.5 / 33.3 / 42.6% | 11.3 / 13.5 / 8.9 / 10.0% | gap from Act 2 on |
| Elites per cleared act 1/2/3 | 2.50 / 2.20 / 2.66 | 2.58 / 2.42 / 2.68 | **no deficit** (Act 2 −0.2) |
| Elites acts 1-3, winners (median / mean) | 8 / 7.84 | 8 / 7.81 | same |
| Campfire acts 1-3: smith / rest / recall | 46.1 / 40.1 / 9.0% | 71.9 / 13.1 / 10.5% | **rests 3× as often** |
| Rest share at 40-60% HP | 74.5% (n 1,318) | 13.3% (n 1,107) | |
| Rest share at 60-80% HP | 42.2% (n 1,807) | 4.5% (n 1,161) | |
| Rest share below 40% HP | 89.6% | 46.4% | |
| Median HP fraction on arrival at a campfire | 0.72 | 0.68 | bot arrives healthier |
| Card reward skip, all / winners | 12.2 / 12.8% | 29.6 / 30.4% | **skips 2.4× less** |
| Skip by act 1/2/3 (winners) | 6.4 / 15.2 / 16.5% | 14.7 / 34.0 / 41.4% | |
| Final deck, winners (median) | 40 | 34 | +6 cards |
| Strikes / Defends left, winners | 2.04 / 2.62 | 1.22 / 3.04 | |
| Removals per winning run | 2.51 (Strike 388, Defend 66) | 2.60 (Strike 688, Defend 58) | same pattern |
| Ruby key: median floor; act 3 share (winners) | 49; 93% | 44; 89% | |
| Sapphire key: act 1/2/3 (winners) | 20 / 43 / 37% | 12 / 22 / 66% (n 339 logged) | bot takes it earlier |
| Emerald key median floor (winners) | 23 | 24 (n 319 logged) | same |
| Top killers, % of all runs | Heart 16.9, Awakened One 8.6, Collector 5.2, Hexaghost 4.5 | Heart 5.8, Hexaghost 3.0, Slavers 2.5, Collector 1.9 | |

Card picks (`cards.json`, acts 1-3, pick rate given offered): the bot takes far more often Metallicize (73 vs 16%),
Havoc (50 vs 6%), Reaper (98 vs 53%), Clothesline (29 vs 7%), Spot Weakness, Inflame, Corruption, Ghostly Armor,
Pommel Strike, Intimidate, Blood for Blood, Anger; far less often Whirlwind (1.6 vs 34%), Bloodletting (9 vs 37%),
Burning Pact (31 vs 59%), True Grit (12 vs 35%), Entrench (2.6 vs 23%), Double Tap (2 vs 18%), Rage (0.1 vs 16%).

## Checks of the report's expert numbers

- 676 runs, 63% kills: reproduced (62.9%).
- Median 8 elites in acts 1-3, 3 in Act 1 (winners): reproduced. "Never fewer than 2 in Act 1": **not** reproduced;
  9 winning runs (2.1%) fought one.
- Smith 68% / rest 18%: **not** reproduced; 71.9% / 13.1% over all runs, 71.8% / 11.4% for winners (acts 1-3;
  with Act 4 70.7% / 13.3%).
- Skip 28% of card rewards: close (29.6% all, 30.4% winners).
- ~34 cards, Strikes removed and Defends kept: reproduced.
- Death by act 11/14/9/10%: reproduced; abandoned runs are only 5 of 676, so they do not move it.

## Interpretation

- The report's experiment 4 premise (elite deficit) is **refuted** for the current stack: elite dose matches the
  expert in every act and among winners. Elite routing is not the visible deviation.
- The visible OOC deviations are (1) resting instead of smithing at medium HP, (2) taking a card from almost every
  reward, giving +6 cards, and (3) specific card preferences. All three are the same in MAP, D and OFF, so they
  come from the prior (student_sel / heart1), and today's search does not change them.
- **Inference, not tested:** resting more may partly be the right answer for a bot whose combat loses more HP per
  fight; the HP-matched bins show the deviation, not that it is a mistake. Likewise, some card preferences
  (Whirlwind, Rage, Double Tap near zero) could reflect how our combat search plays those cards, not OOC judgement.
- Combat costs the bot more HP (`hploss.py` → `hploss.json`; net HP lost per won fight, Burning Blood heal
  included, acts 1-3; expert from `current_hp_per_floor`): elites 13.0 / 10.1 / 6.1 vs 9.3 / 5.3 / 1.9 per act,
  bosses 19.3 / 23.6 / 13.0 vs 11.3 / 11.2 / 9.0, hallway fights about equal. So part of the extra resting pays
  for extra combat damage. This is confounded by deck strength (the expert's decks are better by Act 2), so it
  does not split combat skill from deck quality.

Seeds: none (existing games only).
