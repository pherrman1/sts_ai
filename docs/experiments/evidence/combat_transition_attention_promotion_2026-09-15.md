# Attention combat-transition promotion

Date: 2026-09-15

The targeted attention-HPO winner was promoted only into the survival slot of
the qualified near-full component stack. The promotion implementation was
independently reviewed before execution and frozen at
`a743364e1425bf5855309b565ac0eac1028cd726`.

## Immutable bindings

- HPO checkpoint: `005f860d847a773c363170d2473fc8f3f77b4beab501c5db44833d2ac8e1e987`
- HPO evidence: `3a4ac8859f9e31f5912449a6c8a1376e7f4e3306791c7e60508cc7e9d956a24c`
- prepared arrays: `a642671d0956f36405b837755cdf3dfb3c4870cde4a1d6f251046ffc8205a1c9`
- promoted survival: `ccc3c210060be34b38fe0671d93c6acde4242563c80a25c5978b4190b80010c9`
- native artifact: `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`

The maxHP `2c5b54d0…`, HP `0c8b5aa8…`, potion `ae1a1411…`, and downstream
`d07ead94…` checkpoints are unchanged. Downstream weights and caches were not
retrained: their inputs depend on HP and potion encodings, not survival. The
shadow receipt explicitly records that compatibility rebind.

## Gates

- Exact HPO-to-component survival parity: 1,536 stratified rows, max error 0.0.
- Frozen TEST quality: survival NLL 0.060411632 to 0.058877671; Brier
  0.017986496 to 0.017384328.
- Final support exposure: `FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS`; every
  nonempty slice at or below 0.1 nat and zero exact-mass rows after the existing
  bounded correction for gold row 71838.
- RAW validity: 1,633,152 transitions; zero HP, potion, gold/Dagger-budget,
  Writhing, relic-residue, RNG, escape, or death-short-circuit violations.
- Native parity: `NEAR_FULL_NATIVE_PARITY_PASS`; 3,904 samples, complete RAW
  state and planner RNG parity, max absolute numeric error 2.38e-6 at 1e-4.
- Executed runtime support: `EXACT_RUNTIME_SUPPORT_COHORT_PASS`; ordered-index
  digests exactly match 505,935/510,030 overall and 51,036/51,441 TEST.

The evidence reuses the original development TEST cohort. It qualifies the
offline composition and native runtime boundary, not online gameplay quality.
Live OOC MCTS remains disabled by default.

## Preserved receipts and commands

Machine-readable receipts are in the adjacent
`combat_transition_attention_promotion_2026-09-15/` directory. Key hashes:

- `quality.json` `f333d19adc4011d83222f316f85d5cec0148ff1427ebaae450074057df1c1329`;
  `quality.npz` `3edb087c0c332cf94922b512bca124451dce050f8d0dd5780c033f4b788fedf9`
- `final-support-exposure.json` `d048463de1fe3f3081da0e64fd31be0957f1e3c952d6cd9b39abb7779458bbd5`;
  row NPZ `8357fc9057c8b8cc1a7215f846e6bc08ac06c6048f43915f9363275bc44b0c0a`
- `final-support-exposure-exact.json` `0eda4556bbd02e40003b3a801c4498b8613fe09fa03a5b15886d1cad26e3148a`;
  corrected row NPZ `02b1815d0a330dd28fbb7ffa5f9839a3cd3aa1bd50c23712df30f0affd022c05`
- `final-support-raw.json` `91e7823a6883aedd607aaec0268bd60d3c92b6bb37c460134054149b59f2c5e5`
- `native-export.json` `65845c272ce83e6f33ebe47b4fb4c053eba18ac055545b93509e0e54b34f5d85`
  records artifact `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`
- `native-parity.json` `60e7fbaca6d2659ecc4a26319ccd579406d0b1fb9830c3a8cc1f976310a9f700`;
  raw native output content `974cba373a802c9e17640506574534bded729cd8076afbbbce7b85ffcc5764c3`,
  preserved gzip `52a8e116621544dcf3ba7a5e76b8b2be17691c4edfc63c45c9c10f31b3097575`;
  fixtures `924b47bd1a8da39f269e862763b9c3ed7991b613947a68f0c50cb078e2bc5ca5`
- `runtime-support.json` `49dcee30a9f7bc291df3400ad765a437bd409077ff2f67b2ec030de2134171a7`;
  raw whole-corpus output content `59dd2abf226a0a43f3b2c810420ef74131ad9bdc4d47cb0b832d11931e9160de`,
  preserved gzip `ac3233051fc522a600827e5dc41ae597344e01a2f43cf017d4998f7330eec1a5`

Commands were executed from the clean reviewed promotion SHA above with
`PYTHONPATH=.` where required:

```text
python3 tools/combat_transition_attention_hpo_promote.py --hpo-evidence /home/philippherrmann/sts_sweep/runs/attention-transition-hpo-20260915/attention_hpo_evidence.json --hpo-model /home/philippherrmann/sts_sweep/runs/attention-transition-hpo-20260915/attention_tuned.pt --prepared /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/prepared.npz --base-parent /home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914 --output-parent /tmp/attention-transition-near-full-20260915 --reviewed-commit a743364e1425bf5855309b565ac0eac1028cd726
python3 tools/combat_transition_near_full_quality.py --parent /tmp/attention-transition-near-full-20260915 --output /tmp/attention-transition-near-full-20260915/promoted-quality.json --source-sha a743364e1425bf5855309b565ac0eac1028cd726
python3 tools/combat_transition_near_full_exposure.py --parent /tmp/attention-transition-near-full-20260915 --output /tmp/promoted-final-support-exposure-v2.json --source-sha a743364e1425bf5855309b565ac0eac1028cd726 --final-support
python3 tools/combat_transition_final_exact_gold.py --parent /tmp/attention-transition-near-full-20260915 --original /tmp/promoted-final-support-exposure-v2.json --output /tmp/promoted-final-support-exposure-exact.json
python3 tools/combat_transition_near_full_evaluate.py hard --parent /tmp/attention-transition-near-full-20260915 --output /tmp/promoted-final-support-raw.json --source-sha a743364e1425bf5855309b565ac0eac1028cd726 --final-support
python3 tools/export_combat_transition_near_full.py --parent /tmp/attention-transition-near-full-20260915 --qualification /tmp/promoted-final-support-exposure-exact.json --validity /tmp/promoted-final-support-raw.json --output /tmp/combat_transition_near_full_attention_hpo_v1.native
python3 tools/qualify_combat_transition_near_full.py --parent /tmp/attention-transition-near-full-20260915 --artifact /tmp/combat_transition_near_full_attention_hpo_v1.native --probe build/linux-gcc-release/combat_transition_runtime_probe --fixture /tmp/promoted-final-native-fixtures-v2.jsonl --output /tmp/promoted-final-native-parity-v2.json
build/linux-gcc-release/combat_transition_runtime_probe /tmp/combat_transition_near_full_attention_hpo_v1.native /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl support-only > /tmp/promoted-runtime-support-all.jsonl
```
