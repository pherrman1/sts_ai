# Exact prior-playout pick cache: hit rate and CPU (issue #1051, 2026-11-15)

Question (issue #1051): how often does a prior playout ask the g7f_E policy MLP about an input the same search has
already scored, and does an exact cache of the MLP's pick pay for itself after #1046 / #1047 (3.32 µs per call)?
No game seed is played for the measurements below: every pass is `one_combat rolloutpolicybench` over recorded
roots (fresh Gumbel K16 + max backup 4 searches configured as whole-run boss-room searches with prior playouts).

## Roots

52 prior-playout roots of §797's G16 + mb4 whole runs (seeds 111980000-111980255, share
`/mnt/project-files/budget-ladder-roots/units/`), 13 per group, one root per fight ([select_roots.py](select_roots.py),
list in [roots.tsv](roots.tsv)): Act 1-2 bosses and Act 3 bosses at 16,000 simulations, Shield and Spear at 10,000
and the Heart at 40,000 (Act 4 strong's budgets). Environment: §775's G16 combat stack ([run_bench.sh](run_bench.sh)).

## Step 1: exact repeats per search (stride 1)

Binary: main 6126315 plus [memostat.patch](memostat.patch) (arm `memostat`, research hack, not in the PR): every
prior-playout call's full MLP input (all nonzero state features, edge count, each edge's distinct index, targets and
distinct action blocks) is keyed into an unbounded per-search table; a repeat counts as a hit, and its stored pick
is compared with the new one. Results in `results/memostat/`, table by
[analyze_memostat.py](analyze_memostat.py):

| group | roots | hits (pooled) | per root mean [min, max] | playout turn 0 / 1 / 2+ | first call of a playout | distinct inputs per search |
|---|---|---|---|---|---|---|
| Act 1-2 bosses | 13 | 30.1% | 30.0% [13, 41] | 25.4 / 30.2 / 32.0% | 29.4% | 157k |
| Act 3 bosses | 13 | 35.1% | 34.5% [10, 63] | 28.7 / 36.7 / 40.2% | 23.8% | 188k |
| Shield and Spear | 13 | 32.4% | 31.4% [12, 55] | 29.2 / 36.5 / 35.1% | 22.2% | 91k |
| Heart | 13 | 30.0% | 30.8% [15, 57] | 26.6 / 33.2 / 31.2% | 24.7% | 498k |
| all | 52 | **31.4%** | 31.7% [10, 63] | 27.3 / 33.8 / 33.6% | 25.2% | 234k |

- 0 of 5.55 M repeats (of 17.7 M calls) had a different pick, so the key determines the pick. A first version keyed only the
  `touched` entries and had false hits: `combatExtractFeaturesReuse` writes the scalar head, the enemy aggregate and
  the misc / relic counters on every call without listing them in `touched`.
- `hashBattleState` is no key: 3.5% of its repeats had different MLP inputs (it ignores fields the features read).
- Per call (instrumented, 4 processes on 4 vCPUs): MLP 2.91 µs, features 0.96 µs, 16.6 prior calls per simulation.
- Estimate: a hit saves only the MLP (the features are needed for the key): 31.4% × 2.91 µs × 16.6 ≈ 15 µs per
  simulation, at most ~14% of a prior-playout search's CPU with a free key; realistic 5-8%.

The issue's go rule (≥ 20% of calls) holds, so the cache was built.

## Step 2: the cache (PR)

`nativeSilverPolicyArgmax` fingerprints the MLP input (128-bit additive fingerprint: one word per nonzero state
entry via `combatStateFingerprint`, per nonzero action-block entry, per target and per edge's distinct index, then the
net's address) and looks it up in a per-thread 4-way table of 2^`STS_SILVER_PRIOR_PICK_CACHE` 16-byte slots (default
2^20 = 16 MB, huge-page advised), never cleared: every entry stays valid, so lifetime and eviction affect only the
hit rate. A miss runs the MLP and stores the pick.

Results by [analyze_cache.py](analyze_cache.py), cache on vs off (`pc0`) on the same 52 roots, four processes at a
time on a 4-vCPU container; `identical` = root visit counts, pick, simulations, prior calls and playout actions all
equal:

