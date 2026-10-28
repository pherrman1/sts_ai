# Expert picks vs student_sel (experiment 7, offline) and the expert-anchored candidate

2026-10-26/27, thread "Train a card ranker on expert picks". Full write-up (tables, examples, design):
https://claude.ai/artifact/MAsYmddTgLwvdrXtsp5YxR. No gameplay seeds were used for anything in this directory.

## Data
- 1,064 Ironclad run files of Baalorlord (`runs.txt`, sha256 per file in `runs.sha256`), 808 unique A20 runs.
  Raw files, decision records and scores: `/mnt/project-files/expert-picks/data/`.
- `tools/reconstruct.py` replays deck, relics, potions and keys floor by floor from the run log (with corrections for
  unlogged transforms and relics); 73% of runs end on exactly the logged deck, 95% within 2 cards. Only runs within
  2 cards are used. Maps come from `Map::fromSeed(seed, 20, act, true)` (`tools/mapdump.cpp`), exact on 65/65 engine
  records.
- 45,835 decision rows as heart1 records, scored by `one_combat heart1score` with student_sel (`cf6bf7fb…`). Native vs
  torch logits agree to 1.1e-5; deck order does not change the output.

## Disagreement (top-1 agreement with the expert, `summary.json`)
| decision | student_sel | random | GBM on the same features (held out) |
|---|---|---|---|
| card reward (pooled) | 50.4% [49.7, 51.2] | 24.7% | 62.8% |
| rest vs smith | 60.3% | | 82.9% |
| smith target | 27.2% | | 49.7% |
| boss relic | 50.2% | 25% | 65–67% |
| shop removal | 65.6% | | |
| map path | 71.2% | | |

The student skips card rewards 12.2% of the time, the expert 27.5%. Below 40% HP the student rests 94% of the time;
the expert smiths half the time. Of 270 removals with a curse in the deck the student removes the curse once, the
expert 147 times.

## Candidate (`candidate/`, inputs to `../expert_anchored_student_ab_20261026/`)
- `tools/make_dataset.py` (with `NO_REST=1`, Philipp's decision card: rest sites are not taught): expert rows on card
  rewards, smith targets, shop removals and boss relics with target log((1 − α) p + α e); anchor = 62,576 gen-3
  decision records with student_sel's own logits. 1,064 capture files, tarball sha256 `07af42c2…`
  (`/mnt/project-files/expert-anchored-ab/candidate/data_nr_a0.6.tar.gz`). Wing Boots counter 1.
- `tools/heart1/distill.py --init student.pt` (`1f96f4bf…`), d64 L2 mult 4 h4 `--trim-map --extra-inputs`, lr 3e-4,
  4 epochs, `--select last`, seed 0, cloud CPU. Logs `candidate/train_log_a*.txt`.
- Exported with `export_heart1_weights.py --allow-other-checkpoint --n-heads 4 --trim-map`:
  α = 0.6 → `expert.bin` sha256 `145061444b796ca81339fdb4a7a20dd582c0aba25e2fd3df0c684bac385cae73`
  (student.pt `d9e7df94…`); α = 0.3 → `642cc40d…`.

## Offline gates (`candidate/gates_a*.json`, `tools/gates.sh`)
Held-out expert runs (1/8 by run hash), top-1 gain over student_sel:

| | card reward | smith | shop remove | boss relic |
|---|---|---|---|---|
| α 0.3 | +2.9 pp | +2.9 | +3.1 | +1.4 |
| α 0.6 | **+8.0 pp** (47.5 → 55.5%) | +12.5 (29.3 → 41.8%) | +4.1 | +1.4 |

Share of gen-3 bot decisions whose argmax changes (α 0.6): rewards 3.1%, boss relic 3.7%, shop 4.7%, map 1.2%,
rest 0.7%, event 0.5%, card selects 0–9%. No screen above 40%, map below 2%.

- Gate 1 (card reward ≥ +8 pp) passes only at α 0.6, exactly at the threshold. Gates 2 and 4 pass for both.
  Native parity on 500 records: max |Δ logit| 1.1e-5. **α = 0.6 is chosen.**
- Spot check (gate 3) of changed bot decisions: card rewards move toward block and scaling (Ghostly Armor over
  Clothesline, Power Through over a skip, Second Wind over Clash) and sometimes to a skip; shop removal Strike instead
  of Defend. Shop purchases also move (4.7%) although purchases were never taught, a side effect of shared weights.
- Expected size of the game effect: on bot states the candidate changes about 1 in 30 card-reward decisions, so
  most games diverge late or not at all. The A/B can only show a large per-change effect.
