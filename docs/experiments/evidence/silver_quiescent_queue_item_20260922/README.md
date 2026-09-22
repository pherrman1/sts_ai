# Silver quiescent queue-item identity: frozen DEV evidence

## Provenance and protocol

- Current-main baseline: `8613f9c7811ce19a81cb731e78b6b58d01ec91ca`; Release replay binary SHA-256 `6e4a635dce114970eb4aef6d303498da20588d1d3297abb3611c2f129defea64`.
- Candidate functional SHA: `68b57f1bc644733e845a7bff15d717d481617dee`; Release replay binary SHA-256 `ad1e4d6350033ecd595a2643193cdf3bcea6906e8480d680f5a3bd69d9fcdb36`.
- Frozen hard64 **DEV** input: `docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl`, SHA-256 `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae`. This is not the consumed HOLDOUT.
- Each arm used the same 64 snapshots, 1,000 simulations per decision, `OMP_NUM_THREADS=4`, default Silver configuration, and `tools/seed_guard.sh`. Commands were run from the candidate repository root, substituting the baseline or candidate Release executable:

  ```sh
  env OMP_NUM_THREADS=4 bash tools/seed_guard.sh EXECUTABLE docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl 1000 --reroot-diagnostics
  env OMP_NUM_THREADS=4 bash tools/seed_guard.sh EXECUTABLE docs/experiments/evidence/silver_hard_combat_v1_20260918/hard64-dev-snapshots.jsonl 1000 --first-decision-only
  ```

The first-decision command exits 1 in both arms because five of 64 roots require transactional selection; both emit 64 rows and the remaining 59 are paired. Raw outputs are `main-dev.jsonl.gz`, `candidate-dev.jsonl.gz`, `main-first.jsonl.gz`, and `candidate-first.jsonl.gz` in this directory. Their uncompressed SHA-256 digests, respectively, are `3b5548570dad54e8103579a0ec67d18d49fa59f8f8b7aaa56f9cbfdd4b9845b9`, `7336927e259e442ec8b4c492cf5160a6fad98c56efc2aa79b095673373cb8c34`, `f1fc52295751b1b7b8f9416ed4cf96feaf5313a7a701e10d73846eea900dfaeb`, and `08a1714f78c19568137ee11d97e0932ba386f3babc5d922b8cf005f6a70ce2a7`.

## Outcomes

| Full-combat DEV metric | Main | Candidate |
| --- | ---: | ---: |
| Completed cases | 64/64 | 64/64 |
| Wins | 51/64 | 52/64 |
| Mean terminal HP fraction | 0.3440911508 | 0.3701368277 |
| Selected deterministic reroots with no fallback | 1,287 | 1,312 |
| Selected deterministic reroot misses | 0 | 0 |
| Positive-visit selected edges without child | 0 | 0 |
| Stochastic candidate-missing fallbacks | 541 | 538 |
| Silver historical queue-item dedup hits | unavailable | 325,548 |
| Nodes created | 2,063,754 | 2,087,288 |
| Simulations | 2,232,000 | 2,268,000 |
| Search time (sum of per-case microseconds) | 16.139 s | 16.675 s |

Full-combat action traces differ in 64/64 cases, including 12 changed first actions. These totals follow different trajectories and cannot establish a causal efficiency or gameplay gain.

On the 59 paired first-decision roots, both arms performed 59,000 root visits. First actions differ in 12/59. Main versus candidate chosen-edge visits total 32,388 versus 32,068; nodes created differ by -54 in aggregate; candidate queue-item dedup hits total 7,763. Search microseconds sum to 656,110.242 versus 691,962.262. The latter is a machine-dependent single-run measurement, not a qualified speed conclusion. The five transactional roots remained in the full-combat replay but are excluded from this same-root seam.

## Read-site and regression boundary

The implementation audit inspected `curCardQueueItem` uses in Silver `BattleContext`, `Actions`, and selection execution. Gambler's Brew's quiescent `GAMBLE` selection and Attack Potion's quiescent `DISCOVERY` selection do not read it. Headbutt leaves queued `OnAfterCardUsed` work that does read it and is excluded by the nonempty action queue. Card play overwrites the field before active card processing. Focused tests cover exact priority, dedup and telemetry, excluded states, the expanded Gambler's Brew subtree through reopened selection and confirmation, retained queue stability and continuing search, Headbutt, ordinary action execution, hand permutation, equivalent-copy repair, and sampled chance reroot.

This is bounded DEV confirmation of the new identity rule and reroot invariants. It is not independent scientific review, HOLDOUT, full-run qualification, or a default promotion. PR #285's HOLDOUT has already been consumed and was not rerun. No fresh independent sanity cohort was run.
