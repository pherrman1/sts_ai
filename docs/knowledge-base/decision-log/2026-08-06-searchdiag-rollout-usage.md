# 2026-08-06 — searchdiag: Searcher2 rollout-usage diagnostics delivered; pre-existing known-RNG crash found

Date: 2026-08-06
Session/task: Implement the rollout-usage diagnostic for the default Searcher2
arm: per-search counters, frontier classification, per-decision CSV rows, and
a staged budget-sweep probe, so we can quantify how much of each combat MCTS
handles explicitly versus by random rollout (input for where an NN leaf
evaluator could add value).

## Decisions

1. **Counter design: write-only instrumentation on Searcher2.**
   `SearchDiagnostics` (member `BattleScumSearcher2::diag`) counts per
   simulation: terminal-in-tree, rollout calls (split by stop cause:
   terminated / depth-capped / pure-VNet skip / fair no-legal-action),
   fair-play direct-leaf eval, and `treeActions` vs `rolloutActions`. The
   invariant `simulations == terminalInsideTree + rolloutCalls +
   leafDirectEval` holds per searcher and is checked by the smoke test. All
   `diag` writes are in `step()`/`playoutRandom`; nothing in the search logic
   reads them, so the instrumentation cannot alter search behavior.
   **Evidence**: a stash A/B against pristine HEAD reproduces the same
   pre-existing crash at the same fight (see 4); both regimes' `searchdiag`
   runs reconcile.

2. **`Node::outcome` (uint8) records terminality for frontier classification.**
   0 = non-terminal, 1 = victory, 2 = defeat, set at the in-tree terminal
   check. Terminal nodes are never expanded, so `outcome != 0` implies
   `edges.empty()` (fair mode: a shared node records the last world that
   visited it — approximate). This is a Node layout change: all including
   translation units were rebuilt (AGENTS.md ABI rule). Alternative rejected:
   a side table keyed by state hash — leakier and slower than one byte.

3. **Per-decision windowing must branch on `STS_FAIR`, not searcher identity.**
   Non-fair mode reuses one searcher per fight, so the per-decision window is
   the cumulative counter delta; fair mode rebuilds the searcher every
   decision, so the whole search is the window. Pointer identity cannot
   distinguish the two: both modes reuse the same stack address. First
   implementation keyed on `&searcher` produced negative windows in fair mode
   (caught by the smoke invariant check).

4. **Row schemas: A/B share one header; per-fight summaries go to a separate
   `<out>.fights.csv`.** Rejected: emitting differently shaped `F` rows under
   the shared header — that is the column-drift trap AGENTS.md warns about
   (producer header vs consumer parity).

5. **Budget-sweep probe = fresh searcher per stage** (chosen over staged
   `searchToTotal` top-up on the agent tree): independent trees per budget,
   so per-stage metrics are not correlated by tree reuse. Stages
   {100, 250, 500, 1000, 3000, 10000, 30000} per decision, throttled by
   `probeEvery`.

6. **Searcher2 determinization stays at two streams for this change; the
   six-stream question stays open.** `determinize` still samples only
   `shuffleRng` + `cardRandomRng`. Sampling `aiRng` (future enemy intents,
   random targets) and `monsterHpRng` (mid-fight spawn rolls) would be
   strictly fairer and matches Searcher3's particle model (all six seed
   pairs), but it is policy-affecting for the fair regime and needs its own
   paired gate. The `searchdiag` CSV records the `fair` column so rows are
   never mixed across regimes. (Alternatives considered: extend
   `determinize` now — rejected: conflates measurement with a behavior
   change.)

7. **Pre-existing crash discovered: known-RNG Searcher2 bestbench aborts at
   HEAD** (not introduced by this work; stash A/B proved it). Signature: act-1
   floor 13 Gremlin Nob fight, CARD_SELECT with
   `cardSelectTask == EXHAUST_MANY` (6), `pickCount = 10`, empty hand → the
   canonical enumerator emits zero valid edges → pre-existing `assert(false)`
   in `playoutRandom` fires. Reproduces on seeds 0–7 at 200–500 sims;
   `STS_FAIR=1` (the recorded baseline regime) is unaffected (fair runs
   completed to floor 30+). **Not root-caused or fixed** — out of scope;
   documented in `combat-search.md` "Known limitations". Hypothesis for a
   future issue: some card/relic/potion combination puts the game into an
   EXHAUST_MANY select with an empty hand; the canonical enumerator (issues
   47/48) has no empty-hand subset rule for this task.

