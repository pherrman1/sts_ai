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
## E2c exact RAW/POST combat-terminal dataset (new producer)

The E2/E2b datasets were captured after reward processing, so they could not
answer whether raw combat-terminal state already predicts run victory. E2c
records TWO matched snapshots of every survived ordinary/elite/act-1-2-boss
combat from the SAME run, then the analyzer compares information-matched
baselines at each boundary.

Producer (opt-in, no default/policy change; seeded via `tools/seed_guard.sh`):

```bash
tools/seed_guard.sh build/one_combat e2cgen <nSeeds> <sims> <asc> \
  build/e2c_raw_terminal.csv <seedOffset>
```

- **RAW** boundary: inside `BattleContext::exitBattle`, after persistent combat
  transfer and before `regainControl()`/reward generation.
- **POST** boundary: at the `REWARDS` screen after non-card rewards, before the
  first card pick/skip.
- Export includes explicit `relic_has_*` / `relic_data_*` (exact signed data)
  and `room_type`/`encounter_id`, and `<out>.provenance.json`.

Analyze:

```bash
STS_XGB_DEVICE=cuda python3 tools/analyze_postcombat_raw_terminal.py \
  build/e2c_raw_terminal.csv build/e2c_raw_terminal
```

It fits B0/B1/B2/T at both RAW and POST using the same XGBoost recipe and
seed-grouped held-out split as E2/E2b, reports log loss / Brier / AUC / ECE,
seed-bootstrap 95% CIs, and the preregistered E2C SUPPORTED / PARTIAL /
NEGATIVE / INCONCLUSIVE decision rule. The `T-raw-no-counter` arm isolates relic
ownership from counter/data for the counter diagnostic.

Do not draw a scientific verdict from the 8-seed smoke; the decision is made
only on the human-controlled production dataset.
