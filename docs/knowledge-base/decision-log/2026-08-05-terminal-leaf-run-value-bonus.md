# 2026-08-05 — Terminal-leaf run-value bonus (cross-combat setup)

Date: 2026-08-05
Session/task: Searcher3 terminal victory leaves priced with the native win
model on the post-combat run state, so combat search can reason about
cross-combat setup (e.g. Happy Flower counter alignment).

## Decision

- Added `search::g_terminalBonus` (thread_local `std::function<double(const
  BattleContext &)>`, default empty) consumed only in
  `BattleScumSearcher3::evaluateTerminal` on `PLAYER_VICTORY` leaves:
  `v += bonus(bc)` (`include/sim/search/BattleScumSearcher3.h`,
  `src/sim/search/BattleScumSearcher3.cpp`).
- `apps/one_combat.cpp::runFullRunOOC` arms the hook per battle when
  `search::g_useSearcher3` is set: `termWinArmForBattle` builds one base rich
  row per fight (future fights resampled from the act pool by default via the
  existing `resampleRemainingActEncounters`, or zeroed with
  `STS_TERM_WIN_HIDDEN=zero`, and the resampled `bossId`/`nextEliteId`/
  `nextFight*`/`remElites`/`remFights` features are parity-excluded), and
  `termLeafBonus` patches only the fields `BattleContext::exitBattle`
  transfers (curHp + Burning Blood heal, maxHp, gold, potionCount, potion
  slots, the 8 counter relics, Lizard Tail, Neow's Lament) by rich index, then
  returns `w * g_winNet.predict(row)`.
- New env vars: `STS_TERM_WIN=1` (enable; default off), `STS_TERM_WIN_W`
  (default 100 — V_win is P(win) in [0,1] vs the S3 leaf's hp+50 scale),
  `STS_TERM_WIN_HIDDEN=resample|zero` (default resample).
- Stage-0 mechanics test `./build/test happy_flower <seed>` (command
  `happy_flower` in `apps/test.cpp::testHappyFlowerCounter`) pins the counter
  arithmetic: relic data ticks once at battle start plus once per turn start,
  end counter = (entry + 1 + bc.turn) mod 3, `updateRelicsOnExit` writes it
  back, and counter 2 at battle start charges +1 energy immediately.

## Rationale

- Terminal leaves priced only HP/potions (`curHp + 50`), so any run-state
  resource that combat changes but the run carries forward — relic counters
  (Happy Flower/Nunchaku/Pen Nib/Ink Bottle/Incense Burner/Sundial/Inserter),
  gold, true HP value — was invisible to the search; cross-combat setup
  (stall one turn so the Happy Flower counter is charged for the next fight)
  could therefore never be chosen, even though `END_TURN` stalling is a legal
  edge and the counter is deterministic in turn count.
- V_combat cannot learn the setup: its labels are this fight's endHp/won
  (`train_value_combat.py`), so the future energy is invisible and stalling
  only hurts the label. The pricing must come from a run-level evaluator; the
  native win tree is the tracked, deployable one.
- **Inference:** the current `v_win_trees.txt` has zero sensitivity to ANY
  persistent counter relic — `r26` (Happy Flower), `r30` (Incense Burner),
  `r31` (Ink Bottle), `r32` (Inserter, unselected), `r35` (Lizard Tail),
  `r44` (Nunchaku), `r52` (Pen Nib), `r68` (Sundial), `r131` (Neow's Lament)
  are all among the 448 selected features (Inserter excepted) with 0 of 1060
  trees splitting on each (verified by scanning tree lines for each relic's
  index in the sel table). The leaf bonus therefore buys correct HP/gold/
  potion pricing today, and counter pricing only once a counter-aware terminal
  model replaces `g_winNet` (Stage 3 counterfactual datagen — generic across
  all counter relics, not Happy Flower only).
- Hidden-info: the rich layout contains the true future encounter queue
  (`nextEliteId`, `nextFight0..2`, boss, elite offsets). Feeding it to the
  fair-play combat search would leak future fights; resample-from-pool is the
  M2 route-search precedent (`oocMapRouteSearchPolicy`). The deployed OOC
  stack still uses the true queue (pre-existing, out of scope).
- S3-only by design: the recommended search is S3−belief−chain (§107); the
  hook is one site and the arm is gated on `search::g_useSearcher3`.

## Alternatives considered

- Reuse Searcher2's vestigial `EvalFnc` constructor hook — rejected: it is
  stored but never called, and the hook lives in the app, not the sim.
- Hard-coded counter bonus (e.g. +X value when ending with counter 2) —
  rejected: the value of +1 energy in the next fight is state-dependent, and a
  constant is hand-authored guidance; the win-tree pricing is learned.
- Retrain V_combat with downstream (run-outcome) labels — rejected for now:
  much larger change; the leaf-blend achieves the same effect with an existing
  model and is the natural first stage.
- Full per-leaf `GameContext` copy + `vFeatCsv` — rejected: serialization per
  terminal leaf was estimated at ~4-8x search cost; the index-patch path is
  ~1 tree walk per leaf (~75% cpu measured at 300 sims on a 16-seed smoke).

## Evidence

- `src/sim/search/BattleScumSearcher3.cpp::evaluateTerminal`, `g_terminalBonus`
- `apps/one_combat.cpp::termLeafBonus`, `termWinArmForBattle`, `termWinDisarm`,
  `termWinIndices`, runFullRunOOC battle branch, env parse next to
  `STS_SEARCHER3`
- `apps/test.cpp::testHappyFlowerCounter` (command `happy_flower`): PASS
- Determinism: two identical `STS_TERM_WIN=1` bestbench runs (4 seeds, 100
  sims) agree on all per-seed game columns; only the wall-clock `sec` column
  differs.
- Parity: patched rich row == full `richFeatureVec(post-combat copy)` after
  zeroing the resampled hidden features; zero mismatches across 4-seed runs.
- 16-seed smoke (seeds 126700–126715, 300 sims, fair, S3−belief−chain):
  bonus off 25.0% / floor 31.4 / hp 13.7 at 14.4 cpu-sec/run; bonus on (w=100)
  18.8% / 29.0 / 10.8 at 25.2 cpu-sec/run. Smoke only — 16 seeds is far too
  small to conclude; the change does alter play (bonus firing + result
  differences), and the cost increase is real and a Stage-2 tuning target.

## Status and follow-up

- Implemented, opt-in (`STS_TERM_WIN=1`), default off.
- Stage 2: controlled paired benchmark (needs a `STS_FORCE_RELIC`-style flag
  so Happy Flower is guaranteed in both arms) + stall telemetry (per-fight
  turns/end counters) + `STS_TERM_WIN_W` sweep; cost reduction (fewer trees,
  caching) if the sweep keeps the ~75% overhead.
- Stage 3: counterfactual terminal-value model — generic across every counter
  relic the run owns (Happy Flower/Incense Burner/Ink Bottle/Inserter/
  Nunchaku/Pen Nib/Sundial + Lizard Tail/Neow's Lament state): at post-combat
  states, branch each owned counter to 0/1/2 (one relic at a time, matching
  the strategicgen2 one-at-a-time counterfactual pattern), label via
  `finishOocCounterfactual`; the win tree currently splits on none of the
  counter features (0/1060 each), so all of them need the learned pricing.

## Addendum (same day) — C_psi already prices the counters; cpsi evaluator

- **Probe (new `cpsictr` mode + `STS_CPSI_CTR_PROBE=1`):** at every
  post-combat state of `runFullRunOOC` runs, for each counter relic the run
  owns, re-predict the C_psi next-fight outcome with that relic's counter
  scalar (`buildCpsiEntry` slots 3..9) set to each value 0..k-1, and
  accumulate the mean ΔP(death)/ΔP(win) vs the state's own counter over the
  six fixed probe encounters. On 200 seeds (626 post-combat states) every
  Ironclad-relevant counter shows **correctly signed, monotone sensitivity**:
  HAPPY_FLOWER c2 −0.0033, INCENSE_BURNER c5 −0.0168, INK_BOTTLE c9 −0.0064,
  NUNCHAKU c9 −0.0086, PEN_NIB c9 −0.0156, SUNDIAL c2 −0.0073 ΔP(death)
  (charged = lower next-fight death; 400-seed run appended in EXPERIMENTS.md
  §110). The GBM confound concern did not materialize — the learned
  mechanism effects dominate.
- **Decision:** `STS_TERM_WIN_EVAL=cpsi` (default `win`) swaps the terminal
  leaf evaluator from `g_winNet` to the C_psi no-peek survival model:
  `bonus = w * P(win of next fight)` with the current fight's encounter as
  the fixed probe encounter (constant within a combat, so only the
  state-dependent part orders the leaves). The entry is built from the
  patched rich row (`cpsiEntryFromRich` mirrors `buildCpsiEntry`), so no
  GameContext copies and no hidden-info handling are needed — the C_psi entry
  has no future-fight features by construction.
- **Caveats:** C_psi sensitivity is learned from observational labels
  (counter confounded with fight length in its training data); the correct
  sign on every relic is strong but not proof of causality — the Stage-3
  counterfactual datagen remains the ground-truth validation. Cost: the
  scalar transformer forward was ~0.58 ms (cpsi-eval ~18x the win-tree leaf);
  vectorized with `#pragma omp simd` on the `linear`/`linearBatch` reduction
  loops plus weight-row hoisting across the token loop
  (`src/sim/search/CombatCpsiNet.cpp`, per-output math bit-identical; probe
  deltas unchanged to 4 decimals; fast-erf and batch-only variants measured
  and rejected) → forward ~0.20 ms, end-to-end cpsi-eval overhead +33.7 →
  +17.4 cpu-sec/run on the same 16-seed block (~9x the win-tree leaf) —
  benchmark at the 1k-sim operating point (est. ~50 min for 128 seeds
  locally).

## Addendum 2 (2026-08-06) — lazy-init data race in termWinIndices

- **Bug:** `termWinIndices()` used the pattern `static TermWinIndices m; if
  (!m.ok) { ...build... }` — the C++11 magic-static guard protects only the
  construction, not the published `m.ok` flag. On the first parallel battle
  (GCP server, 24 threads, cpsi-eval arm), several threads entered the
  function simultaneously; a thread could read the half-built struct and
  write through a garbage `potIdx` index (`row[ix.potIdx[pid]] = 1.0f`),
  corrupting the heap — `malloc(): unaligned tcache chunk detected` +
  segfault. The win-tree arms ran the same racy code (shared patch path) and
  completed, but their data was not trustworthy.
- **Fix:** rewrote `termWinIndices()` as a magic-static lambda (single init
  lock guards construction and publication). Verified locally: two 32-seed
  cpsi-eval runs deterministic post-fix; full 256-seed × 5-arm sweep
  restarted on `sts-test` with the fixed binary.
- **Lesson:** any lazily-built lookup shared across the parallel benchmark
  loop must be a magic-static lambda or warmed single-threaded in `main`;
