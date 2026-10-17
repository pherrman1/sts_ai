# Potion prices by paired continuation at A20: result (§509, 2026-10-17)

Pre-registration: [PREREG.md](PREREG.md). Analysis: [analysis.json](analysis.json)
(`tools/analyze_potion_price_probe.py` at `9282628a`, which added the review's terminal-state filter,
labels and dropped-replicate count; the run binary is unchanged).

## Execution

- RUN_COMMIT `5dfabf90`, `one_combat` sha256 `16f41273…ac03` on both containers (byte-identical
  builds), same environment ([run_slice.sh](run_slice.sh)). Independent pre-launch review PASS.
- This thread: seeds 111110000–111110499, 241 seeds finished before the 3 h deadline. Worker W=1:
  111110500–111110999, 257 finished. No unit failed. Unstarted seeds (259 + 243) stay unused.
- Raw data on the share: `potion-price-probe/ppp-w00.tar.gz` (sha256 `5ab87bdc…4a99`),
  `ppp-w01.tar.gz` (`ba3a82d4…4958`), checked from a second extraction.
- 491 source seeds with an eligible state, 3,550 sampled states, 5,220 potion rows. 0 invalid rows.
  7 terminal states (the observer's post-run call, flagged in review) dropped. 0 bootstrap replicates
  without a positive HP slope.

## Result

Primary (`altFloor`, A20 floor model): **CONSISTENT_WITH_11**. Value of 1 HP 0.092 floors
[0.074, 0.111]. Pooled potion price **9.9 HP-eq [7.9, 12.3]**. The lower bound is below 8, so the
range §385 measured (2-8) is not excluded.

| Value column | Label | Pooled HP-eq [95% CI] |
|---|---|---|
| altFloor (A20 floor, primary) | CONSISTENT_WITH_11 | 9.9 [7.9, 12.3] |
| floorValue (production A0 floor) | CONSISTENT_WITH_11 | 8.6 [6.7, 11.0] |
| won (public X2-B) | CONSISTENT_WITH_11 | 11.2 [8.7, 14.4] |
| altWon (A20 win model) | FORMULA_UNDERPRICES | 16.6 [12.0, 23.4] |

Per type (`altFloor`, descriptive, n ≥ 100; 27 types, so about one 95% CI in 20 misses by chance):

| Higher | HP-eq [CI] | Near zero or lower | HP-eq [CI] |
|---|---|---|---|
| Fairy in a Bottle (304) | 44.1 [33.2, 58.1] | Weak (243) | 0.6 [−10.9, 10.1] |
| Attack (216) | 21.1 [10.4, 32.5] | Block (164) | 0.6 [−10.2, 9.9] |
| Blood (161) | 18.0 [8.4, 29.1] | Swift (193) | −5.8 [−18.6, 4.5] |
| Skill (196) | 14.9 [7.0, 23.9] | Speed (191) | −0.9 [−14.0, 10.4] |
| Fear (194) | 13.6 [6.3, 22.4] | Essence of Steel (156) | −2.2 [−15.1, 6.9] |
| Power (261) | 13.3 [4.9, 23.8] | Liquid Bronze (125) | −1.2 [−17.0, 14.0] |

The rest (Colorless, Dexterity, Explosive, Strength, Energy, Fire, Duplication, Regen, Gambler's
Brew, Ancient) lie between 7 and 12. Flex, Blessing of the Forge, Elixir and Liquid Memories lie
between 2 and 6, all with wide CIs. Silver already scores the Fairy at 11 + 0.3 × max HP (about 35
at 80 max HP), consistent with 44 [33, 58].

## Interpretation

- Silver's flat 11 per potion is about right **on average** at A20 under the current policy. The data
  doesn't support raising or lowering it.
- Played out for 3 fights and then valued, X2-B also gives about 11. **Inference:** §385's low X2-B
  prices (2-8) came from pricing the post-fight state statically, not from playing the potion; the
  continuation is what puts the value back in.
- The spread across types is large. Several defensive or one-turn buff potions price near 0, and
  attack/card-generating potions price at 15-21. **Inference:** a per-type potion weight could matter
  more than the level. That needs a pre-registered fight-level test; a few types could be outliers by
  chance.
- Limits: priced at battle start, not at the end of the previous fight. Known-RNG continuation. The
  A0-trained V4 policy at A20. 3 fights ahead then a model, so value beyond that horizon depends on
  the floor model.
