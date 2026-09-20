# `silver_hard_combat_v1` first frozen candidate pool

Status: frozen v1 benchmark artifact, benchmark-only, not a production
promotion gate. Source/replay executable SHA: `e7695fe14c342861937535f990c18479def86502`.
Pinned Silver SHA: `84ab3ead9d88c01c4be09a6773fb9a947f57d5ff`.
Release binary SHA-256: `one_combat`
`a96825135d7901e84f91728269d95392f524ef53cd7e3d7dc7a448301d29bfc9`,
`silver_hard_combat_replay`
`35188436f301f9c9314642ed0a6ff3d4f63479cfd20929033a23f49be15e8117`.

## Frozen source configuration

- Ironclad, ascension 0, Act-3 horizon, keys off.
- Project-fair RNG, Searcher2, native OOC on, policy PUCT on.
- Ordinary Silver collection: adaptive retained-root policy on, allocated
  32,768-node reuse cap, no exact visit lock, no rho racing.
- Source base budget: 10,000 simulations; observed capture configuration is
  retained per combat (ordinary adaptive roots record 500 or 10,000).
- `OMP_NUM_THREADS=4`; source seeds `12100000..12100127` inclusive.
- Capture schema: `silver_hard_combat_v1`; one first actionable snapshot per
  real combat; 3,096 captures from 128 completed gameplay seeds.

## Screens and selection

The 1k screen covered all 3,096 captures: 3,042 wins, 54 losses, and zero
technical replay failures. The predeclared 10k teacher screen covered all 54
losses plus three successive blocks of 128 lowest-HP-fraction 1k wins. The
combined teacher table has 22 Tier A, 116 Tier B, 32 Tier C, 10 anomalous,
and 258 easy cases. Easy and anomalous cases were excluded from v1.

Selection is deterministic in
[`tools/freeze_silver_hard_combat.py`](../../../../tools/freeze_silver_hard_combat.py)
(SHA-256 `c6532c66e4e02f72136b7dea0f493c402cd3439d7e78aaa5939b502f787a91fc`).
It ranks A, then material B (terminal HP-fraction improvement at least 0.10),
then C; caps a source seed at two cases; and performs a deterministic
exact-size, source-disjoint partition. The first feasible subset in
source-seed order becomes DEV; the remaining source groups become HOLDOUT.
The selected sets share no source seed and contain no exact state-hash
duplicates. Tier-C cases are retained to fill the frozen hard set after A/B
under the two-case source cap; they are not selected by an additional
diversity heuristic.

DEV composition is 9 Tier A / 48 Tier B / 7 Tier C, across Acts 1/2/3
`12/16/36`, with room types hallway/elite/boss/other `8/22/32/2`.
HOLDOUT is 13 / 47 / 4, across Acts 1/2/3 `8/19/37`, with room types
`18/22/22/2`.

## Frozen baselines

The 1k baseline is the complete fixed-budget screen result for the selected
cases. The 10k values are the separate frozen teacher/reference replay result
for the same selected cases. Both use the benchmark seed stored in each
snapshot; adaptive, exact-lock, and rho racing are disabled in replay.

| cohort | budget | wins | mean terminal HP/maxHP (losses=0) | mean decisions | mean simulations | mean wall seconds | replay failures |
|---|---:|---:|---:|---:|---:|---:|---:|
| hard64-dev | 1,000 | 48/64 | 0.2011844 | 34.937500 | 34,937.50 | 0.258381 | 0 |
| hard64-holdout | 1,000 | 47/64 | 0.2359278 | 33.734375 | 33,734.375 | 0.244461 | 0 |
| hard64-dev | 10,000 teacher/reference | 57/64 | 0.5013957 | 34.265625 | 342,656.25 | 3.088858 | 0 |
| hard64-holdout | 10,000 teacher/reference | 60/64 | 0.5374656 | 32.625000 | 326,250.00 | 2.960088 | 0 |

