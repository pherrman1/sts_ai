# E2 post-combat run-win critic

Run the offline diagnostic with:

```bash
STS_XGB_DEVICE=cuda python3 tools/train_postcombat_runwin.py \
  build/vrich.csv build/e2_postcombat_runwin
```

The input is the existing `datagen2` rich trajectory dataset. The script uses
seed-grouped train/validation splitting, compares constant B0, HP/progression
B1, and rich T, and writes metrics, calibration deciles, seed bootstrap
summaries, validation predictions, models, provenance, and SHA256 sums under
`build/e2_postcombat_runwin/`.

The boundary is after forced gold/relic/potion pickup and immediately before
the first card pick/skip. This is not a new gameplay or data-generation mode.
The result is predictive under the datagen continuation policy and is not a
causal estimate of item values.

## E2b masked diagnostic

The broader offline E2b diagnostic is intentionally separate:

```bash
STS_XGB_DEVICE=cuda python3 tools/analyze_postcombat_leaf_available.py \
  build/vrich.csv build/e2b_leaf_available
```

It compares B1, T-full, T-fair, and T-masked on all represented card-reward
rows with one seed-grouped split and held-out seed bootstrap. T-fair removes
the verified future encounter and forward-map families. T-masked additionally
removes direct reward fields and all verified elite-relic-induced side effects
(including HP/max HP, deck/upgrades, bottle state, potion capacity, and relic
state). The manifest is
fail-closed and the output verdicts are `MASKED SUPPORT`, `MASKED INCONCLUSIVE`,
or `MASKED NEGATIVE`.

This is not an exact raw-terminal or ordinary-combat result: `vrich.csv` has no
room/encounter identifier and is captured after forced non-card reward pickup.
The historical E2 file has exactly 1,009 columns and predates the current
`richHeader()` `fmD*`/`fmC*` and `curMapX`/`curMapY` fields; their absence is
recorded in the manifest provenance rather than treated as constant values.
The original B1 comparator retains HP/maxHP/hpFrac while T-masked excludes
HP/maxHP, so `MASKED NEGATIVE` is not an information-matched raw-terminal
comparison.
Relic columns combine ownership and counters, so the counter-awareness arm is
reported as not testable rather than treating post-pickup relics as a clean
counter intervention.