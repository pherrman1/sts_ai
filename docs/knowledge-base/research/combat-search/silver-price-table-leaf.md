# Silver price-table leaf (research, default off)

Status: research flag `STS_SILVER_PRICE_TABLE_LEAF`, off by default (leaf plan stage 0, thread B, 2026-11-05).
Evidence and model provenance: [silver_price_table_leaf_20261105](../../../experiments/evidence/silver_price_table_leaf_20261105/README.md).
Stage C pre-registration (frozen, run 2026-11-05, INCONCLUSIVE): [PREREG-stageC.md](../../../experiments/evidence/silver_price_table_leaf_20261105/PREREG-stageC.md).

## Stage C result (2026-11-05, §TBD)
INCONCLUSIVE: Heart kill at S&S → Heart over 1,021 states T − D +1.59 pp [−0.05, +3.23] (97.5%), TA − D +1.25.
On Incense states the table recovers most of §724's term (+4.5 vs +5.9 pp); on states without Incense Burner it
loses −2.4 pp (more potions and HP spent in S&S). The flag stays research-only
([RESULT](../../../experiments/evidence/silver_price_table_leaf_20261105/stagec/RESULT.md)).

## Why
PPO critics fail as Silver's combat leaf (§747 heart1, §755 LONG_B): they get the level of a state right but not its
1-3 HP differences. Models fitted on causal paired labels do price single changes (§746 model A beats Silver's leaf on
paired squared error). Calling such a model at every leaf inside the tree is too slow and puts the model's noise into
every comparison, so the leaf uses it through a **price table**: the model is evaluated once per fight, on perturbed
copies of the fight-start state, and the search only reads the resulting prices.

## How
Code: `apps/one_combat/silver_price_table.{h,cpp}` (features, model, table build, flag),
`SilverPriceTable` and the victory branch of `SilverSearcher::evaluateEndState` (`src/sim/search/SilverSearcher.cpp`),
hook `setNativeSilverPriceTableBuilder` (`NativeSilverBackend`).

1. **Flag.** `STS_SILVER_PRICE_TABLE_LEAF=a746[:ENC,...][:anchor]` or `<model>.trees:ENC,...[:anchor]`; `a746` defaults to Shield &
   Spear (model A is a Heart-entry model, so the fight before the Heart is the only fight where its target is the
   next state). one_combat installs the builder after the native Silver backend; any other binary fails the fight if
   the option is set. The spec, model paths and sha256 are recorded in the Silver leaf specification
   (`price_table_leaf`).
2. **Table build** (once per selected fight, at the first search root; whole-run fights and act4replay, not research
   overrides). The fight-start state is read from the `GameContext` in make_variants.py's names. The model scores:
   - HP knots at 1 HP, 10/25/50/75/100% of max HP and the start HP;
   - each held potion type removed (one copy);
   - max HP +5 (and −5 when HP stays below it);
   - gold −50 (when ≥ 50 gold);
   - every value of each held relic counter a fight can change (Happy Flower 0-2, Incense Burner 0-5, Ink Bottle 0-9,
     Lizard Tail 0-1, Nunchaku 0-9, Omamori 0-2, Pen Nib 0-9, Sundial 0-2).
   About 10-40 model rows per fight.
3. **Scale.** Prices are in units of the model's own 1-HP slope at the start HP: s = mean slope of the two knot
   segments next to the start HP, floored at a quarter of the 1-HP-to-max chord slope (a flat stretch at the start HP
   would otherwise make every price explode). A fight whose curve is flat everywhere keeps the default leaf (counted).
   This keeps `winBonus` (53) as the gap between a loss and a 1-HP win and the turn penalty (0.4 per turn) as 0.4 HP
   at the margin, as in the default leaf.
4. **Prices.** U(h) = 1 + (V(h) − V(1)) / s, piecewise linear through the knots (end segments extend it); potion of
   type t: (V(root) − V(root without one t)) / s, a type not held at the start (gained in the fight) at Silver's flat
   11; max HP and gold: the finite differences above / s per point; counter value v: (V(root with v) − V(root)) / s.
