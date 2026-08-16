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