The replay result schema has no CPU-time counter; CPU cost is therefore
`unavailable`, while wall time above is measured by the replay executable.

The exact reviewable snapshot and cohort files are persisted in this evidence
directory: `hard64-dev-snapshots.jsonl`, `hard64-holdout-snapshots.jsonl`,
`hard64-dev.jsonl`, and `hard64-holdout.jsonl`. `source-manifest.json` records
source provenance/configuration, `teacher-manifest.json` records the tier
thresholds and screening inputs, and `selection-receipt.json` records the
deterministic membership and source-seed partition.

## Artifact locations and hashes

All raw source/screen artifacts, including the interrupted-run quarantine, are
durably archived outside the app-managed worktree at
`/home/philippherrmann/sts_sweep/runs/silver-hard-combat-v1-20260918/`.
The producing worktree also contains a working copy under
`build/silver-hard-combat-v1-20260918/`. The membership files and baseline
outputs are tracked in this directory; their hashes are:

| artifact | SHA-256 |
|---|---|
| `source-captures.jsonl` | `d59a2993754223aa3d549eeaa29b2e2aacafc79de01a614943ce87c420263765` |
| `source-results.csv` | `46eba54bfb7750fd4160b1674ab935ce116287f5dc6a3079cc1d62a4d2d0ee67` |
| `source-results.csv.meta.json` | `8c881593fe0d28fc0d8e75aad441bdd539d920826bd4cf6346d44ac62a4c471a` |
| `screen-1k.jsonl` | `a849253e0e268d99272397bdc1289dfc4ab21deae53cc20415757b08b656cece` |
| `screen-10k-all.jsonl` | `b3fd6045ed8be4c44623c47f21895b0eaa2c4588aec4c12cbe40207fb88bcd32` |
| `hard64-dev.jsonl` | `06af97bace598a23fb5d396e48568b6fd5e68b81a5dca88c01193ddacbfd5c31` |
| `hard64-holdout.jsonl` | `620e831be1a6743d074ded72f50ccb6444505b18ca7e4663cadf853aaf682ef3` |
| `selection-receipt.json` | `458bcb481fe899af4170ba020dacaa764d3b785a2b2a5773772ce7e6d7bb1ced` |
| `hard64-dev-snapshots.jsonl` | `ab7c3298754864986c31273a0f1d23967b165fdd79a386261b680b8ad16d0eae` |
| `hard64-holdout-snapshots.jsonl` | `e8b914ad74ca0508ee6b1db329c5f454e92e7785cd60af1475d53b35a9d8af34` |
| `source-manifest.json` | `95277aa4e9e03bf7647318d3621c999016f9db8e1ec3402b97dc34e5af5a8ffe` |
| `teacher-manifest.json` | `ecb1967d162761c97712e991be4644825d06bc8fc091a2ce65427e6327b7b24b` |
| `hard64-dev-baseline.jsonl` | `da1cb25018a3b08ff0324c95258c9c677ef894aa864d87d7aed2001914e2e222` |
| `hard64-holdout-baseline.jsonl` | `c79b98cb51829de44d47fe61ba27ef36521e0eeadcdeb8ec542c4b343f9ff4db` |

## Commands and technical exclusion

The source run was launched through `bash tools/seed_guard.sh` with the
configuration above and `one_combat bestbench 10000 128 0 12100000`.
Screens and baselines were run through the same guard with
`silver_hard_combat_replay SNAPSHOTS 1000` or `10000`.

An initial Debug collection was interrupted during a toolchain-speed check.
Its 400 partial capture rows and 13 completed result rows are preserved under
`/home/philippherrmann/sts_sweep/runs/silver-hard-combat-v1-20260918/interrupted-debug/`
with `SHA256SUMS`; they are excluded technically because three active source
seeds had no completed whole-run result. The final source population is the
clean Release rerun only. No rows were silently discarded.

Knowledge impact: durable benchmark evidence and selection procedure; no
Silver search behavior, threshold, model, or production gate was changed.