## Alternatives considered

- Staged top-up probes on the agent's reused tree (correlated per-stage
  deltas) — rejected in favor of fresh probes per stage.
- Single CSV with rowtype-specific column semantics — rejected (drift trap).
- Bootstrap CIs computed in C++ — deferred; per-stage visit/value pairs are
  emitted so the offline analysis can bootstrap (pattern: `analysis_s2s.py`).

## Evidence

- `STS_FAIR=1 ./build/one_combat searchdiag 1 500 0 build/sdiag_smoke.csv 2`:
  all 569 rows reconcile (sims == term + rollouts + direct-eval), fractions in
  [0,1]; B-sweep shows rollout fraction 0.99 → 0.90 and visited-terminal
  coverage 0.15 → 0.91 from 100 → 30k sims; best action flips 0→1 at 250 sims,
  stable 250→10k, flips back at 30k (MCTS noise, expected).
- `./build/one_combat searchdiag 1 200 0 build/sdiag_kr.csv 1 13` (known-RNG,
  seed 13 survives the pre-existing crash): 520 rows reconcile; cumulative
  windowing branch verified.
- Stash A/B (pristine HEAD): identical crash signature at the same fight —
  crash is pre-existing.
- `STS_FAIR=1 ./build/one_combat bestbench 1000 8 0`: completes, 12.5% win
  (8-seed noise band around the 37.5% 256-seed reference; crash-freedom was
  the check).
- `ctest --test-dir build`: 4/5 pass; `selfplay_syntax` fails on CRLF
  (`$'in\r'`) — pre-existing Windows-checkout artifact, unrelated.

## Status

Implemented and verified locally. GCP sweep (paired, per EXPERIMENTS.md rules:
seeds, budgets, fair/known-RNG regimes, model hashes, threads) and
`EXPERIMENTS.md` recording are the follow-up.

## Addendum (same session): maxTreeDepth metric + first full experiment (§117)

- **maxTreeDepth added** (SearchDiagnostics::maxTreeDepth, cumulative
  deepest explicit tree path per searcher) to close the conversation's
  

## Addendum (same session): maxTreeDepth metric + first full experiment (§117)

- **`maxTreeDepth` added** (`SearchDiagnostics::maxTreeDepth`, cumulative
  deepest explicit tree path per searcher) to close the conversation's
  "average/max tree depth" item; wired into rowtypes A/B as `maxTreeDepth`.
- **First full run recorded in EXPERIMENTS.md §117** (local WSL, commit
  `4325c03` + this diff): fair arm 6 seeds @1k (Searcher2 fair, probeEvery 2),
  known-RNG arm 8 seeds @1k. Headlines: known-RNG hallway fights drop to 19%
  rollout-call fraction at 30k sims (vs 62% fair); bosses stay rollout-heavy
  in both regimes (known-RNG 55%, fair 86% at 30k); visited-terminal coverage
  at 30k reaches 0.85 (KR act 1) but only ~0.50-0.69 fair act 3; NN-leaf
  value concentrates on boss/long fights (rollout fraction 0.78-0.89, avg
  rollout 12-13 actions, vtc <= 0.24). Artifacts in `build/`:
  `sdiag_fair.csv(.fights.csv)`, `sdiag_kr_arm/s*.csv(.fights.csv)`,
  `sdiag_grouped.csv`, `sdiag_group.py`.
- **Known-RNG crash re-confirmed at a second site** (seed 12 @1k, floor 21
  Shelled Parasite, same EXHAUST_MANY/empty-hand signature); the known-RNG
  arm's seed set was restricted to survivors (10,11,13,14,16,17,18,19).
