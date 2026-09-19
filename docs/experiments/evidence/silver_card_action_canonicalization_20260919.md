# Silver card-action canonicalization screen (2026-09-19)

This is a bounded efficiency screen for the two implementation variants in
PR review. It is not a gameplay-quality gate or a default-promotion claim.

## Provenance and protocol

- Baseline: `338ce1e9f560ba3ade3447a0b02c099022b395f6`
- Commit A: `dc811044` (ordinary card-play deduplication)
- Commit B: `05548a3e` (ordinary card-play plus safe single-card selection deduplication)
- Cohort: `hard64-dev-snapshots.jsonl`, 64 frozen DEV snapshots; HOLDOUT was not used.
- Command: `bash tools/seed_guard.sh <silver_hard_combat_replay> hard64-dev-snapshots.jsonl 1000`
- Build: Linux GCC Release ccache preset, same host and `OMP_NUM_THREADS=4`.
- Replay configuration: fixed 1,000 simulations per decision, allocated 32,768-node
  reuse cap, adaptive/exact-visit-lock/rho stopping disabled, matching the frozen
  `silver_hard_combat_v1` replay protocol.

Binary SHA-256 hashes:

| arm | binary | SHA-256 |
|---|---|---|
| Control | baseline replay | `b20d6ccf97e1b24e1ed6f4db8691ec022a716a905d13f23595c4ef9377562b0e` |
| A | `dc811044` replay | `3a441fbd1b96fa039c309081cd318f9e8b47f18b562c0feeab739b891253df92` |
| B | `05548a3e` replay | `c2825bc4b3ceb98daa91c8293858f25a56da8e374eb47d17ab843496a3e42763` |

## Results

| arm | wins | mean HP/maxHP, losses=0 | decisions | simulations | nodes created | failures | wall seconds (runs) |
|---|---:|---:|---:|---:|---:|---:|---|
| Control | 48/64 | 0.201184418 | 2,236 | 2,236,000 | 2,061,865 | 0 | 16.23 |
| A | 51/64 | 0.323599945 | 2,265 | 2,265,000 | 2,099,430 | 0 | 16.03; 15.91 |
| B | 51/64 | 0.329883253 | 2,234 | 2,234,000 | 2,069,231 | 0 | 16.54; 15.77 |

B versus A had 30,199 fewer created nodes and 31 fewer decisions. The action
trace hashes differed on 17 of 64 cases, while wins remained identical. Wall
time was variable across the two fixed-cohort runs and does not establish a
stable speedup: B was slower once and faster once. The bounded result supports
less redundant search work without an obvious degradation, but does not support
a runtime-promotion claim or equivalence.

Raw JSONL result hashes:

- Control: `307b69a462a8885f2ffced762f1ec791b798ddc518c5dfa90fcabdb50bff0c95`
- A run 1: `867e20e8874a3e0e7dfef8169efcad06c168a63de35487353b657e69487e1588`
- A run 2: `e5dc4b46f4097d3e42ad1c6cb4274f305d74b677de215aecea7fd0e817f84a4c`
- B run 1: `d6fb36dff3efb3205a6993284b1f9a091d800347ee5c772e05cd6e6efb3af618`
- B run 2: `d34ce96cb20474867dbc4df26350c004fdfef6777c7f96d3fe117fe72001cea4`

Knowledge impact: experiment evidence only; no default, model, or gameplay
quality decision is authorized by this screen.