5. **Leaf.** On a victory: winBonus + U(post-fight healed HP) + Σ held potion prices + Σ counter prices at the end
   value (`BattleContext::updateRelicsOnExit`'s mapping) + max-HP and gold prices × change against the search root −
   turn penalty − Smoke Bomb and Parasite penalties. The loss branch, the final-fight leaf and every unlisted fight are
   unchanged. `STS_SILVER_INCENSE_HEART_PHASE`, if also set, adds §724's term on top (stage C's TI arm).
6. **Death saves.** Fairy in a Bottle and Lizard Tail are priced by the table, not by Silver's 0.3/0.6 × max HP and
   0.5 × max HP terms: the model sees the Fairy potion (`pot:FAIRY_POTION`, its removal price) and the Lizard Tail
   counter (`ctr:LIZARD_TAIL` 1 = unused, 0 = used). A death saved in the fight shows up as the consumed save plus the
   revive HP. Mark of the Bloom is a model feature, so no special case.

## Anchored win bonus (`:anchor`, stage C arm TA)
`STS_SILVER_PRICE_TABLE_LEAF=a746:anchor` (or `a746:ENC,...:anchor`) sets the fight's win bonus to
V(root)/s − (U(start HP) + Σ held potion prices), the same as V(1 HP with the start potions)/s − 1 − Σ potion prices:
a loss then costs, against a win that ends in the start state, what the model says. The raw value is clamped to
[53, 212]. The floor keeps at least the default leaf's balance between wins and the loss / unfinished leaf
(monster damage up to 37, 1.5 per survived turn up to turn 100, half the potion score, death saves); a lower bonus
would let long losing lines outscore short wins. The cap 212 = 4 × 53 is the scale floor's factor. On §724's 592 S&S states the raw anchor has
quantiles −37 / −15 / 11 / 114 / 1,064 (5/25/50/75/95%), so the floor binds in 398 states (TA plays as T there), 81
are inside and 113 hit the cap; mean bonus 92.5 (README). Counted in `PriceTableLeafStats` (`anchorLow`,
`anchorHigh`); the spec records `anchor`.

## Model a746
§746 model A: XGBoost GBM on §732's 440 state features (HP, max HP, HP fraction, potions and slots, deck and upgrades,
relics, relic counters, Searing Blow misc, Silver's S&S leaf L), monotone + in HP, max HP, HP fraction, potion count,
each potion type and L, refit on all 68,032 labelled fights of §731 + §745 (4,252 Heart-entry bases) with §746's
pinned recipe. Exported to CompactTreeNet (`models/candidates/silver_price_a746.trees`, feature tokens `f<i>` index
the vocabulary's names). Out-of-vocabulary cards, relics or potions add nothing (Python would fail); the build counts
them.

## Tests
- `silver_price_table` (ctest, core): feature rows equal Python's Feat.row and margins equal XGBoost's on stored
  states; GameContext → state names; every stored state's table has a non-decreasing HP curve and non-negative potion
  prices; the leaf without a table is Silver's default; with a table more HP never lowers a win and removing a held
  potion never raises it; table build time; with `:anchor` the raw bonus plus the start state's table value equals
  V(root)/s, the bonus stays in [53, 212] and the leaf uses it.
- `silver_price_table_off_identity` (ctest, core): a 4-state S&S → Heart act4replay (seeds 111459990-993, flat 500
  sims) gives main 4851f703's rows with the option unset and =0; with `a746` it loads, logs and plays.

## Limits
- One model, one fight: model A's target is Heart kill from the Heart's start, so only S&S is meaningful. Stage 4 adds
  models fitted on the paired fight-end labels (thread A) for other fights; the interface takes any CompactTreeNet
  model with a vocabulary and a fight list.
- Model A is miscalibrated on single changes (§746: HP and potion effects 1.1-1.7× too large, relic removal and
  max-HP loss too small); the table inherits that. The refit prices the Incense phase at about 0.6× §723 (README).
- `winBonus` stays 53 while U spans up to 4× the HP range (median U(start HP) 146 at S&S), so the table's price of
  dying relative to an S&S win differs from the model's own (0.3-2.4×, median 1.27×; README). The `:anchor` option
  (below) makes it consistent where the model prices dying above 53, not below.
- The table is linear between knots and additive across potions and counters (no interactions).
