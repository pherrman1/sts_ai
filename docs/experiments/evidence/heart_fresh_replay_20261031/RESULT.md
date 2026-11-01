# Result: fresh Heart replay at production search (2026-10-31)

**Verdict (pre-registered, `analyze.py`): IN_GAME_ARTIFACT.** Rebuilt fresh at production Act-4 search, the
perturbed children win the Heart as often as their controls. The −10.6 pp gap from the game itself does not reproduce.

Campaign: 240/240 units verified (`verify_campaign.py`: MISSING 0, BAD 0, duplicates 0, run ff092676, DONE 16/16), 16
workers, 19:55-20:52Z. Every unit has 2 valid rows and printed the production log lines. Results are in
[results/result.json](results/result.json).

| | fresh (production search) | in game (pilot) |
|---|---|---|
| Controls (60 states × 2 fights) | 66.7% | 75.0% |
| Children (180 states × 2 fights) | 66.4% | 64.4% |
| Children − control, per entry, seed-clustered | **−0.3 pp [−6.4, +5.6]** | −10.6 pp [−19.4, −1.7] |

- **Where the in-game gap comes from.** It sits in the controls, not the children:
  - The in-game control beats its fresh replay by +8.3 pp [−0.9, +18.3].
  - The in-game children match their fresh replays, −1.9 pp [−7.8, +3.9].
  - The difference-in-differences is −10.3 pp [−20.0, −0.6].
- **Per operator** (fresh child − fresh control, n children, 180 in total, no CIs, exploratory):
  - relic_add +9.5 (21), unupgrade +5.3 (19), max_hp +5.0 (10), relic_counter +5.0 (10).
  - card_remove +2.9 (17), upgrade +2.9 (17).
  - hp 0 (18), potion_remove 0 (9), relic_swap 0 (7).
  - potion_add −3.8 (13), relic_remove −10.0 (15), card_add −11.1 (9), gold −16.7 (15).
  - The gold children are not identical to their controls at the Heart: their paths diverge after the extra gold
    (different shop buys or relics). The replay drops gold itself.
- **Check against the weaker search.** The earlier learned-stop replay gave −3.3 pp [−8.3, +1.7], controls 64%.
  Both regimes agree that the fresh gap is about 0.

## Reading
At equal Heart-entry states, the perturbed children are not weaker. The pilot's sign anomaly came from the in-game
control winning its Heart more often than the same state does when rebuilt.

Remaining candidates, none of them tested here:
1. **Noise.** The in-game control is one fight per entry, and the +8.3 pp CI touches 0.
2. **State the replay drops.** Gold enters the g7f_E prior, card misc too. The in-game control carries it, the replay
   does not. But the children carry it in game too.
3. **Something the in-game control shares with run 1 but the children do not.** The control replays run 1 byte for
   byte. One example would be Silver's tree reuse across fights or within the Heart, which only matches exactly on the
   unperturbed path. This is less likely, though: run 1's redrawn unperturbed forks of the same entries,
   which leave that path, also won 70.7% in game (§726).

So the perturbation effects on Heart win are not evidence against V_A4's causal signs. A re-scoped check of candidate 3:
- Replay the controls in game with tree reuse forced off.
- Or play the Heart in game twice on a fresh battle seed.

Caveat: the replay does not carry gold or card misc. Bottled cards are carried (61/240 states).
