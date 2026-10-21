# CRN act-end price pilot: STOP (ledger §TBD, 2026-10-21)

Pre-registration: [PREREG.md](PREREG.md). The campaign ran on 4 workers (Philipp 2026-10-21 13:44Z), RUN_COMMIT `cc78c5e5`,
code `56950107`, binary `9829d475…`. All 64 units have rc 0 and all 4 tars are verified ([verify.txt](verify.txt),
[tars.sha256](tars.sha256)); the raw tars are in `/mnt/project-files/silver-leaf-eval/crn-act-pilot/`.
Analysis: `python3 tools/analyze_crn_act_price_pilot.py result.json <pilot tars> --compare <§537 tars>` → [result.json](result.json).

**Decision (pre-registered): STOP.** The HP slope CI includes 0, and the projected campaign is about 14,600 core-h,
far above the 800 core-h bar.

Data: 668 valid states (acts 1/2/3: 321/221/120) and 3,377 continuations, with no seed dropped. The values are the
A20 floor model (`altFloor`) after each continuation; the 3-fight comparison is the full §537 data (2,667 states).

| | act-end horizon (pilot) | 3 fights (§537) |
|---|---|---|
| HP slope, floors per HP (seed bootstrap 95%) | 0.054 [−0.031, +0.134] | 0.066 [0.046, 0.086] |
| mean Δ floors for −12 HP | −0.65 | −0.79 |
| SD of paired Δ, −12 HP / −potion / −50 gold / −5 max HP | 7.3 / 5.5 / 5.7 / 5.6 | 4.8 / 4.7 / 3.9 / 4.1 |
| pairs with identical outcome, −12 HP | 33% | 23% |
| CPU per continuation / core-h per state | 9.5 s / 0.013 | ~10.5 s (flat 10k) |

Prices at the act-end horizon (ratio of means, HP-eq): non-Fairy potion 9.2 [−6.1, +41.0]; Fairy 27.6 [−4.2, +369];
max HP −1.6 per point [−32.7, +0.7]; gold −0.37 per gold [−5.1, −0.05]. The −50 gold and −5 max HP copies end
*ahead* of base on average (+1.0 and +0.4 floors). That is noise, not a price.

Projected N\* for a ±3 HP-eq per-act potion price: about 8,400 / 179,000 / 438,000 states for acts 1/2/3, or about
14,600 core-h.

**Reading:** a longer horizon adds more divergence noise than signal. Once a copy makes a different decision, the
randomness it shares with base no longer lines up. The paired-Δ SD rises by about 50% while the HP effect does not
grow (−0.65 vs −0.79 floors), so signal-to-noise per pair halves (0.09 vs 0.16). **Inference:** CRN difference labels
are only usable at short horizons. At those horizons §537's prices did not transfer to whole runs (§542), so neither
horizon gives an affordable training label for a learned Silver leaf.

Seeds used: 111146000–111146063 (pilot) and 111146900–111146903 (smokes). 111146950–959 were reserved for the
reviewer, and the rest of 111146000–146999 is unused.
