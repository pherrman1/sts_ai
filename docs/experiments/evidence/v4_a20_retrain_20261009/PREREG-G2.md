# G2: A20-retrained V4 Q head at A20 (pre-registration)

Question: does the deployed V4 with its Q head retrained on A20 full-run labels
play A20 better than the current V4?

## Data (frozen before training)

- `strategicgen2` at ASC 20 on frozen `2c89ed97` (binary 4a3c9ecc), 25 cloud workers,
  seeds 67000000+1000W+k, brief `/mnt/project-files/v4-a20-retrain/BRIEF-worker.md`:
  8 sampled decisions per run, every option played to the run's end 4 times
  (common random numbers), native Silver 2,000 exact root sims with root prior v1
  (w400, sha 573305c4) in both the main run and branches; run policy = deployed-default
  heuristic OOC.
- 155 chunk files, 611 complete runs, 275,085 rows, 4,856 labeled decisions
  (3,820 with >1 option). Partial chunks keep only complete seeds (w01 67001012,
  w08 67008012 Silver stalls; w07 67007000, w09 67009012 container restarts).

## Training (CPU, this container)

- Split: seed-disjoint 80/20 (`STRAT_SPLIT_MANIFEST`, 488/123 seeds), shared by all arms.
- `STRAT_LABEL_SCALE=floor` (value = endFloor, Q = labelFloor).
- Held-out strict Q top-1 on 764 validation decisions with >= 2 labeled options:
  uniform random 0.255; heuristic chosen action 0.334; deployed V4 Q 0.255;
  scratch V4 (all heads) 0.276; warm start from deployed V4, Q head only, 0.301 (6 epochs).
- Candidate: warm-start Q-only model, best validation Q top-1 over a 30-epoch run
  (`W30_best_qtop1.pt`, epoch 12, validation Q top-1 0.309), exported as `v4_a20_w30.native` sha256 `135e5500be4dfb939389ee7b98f51ecdd3de0758d282e31641790fc4e5cea711` (copy in `/mnt/project-files/v4-a20-retrain/models/`), exported with `export_strategic_tok.py` (parity checks pass).
  The deployed .native was re-imported with `tools/import_strategic_tok_native.py`
  (byte-exact round trip).

## Gate

- Stack as G1 (`PREREG-G1.md`), guard off, margin 1.0 (now 1 floor for the candidate).
- Arms: C = current V4 (e62abd83), T = candidate. Seeds 67200000..67200127 paired, A20.
- Primary: mean paired floor difference T - C, 95% paired bootstrap CI (10,000 reps,
  RNG 20261010). Secondary: wins, floor >= 50, rows differing.
- Decision: `RETRAIN_BETTER` if CI lower bound > 0; `RETRAIN_WORSE` if upper bound < 0;
  else `NOT_SHOWN`. No default change in any case.