| run | variant | hits | CPU on / off (sum) | geomean | identical |
|---|---|---|---|---|---|
| r1 | v1 (chained hash), 2^18 / 2^20 / 2^22 | 27.5 / 30.3 / 31.2% | 0.994 / 0.991 / 1.001 | 0.973 / 0.978 / 0.996 | 52/52 each |
| r2 | v2 (additive hash, huge pages), 2^16 / 2^18 / 2^20 | 21.9 / 27.5 / 30.3% | 0.991 / 0.970 / 0.952 | 0.972 / 0.963 / 0.950 | 52/52 each |
| r3 | v2 2^20 / 2^19 | 30.3 / 29.2% | 0.939 / 0.954 | 0.934 / 0.935 | 52/52 each |
| r3 | v2 2^20, hits ignored (cost only) | 0% | 1.107 | 1.100 | 52/52 |
| r4 | v2 2^20; v3 (multiply-fold mix) 2^20 twice | 30.3% | 0.976; 0.975 / 0.950 | 0.969; 0.974 / 0.943 | 52/52 each |
| r5 | v2, hits ignored, 2^10 / 2^20 table; v2 on 2^20 | 0 / 0 / 30.3% | 1.075 / 1.096 / 0.938 | 1.061 / 1.089 / 0.927 | 52/52 each |
| r6 | v3 2^20; v4 (branch-free) 2^20 twice | 30.3% | 0.948; 0.993 / 0.995 | 0.962; 1.004 / 1.014 | 52/52 each |

Hits pooled over all 52 searches (the never-cleared table also hits across searches).

- **The cache is exact:** 52/52 roots identical in every one of the 18 cache-on (or hits-ignored) vs off pairs.
- **CPU:** v2 / v3 at 2^20 (the PR is v3) average about **0.95x** a prior-playout search (seven runs, 0.938-0.976;
  run-to-run noise of identical configurations is about ±2.5%). The hits save about 17% (r3: 0.94 with hits vs
  1.11 with hits ignored); the key costs about 7.5% (r5, table in L1) and the 16 MB table's misses about 2% more.
- Chained hashing (v1) cost all of the saving; branch-free zero masking (v4) was slower than v3.
- **Inference:** a faster MLP (#1052) shrinks what a hit saves; at half the MLP time the cache would be about
  break-even.

## Step 3: whole games

Two of §775's G16 + mb4 A20 games replayed (recorded seeds 111378257 and 111378263, no new seeds; environment
[games/g16.sh](games/g16.sh), a copy of the 2026-11-14 speed report's script with `STS_SILVER_GUMBEL_STOP_TRACE`), main
6126315 (v3 preset, binary sha256 bdd6a2e0...) against this branch (cache on by default, 4d1b4c67...), all four
games at once on the 4-vCPU container:

| seed | result | Gumbel stop-trace rows | rows differing (CPU columns dropped) | game log | CPU main → cache |
|---|---|---|---|---|---|
| 111378257 | died floor 28 | 1,083 | 0 | identical | 97.8 → 94.3 s (0.964x) |
| 111378263 | Heart kill | 2,418 | 0 | identical | 445.9 → 433.0 s (0.971x) |

Traces and logs: `/mnt/project-files/prior-pick-cache-1051/games/` (sha256 in [games/traces.sha256](games/traces.sha256);
they differ only in CPU columns). Root rows of this measurement: `/mnt/project-files/prior-pick-cache-1051/roots/`.

## Conclusion

The exact cache works (identical root visits on 52 roots in every run, identical whole games) and saves about 5% of
a prior-playout search's CPU, about 3% of a whole G16 game. That is a third of the issue's estimate: a hit saves
only the MLP (2.9 µs after #1046), the 128-bit key over ~150 nonzero input words costs about 7.5% and the table's
cache misses about 2%. **Knowledge impact:** combat-search architecture page (prior pick cache paragraph) and the
environment-variable table (`STS_SILVER_PRIOR_PICK_CACHE`).
