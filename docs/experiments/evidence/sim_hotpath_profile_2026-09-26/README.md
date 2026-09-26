# Native Silver hot-path profile and live-only action-queue copy (2026-09-26)

Issue #350, ledger §359.

## Workload

`test silver_profile <sims> <stride>` (`apps/test.cpp::silverProfile`): a
mid-run Ironclad deck (starter plus 12 cards, Vajra, Orichalcum, two potions,
80 HP) fights 12 encounters across acts 1–3 (Jaw Worm, Gremlin Nob, Lagavulin,
Guardian, Hexaghost, Chosen, Book of Stabbing, Automaton, Champ, Three
Darklings, Nemesis, Time Eater), played at 100 simulations per decision. Every
4th decision root (89 of 354) is then searched with `sims` simulations, one
searcher per combat re-rooted with `setRoot` (production's fallback path).
Output is deterministic except timings; `digest` fingerprints every root's
edge visit counts.

The builds are Release (`-O3 -flto`); the callgrind builds also have
`-g -fno-omit-frame-pointer`. The machine is a 4-vCPU cloud container, so wall
time is noisy (about ±5% run to run).

## Phase 1: where the time goes (control, `silver_profile 2000 4`, callgrind)

18.50 G instructions in total. Inclusive shares
(`callgrind_inclusive_before.txt`):

| Component | Share |
|---|---|
| `SilverSearcher::step` | 96.2% |
| rollouts (`rolloutToEnd`: rollout agent plus action execution) | 73.2% |
| of which rollout policy (`SilverRolloutAgent::chooseBattleCardPlay`) | 16.9% |
| node dedup (`getOrCreateNode`: hash, `equalForSearch`, state moves) | 11.4% |
| `BattleContext` copy-assign (rollout/expansion scratch) | 7.7% |
| `BattleContext` swap/moves (node creation) | 5.8% |
| draw (`drawCards`, including information-set sorting) | 8.5% |
| `CardInstance::canUse` (playability checks) | 5.8% |
| dedup-table memset in `resetForSearch` | 2.6% |

The exclusive profile is flat: the top function (`executeActions`) takes 6.1%.
The simulator (rollouts plus expansion `execute`) accounts for about
three quarters of search cost; tree bookkeeping and state copies account for
the rest.

The one structural cost that is concentrated and decision-relevant is state
size. `sizeof(BattleContext)` is 8008 bytes, of which the 128-slot action
queue (`ActionQueue<128>`, 48-byte actions) is 6192 bytes. That queue is
nearly always empty at search states, yet every copy, move and swap carried
the whole ring buffer.

The dedup-table memset is overstated under callgrind (`rep stosb` is counted
per byte). It is a 1 MB clear per `setRoot`, negligible next to a
2,000-simulation search (**Inference**).

## Phase 2: live-only action-queue copy

`ActionQueue` gets a copy constructor and copy assignment that copy the
indices and flag bitsets, and only the queued slots, at the same ring
positions. Moves now use the copy. Nothing reads slots outside the queue:
`operator==` compares the queued actions, `hashBattleState` uses only the
size, and binary serialization excludes the queue.

Results:

- Instructions (callgrind, same harness): 18.50 G → 17.76 G (−4.0%).
  Copy-assign 7.7% → 4.3%, swap/moves 5.8% → 3.9%.
- Throughput, interleaved runs (`ab_2000sims.txt`, `ab_10000sims.txt`):
  - `silver_profile 2000 4`, 8 runs each: median 73,423 → 78,161 sims/s
    (×1.065).
  - `silver_profile 10000 4`, 4 runs each: median 68,708 → 72,976 sims/s
    (×1.062); every treatment run beats every control run.
- Parity:
  - Search outcomes are identical: `digest` 1110471879896229421 (2000 sims)
    and 12620900646745881107 (10000 sims) for both builds.
  - `bestbench 1000 8 0 126700` rows sorted by seed are identical apart from
    `sec` (`bestbench_*_126700_8.csv`). Win 4/8, average floor 42.9.
  - Whole-run CPU per run is 16.34 s control vs 16.15 s treatment; 8 seeds
    cannot resolve a difference this small.

The wall-clock gain is larger than the instruction reduction. This is
consistent with the change mainly saving memory traffic (**Inference**).

## Phase 3: batched/SIMD state execution

Not pursued. No tight, uniform loop dominates. Rollout cost is spread across
event-driven action dispatch (`executeActions` 6.1% exclusive, the rest in
many distinct handlers), playability checks, draws and the rollout policy.
Rollouts vary in length and branch per card and monster (**Inference** from
the flat profile; no prototype was built). By the issue's decision rule,
stopping here is correct until a concentrated loop appears.

## Remaining candidates (not tested)

- Smaller state: after this change most of the remaining ~1.8 KB copy is
  fixed-size arrays (card queue 372 B, monsters 584 B, hand 120 B) plus
  heap-backed piles and the player's `std::map` status table (about 16
  allocations per simulation, roughly 5% of instructions).
- The information-set sort in `CardPile::absorbUnordered` (3.3%) defines the
  canonical order. A faster comparator must keep the same order, or sampling
  indices change.
- `CardInstance::canUse` in the rollout policy (5.8%).

## Files

- `callgrind_{inclusive,exclusive}_{before,after}.txt`: callgrind summaries,
  same harness.
- `ab_2000sims.txt`, `ab_10000sims.txt`: interleaved throughput runs.
- `bestbench_{control,treatment}_126700_8.csv` (+ `.meta.json`),
  `bestbench_summary.txt`: parity runs.
- `binaries.sha256`: `test_base`/`test_queue` (harness) and
  `oc_base`/`oc_new` (`one_combat`).
