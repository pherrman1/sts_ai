# Silver card-action canonicalization screen (2026-09-19)

This is a bounded efficiency screen for the two implementation variants in
PR review. It is not a gameplay-quality gate or a default-promotion claim.

## Provenance and protocol

- Baseline: `338ce1e9f560ba3ade3447a0b02c099022b395f6`
- Commit A: `dc811044` (ordinary card-play deduplication)
- Commit B: `bbdd71cf` (ordinary card-play plus safe single-card selection deduplication)
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
| B | `bbdd71cf` replay | `c2825bc4b3ceb98daa91c8293858f25a56da8e374eb47d17ab843496a3e42763` |

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

## 16-seed full-run A/B follow-up

To test the effect beyond isolated snapshots, A and B were run on the paired
source-seed block `12100032..12100047` (16 seeds per arm) using:

```text
OMP_NUM_THREADS=4 STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1
STS_NATIVE_OOC=1 STS_SILVER_EXACT_ROOT_BUDGETS=1
STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_ADAPTIVE=0
STS_SILVER_VNET_LEAF_DIRECT=0 STS_SILVER_TELEMETRY=1
one_combat bestbench 10000 16 0 12100032 <results.csv>
```

| arm | wins | mean HP/maxHP, losses=0 | mean full-run sec | aggregate Silver decisions | aggregate simulations | aggregate nodes | failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| A | 13/16 | 0.536789429 | 34.6148 | 7,839 | 78,510,000 | 65,678,386 | 0 |
| B | 14/16 | 0.565011767 | 36.7577 | 8,065 | 80,750,000 | 67,542,885 | 0 |

Paired B-minus-A full-run wall time was `+2.1429s/seed` (`+34.2859s` total);
B was faster on 5 seeds and A on 11. Wins were 13 both-win, 0 A-only,
1 B-only, and 2 both-lose. This is an outcome-coupled full-run screen: the
arms can take different trajectories, so aggregate decisions, simulations, and
nodes are not a clean causal measure of selection dedup alone. It provides no
runtime or search-work support for B over A in this small follow-up; the one
additional B win and higher terminal HP are not a policy-quality claim.

Raw artifacts were retained locally under
`build/silver-card-canonicalization-32seed/`:

- A CSV: `39a933af736408041fb9f77edade6f69cb5a674b371e742ad3cdfd7f291f6a0a`
- A metadata: `204c30ef76cd022f64580f2543e62d5e5aa7016b0752c5ab623dab119a9839cf`
- A log: `027057b3a0ca542761a76f27628f74b3005728a716ef6a90a67251e8cef45c40`
- B CSV: `6c7b331dc7f1fb202b61402156d76fe31b5020d57f2d06c65a14b1867644b0d8`
- B metadata: `9e0b9c09b85dd4803ab87098d2d98953578b3a98250c579cbc62607083a4bed4`
- B log: `e5647df0044f52703a4002516e2b362b1622ea4955e511de809c3b0eb44fcf1e`
