# Pilot: several uniform random playouts per Silver leaf vs greedy (A20, fight level)

Status: small in-thread pilot requested by Philipp (2026-10-17 22:11Z, thread "Distilled Silver playout picker":
"can you try it on a small pilot with increasing random playouts per leaf?"). Descriptive only, no labels, no default
change. Ledger §523. Seeds assigned by the coordinator: 111193700–111193799.

## Question

§479 found one uniform random playout per leaf far worse than the greedy playout (−22.80 [−27.87, −18.18] fight score
at 2,500 simulations). Does averaging more random playouts per leaf close that gap, and at what CPU?

## Design

`one_combat ctmsilvergen` at Ascension 20, new armset `uniformpl`, otherwise the §519/§521 harness (`env.sh`,
`run.sh` here; student C source runs, gen-6 E root prior weight 400, keys flag off, hallway every 3rd, R = 2).
`STS_SILVER_ROLLOUT_ROOT_TABLE=0`, so greedy uses the ADR-0040 table. Arms at 2,500 simulations: `greedy2500`,
`uniform1x2500`, `uniform2x2500`, `uniform4x2500`, `uniform8x2500` (k uniform random playouts averaged per leaf).

- Sources 111193700–111193715 (16), in this thread on 4 cores (4 shards of 4). Smoke 111193790–111193793.
- Code commit and binary: `CODE` in `run.sh`, `BINARY_SHA256`.

## Analysis

`analyze.py` (the §521 analyzer with these arms): per arm score, win, HP lost, CPU per fight and per simulation,
rollout length; `uniform<k> − greedy` and `uniform8 − uniform1` paired contrasts with 95% seed bootstrap; CPU ratios
`uniform<k> / greedy`. No decision rule: a promising k would need a pre-registered CPU-matched test.
