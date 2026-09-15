# Dynamic Silver dedup and 128k lazy reuse cap

Baseline `fa2ea0ad702281a6b2a1366d792a8e920227832d` (corrected lazy PR #185).
Measured implementation `9a849fd7deadb4374ad33f42796811b03a3ceb07`.
The later evidence commit contains documentation/artifacts only.

Open-addressed dedup starts at 65,536 slots. On a miss, insertion above 50%
occupancy doubles capacity and reinserts existing hash/Node-pointer entries.
Duplicate hits do not grow. Occupancy is cleared on fresh reset and rebuilt
from retained members on compaction, but table capacity never shrinks within
the searcher. Rehash touches no node/state/statistics or gameplay RNG.
Production cap is now 131,072; the existing lazy trigger/final retained-cap
check remains unchanged. No unconditional reroot GC.

## Checks

- Focused forcing test grows a small table seven times and a production-sized
  table 65,536→131,072→262,144 at entries 32,769/65,537. Every prior state returns
  the same Node pointer, with exact visits/Q and no duplicate creation or RNG
  advance. Subsequent search, compaction and reset pass ownership/count checks;
  compaction/reset retain capacity. [Raw resize checks](resize-tests.log).
- Existing deterministic 96-step trace-parity tests (observer OFF and ON)
  compare default and 262,144-slot tables, including node statistics/states,
  selected actions and both search/rollout RNGs. They pass exactly.
- Existing Silver bridge/search tests pass; default cap asserted 131,072 and
  generic session fixtures verify genuinely over-cap fallback.
- Complete default Debug build passes. Complete CTest 92/92 pass, 47.36 seconds.
- Initial full suite failed a stale legacy teacher acceptance expectation.
  Frozen teacher 32k cap stays frozen; production-cap mismatch now explicitly
  rejects before output in both producers, and that self-test is repaired.
  No relabeling of 128k execution as 32k contract evidence. Raw failure retained.

## Tiny real repeated-10k canary

Guarded Release command:
```
/usr/bin/time -v -o memory.txt bash tools/seed_guard.sh \
  build/linux-gcc-release-ccache/silver_search_optimization_test --repeated-reroot-canary
```

Starter-deck Ironclad 400/400 HP, Jaw Worm A0, seed 0xBADC0DE, floor 1 / act 1,
exploration 25/25, widening 3.7028/0.52389. Follow expanded legal END_TURN first
stored outcomes. Each search adds 10k simulations. Fourteen reroots and a final
10k continuation; no dummy allocations/fresh resets, no gameplay cohort.

| Observation | Value |
| --- | ---: |
| Peak live allocated nodes before reroot collection | 140,976 |
| Peak stored BattleContexts | 116,788 |
| Largest candidate-reachable graph | 80 |
| Final dedup capacity | 262,144 slots (4 MiB) |
| Number of resizes | 2 |
| Peak sampled dedup load | 49.3408% |
| Final dedup entries / load | 4,693 / 1.7902% |
| Pressure collection | 140,976→3 nodes |
| Reclaimed nodes | 140,973 |
| Final continuation live nodes | 5,497 |
| Cumulative real allocations | 146,470 |

32k would trigger collection earlier (round 3), but no candidate-reachable graph
would require 32k cap fallback (maximum 80). 128k triggers one collection at
round 14; final retained-cap check never blocks. The cap is checked at reroot,
so a 10k search batch can overshoot it before collection. Direct canary checks
the retained predicate; session fixtures verify production ordering/fallback.
Historical totals are real PR allocations, not an executed old-policy graph.

## Memory observation

External `/usr/bin/time -v` reports 794,040 KiB maximum RSS = 775.43 MiB, no swaps,
exit 0. This includes canary verification sets and copied-node/edge snapshots,
not just searcher storage. Raw node/state/table sizeof payload at the sampled
peak is approximately 711.72 MiB, excluding heap capacities and other overhead.
Measured host has about 31 GiB RAM. This fixture is comfortably within its memory
budget; it is not a universal per-searcher RAM bound for different decks,
simulation budgets or concurrent searchers. No permanent memory infrastructure.
No timing/quality/win-rate claim; no broader benchmark, sanitizer or new
independent review. [Raw canary](canary.log), [memory observation](memory-time.txt),
[provenance and artifact hashes](provenance.json).
