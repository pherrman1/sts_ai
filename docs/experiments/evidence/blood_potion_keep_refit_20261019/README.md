# Blood Potion keep-value refit for the fixed heal (§552)

`potionKeepRank` (ADR-0039) was fitted on CTM corpora played with the legacy in-combat Blood Potion heal
(40% of max HP without Sacred Bark; `STS_BLOOD_POTION_HEAL_FIX=0`, §544).

1. Bias bound, no seeds: `tools/potion_keep/blood_heal_bound.py` on the ADR-0039 corpora (re-extraction
   reproduces `a20-fit.csv` / `a0-fit.csv` exactly). A20: Blood held in 12,465 fights (the fit's `held` column, 12,564, counts potions, so two Blood Potions in one fight count twice), drunk in 75%, old excess
   heal 12.16 HP per held fight, but 42% of drinking fights end at max HP (overheal). Removing the whole
   excess drops the HP coefficient from 12.58 to 0.24 (A0 8.50 to -0.59): the corrected value lies between
   0.9 and 11.6, which spans the whole ranking. `bound-fits.txt`.
2. Paired probe: `potionpriceprobe 1 SEED 10000 20 OUT 8 1 0 all addpot:BLOOD_POTION,ooc=heart1` (commit
   30d3c3df adds `addpot:NAME`), student_sel OOC, OOC MCTS off, A20, acts 1-3, current Silver defaults;
   `run_unit.sh` has the environment. Every sampled battle-start state with a free slot plays the next fight
   unchanged and with one Blood Potion added (common random numbers). Each seed ran once with the heal fix on
   and once off. Seeds 111200191-111200210 (20 seeds x 2 regimes, all rc=0, mean 145 s wall per run on 4
   parallel processes). `delta.txt`, raw CSVs in `probe-csv.tar.gz`, `runs.txt`.
   - value (HP + 53 x survived, ADR-0039 units): fix on 8.90 (100 states), fix off 12.72 (102 states)
   - change -3.82, 95% seed-bootstrap CI [-5.43, -2.28]; 91 identical start states: paired -4.03 (sd 7.39)
3. New value: A20 14.12 - 3.82; A0 9.14 - 3.82 x 0.721 (**Inference:** scaled by the old excess heal per held
   fight, 8.77 / 12.16; A0 not probed); mean 8.34 -> rank 834 (was 1163). **Inference:** subtracting the probe's
   causal change from the observational regression value assumes the heal fix shifts both by the same amount.
   Across the A20 CI, with the 0.721 A0 scaling, the rank stays between about 696 and 967: above Heart of Iron
   (666), and below Fruit Juice (924) at the point estimate, so under this scaling only the order against Fruit
   Juice is uncertain. At the point estimate, letting the A0 shift range from none to the full A20 change gives
   781-972. Combining that with the A20 CI gives about 620-1049: below Heart of Iron at the low end (full A0
   shift) and above Fruit Juice at the high end (no A0 shift). The A0 value is probably a bit higher than
   scaled, since more A0 drinking fights end at max HP (51% vs 42%), so more of the old heal was overheal.
