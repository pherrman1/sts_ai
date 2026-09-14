# Cap-triggered Silver collection: exact flat-1k parity

This correction supersedes the unconditional-cleanup policy tested in ledger §254;
that earlier adverse smoke remains historical evidence. Production sessions now
leave pools and global dedup untouched below their configured cap. At or above
it, an exact candidate is compacted and the retained count is rechecked before
reuse/fresh fallback. Direct `rerootAt` defaults to baseline behavior; its
explicit compaction argument is requested by the session only under pressure.

Baseline: `876e9305a258df3d5a5eafd50e30375b933f8884`.
Measured corrected candidate: `1e7ca07613885acfabaa0ed639a026cda904321c`.
The later evidence commit changes documentation/artifacts only.

## Same 16 seeds, exact recorded parity

Baseline and corrected candidate use seeds 0–15, Ironclad A0, project-fair
Silver/local search RNG, exact flat 1k per private search including selection
subdecisions, allocated cap 32,768, adaptive/direct learned leaves OFF, keys
OFF, default native OOC, same tracked models, Release and OMP4. Both arms
exit 0. Existing baseline binary comes from exact tracked source/dependency
exports inside this worktree. No new worktree or broader seed block.

- All 16 rows match exactly by seed in all nine non-timing fields: seed, won,
  floor, act, hpEnd, maxHp, fightsLost, deathCombat and deathEncounter.
- All 7,008 decision diagnostic records match in every column, including
  allocation, inherited visits, selected-edge visits, root visits and fallback
  reasons. Parallel emission order is normalized using complete-row multisets.
- All 380 per-combat telemetry records match exactly as multisets.
- Fresh baseline rows also match the preserved §254 baseline rows.
- Both arms win 10/16, mean floor 45.375, mean end HP 23.4375.
- No cap fallback, adaptive escalation or integration failure counters.
  Maximum pre-reroot allocation is 13,454, confirming no memory-pressure path.

Only CSV `sec` is excluded; timing/output order are not parity criteria.
Scaling diagnostics do not include action fingerprints or full states. This is
exact recorded outcome/search-diagnostic parity, not a full trajectory trace
or search-quality qualification. [parity.json](parity.json) lists compared
fields and canonical diagnostic hash. `python3 verify_parity.py` reproduces
row/diagnostic/telemetry/metadata comparisons from adjacent committed artifacts.

## Real repeated 10k cap-triggered canary

Same durable starter-deck Ironclad 200/200 HP / Jaw Worm A0 fixture, seed
0xBADC0DE, floor 1 / act 1, exploration 25/25, widening 3.7028/0.52389. Follow
expanded legal END_TURN outcomes. Each search adds 10k simulations; collection
runs only when the old actual allocation reaches 32,768. No dummy allocation
or fresh reset.

| Collection | Old actual allocation | Retained | Cumulative real allocations |
| --- | ---: | ---: | ---: |
| 1 | 35,825 | 79 | 35,825 |
| 2 | 34,622 | 7 | 70,368 |
| 3 | 37,683 | 3 | 108,044 |

Ten reroots include three actual pressure-triggered collections and seven
baseline reroots. Collection reclaims 108,041 nodes. Final 10k continuation passes
at 7,602 live nodes / 115,643 cumulative real allocations. Retained snapshots,
dedup and live edge/state/chance-parent ownership pass throughout. Debug and
Release output agrees. Direct canary checks the retained cap predicate; session
fixtures separately verify pressure triggering and truly over-cap fallback.
Cumulative allocation is a PR counter, not an executed baseline graph size.

Focused 3/3 CTest and complete default Debug build / 92/92 CTest pass. A below-cap
regression explicitly preserves an orphan node's statistics and dedup slots.
An initial canary dedup assertion incorrectly included the fresh root (which
baseline intentionally excludes); it was restricted to prior dedup members.
No sanitizer, new independent review, broader gameplay cohort or 10k quality
benchmark. Correctness/parity handoff only; no merge or win-rate improvement.
