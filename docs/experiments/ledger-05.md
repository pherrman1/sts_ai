## §117 Searcher2 rollout-usage diagnostic (searchdiag): first full measurement - known-RNG hallway fights become near-explicit at 30k sims; boss fights stay rollout-dominant in both regimes (2026-08-06, local WSL)

- **What:** diagnostic-only measurement (no policy change, no win-rate claims) of
  how much of each combat the default Searcher2 arm handles via explicit tree
  descent vs random rollout, plus frontier terminality and root-decision
  stability vs budget. New `searchdiag` mode + write-only searcher counters
  (decision log `2026-08-06-searchdiag-rollout-usage.md`; `combat-search.md`
  "rollout-usage diagnostics").
- **Config:** commit `4325c03` + uncommitted searchdiag diff; WSL build;
  `one_combat searchdiag <nSeeds> 1000 0 <out> 2 <seedOff>`; Searcher2; asc 0;
  8 threads; native OOC; policy PUCT on (`build/policy_trees_c.txt`); no
  combat value/PVNet; `STS_ROLLOUT_DEPTH` unset (rollouts play to battle end).
  Fair arm: `STS_FAIR=1`, seeds 0-5. Known-RNG arm: seeds 10,11,13,14,16,17,18,19
  (seed 12 excluded: pre-existing empty-hand EXHAUST_MANY assert, see below).
  Budget-sweep probes {100..30k} on fresh searchers every 2nd decision;
  agent decisions at 1000 sims. **Fair arm is Searcher2 fair, not the
  recommended S3 particle stack** - results are regime-scoped, not comparable
  to gate numbers.
- **Rollout-call fraction by room x budget** (probe rows; n per cell in
  parentheses): fair MONSTER 0.71/0.70/0.69/0.68/0.66/0.64/0.62; fair ELITE
  0.83/0.81/0.80/0.79/0.77/0.74/0.72; fair BOSS 0.92/0.91/0.90/0.90/0.89/0.87/0.86.
  known-RNG MONSTER 0.48/0.45/0.43/0.40/0.33/0.27/0.19; ELITE
  0.71/0.68/0.64/0.58/0.46/0.31/0.18; BOSS 0.91/0.89/0.87/0.84/0.78/0.68/0.55.
  Known-RNG hallway fights become ~80% explicit at 30k sims; bosses stay
  rollout-heavy in both regimes (fair 86%, known-RNG 55% at 30k).
- **Visit-weighted terminal coverage by act x budget:** fair act1
  0.45/0.47/0.50/0.53/0.59/0.64/0.69, act2 0.29/0.32/0.34/0.37/0.43/0.49/0.57,
  act3 0.26/0.28/0.30/0.33/0.38/0.44/0.50; known-RNG act1
  0.51/0.53/0.55/0.57/0.64/0.74/0.85, act2 0.46/0.50/0.55/0.60/0.68/0.76/0.84,
  act3 0.25/0.25/0.27/0.32/0.41/0.53/0.66. Even at 30k sims the MCTS-preferred
  portion of the tree is not fully terminal (fair act3 0.50) - rollouts still
  value most search mass.
- **Agent decisions at 1000 sims (A rows, per room):** fair MONSTER/ELITE/BOSS
  rollFrac 0.69/0.80/0.89, avgRolloutLen 7.4/8.7/12.6, maxTreeDepth
  8.9/8.6/9.6, vtc 0.53/0.32/0.22; known-RNG MONSTER/ELITE/BOSS rollFrac
  0.74/0.76/0.78, avgRolloutLen 12.6/11.6/12.7, maxTreeDepth 11.8/10.3/12.4,
  vtc 0.30/0.27/0.24.
- **Structural finding (regime cost):** fair mode commits one action per
  search, so ~123 decisions/fight vs ~2/fight known-RNG (line replay), i.e.
  ~40x more searches per fight and ~40x more probe cost per seed.
- **NN-leaf relevance:** the data supports the hypothesis that a leaf
  evaluator pays off mostly on boss/long fights (rollout fraction 0.78-0.89,
  avg rollout 12-13 actions, vtc <= 0.24), not on known-RNG hallway fights at
  deep budgets (19% rollout, vtc 0.85). Conditioning NN blending on measured
  rollout length/coverage rather than raw depth is feasible with this schema.
- **By-act view** (`build/sdiag_by_act.csv`, script `build/sdiag_by_act.py`;
  means per regime x act x budget, n per cell): for known-RNG, **act 3 is the
  rollout-heavy zone regardless of room** - rollout fraction at 30k sims: act1
  0.20, act2 0.19, act3 0.39; by room @30k: act1 MONSTER 0.09 / act2 MONSTER
  0.07 / act3 MONSTER 0.37, bosses 0.39-0.67. For fair, room dominates act:
  MONSTER 0.47-0.74, ELITE 0.67-0.79, BOSS 0.83-0.89 at 30k across all acts.
  maxTreeDepth @30k: KR act3 15.7 vs act1 13.6; fair ~12 flat. valueGap (KR)
  grows to 970-1716 HP at 30k vs fair 268-353 - known-RNG root decisions
  become far more conclusive; fair stays tight. stableVsPrev @30k: fair
  0.87-0.95, KR 0.88-1.00.
- **Pre-existing crash re-confirmed:** known-RNG Searcher2 aborts at
  CARD_SELECT EXHAUST_MANY with empty hand (act-1 floor 13 Gremlin Nob, and
  floor 21 Shelled Parasite for seed 12 at 1k sims); fair path unaffected.
  Coverage of the known-RNG arm is therefore seed-restricted.
- **Artifacts:** `build/sdiag_fair.csv(.fights.csv)`, `build/sdiag_kr_arm/s*.csv(.fights.csv)`,
  `build/sdiag_grouped.csv` (grouped means by regime x room x act x deck x
  legal-action bucket x turn x budget), `build/sdiag_by_act.csv`,
  `build/sdiag_by_encounter.csv`,
  `build/sdiag_group.py`, `build/sdiag_by_act.py`, `build/sdiag_by_encounter.py`
  (grouping scripts).
  Cost: fair arm 283s wall (6 seeds); known-RNG ~1 min/seed.

## §118 Root-stability adaptive search (STS_CONV_ROOT) paired gate: candidate point (MIN=500/PATIENCE=500) FALSIFIED — win below flat at 256 paired seeds; adaptive line stopped, defaults stay env-only (2026-08-06, local + GCP)

- **What:** paired benchmark of the §117-era adaptive-budget arm:
  `BattleScumSearcher2::searchToTotalRootStable` (chunked search, root-action
  stability stop) with the budget-neutral per-fight `fightPool` reinvestment
  and the `onlyLegalAction` forced-move shortcut, vs the flat fixed-budget
  arm. Provisional 64-seed local signal was +3.1pp at −9% cpu for
  MIN=500/PATIENCE=500 (plan `plan-searchdiag-adaptive-continuation.md`,
  decision log `2026-08-06-conv-root-stable-search.md`); this entry is the
  required confirmation run and the arbiter verdict.
- **Config (both arms):** commit `99d55dd`; `one_combat bestbench 1000 256 0 0
  <out.csv>`; Searcher2 fair (`STS_FAIR=1`), asc 0, native OOC, policy PUCT on
  (`build/policy_trees_c.txt`), no combat value/PVNet
  (floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`). Candidate
  arm adds `STS_CONV_ROOT=1 STS_CONV_ROOT_MIN=500 STS_CONV_ROOT_PATIENCE=500`
  (other knobs default: START=250, GROW=2.0, CHECK=100, SHARE=0.05, VALUE=1.0,
  MAX_FRAC=3.0). Metric formula = producer `bestbench` summary line
  (win% = wins/seeds, avg_floor, avg_hp_end, cpu_sec/run); paired flip counts
  from per-seed `won` columns.
- **128-seed local confirmation (T2, this machine, 12 threads):** flat
  **21.9% / 28 wins** / floor 36.0 / hp 13.1 / cpu 6.66 s·run vs candidate
  **21.1% / 27 wins** / floor 36.3 / hp 10.9 / cpu 6.15 (−7.7%); flips 8 up /
  9 down / 111 same. Delta −0.8pp, within noise → proceeded to the gate per
  plan decision rule (only a >5pp loss would stop at T2).
- **256-seed GCP gate (T3, sts-test, 24 threads):** flat **22.3% / 57 wins** /
  floor 36.0 / hp 12.6 / cpu 8.98 s·run (wall 102 s) vs candidate **19.9% /
  51 wins** / floor 36.1 / hp 10.7 / cpu 7.96 (−11%, wall 90 s). Paired:
  **224 same, 13 candidate-better, 19 flat-better** → delta −6 wins
  (−2.3pp), McNemar-style SE 2.07pp, 95% CI −2.3 ± 4.1pp.
- **Verdict:** ❌ **falsified.** Win < flat with a CI that does not exclude a
  meaningful loss (plan T3 rule: promote only if win ≥ flat with CI excluding
  a meaningful loss AND cpu ≤ flat). The cpu saving (−11%) is real and
  directionally reproducible (T2 −7.7%, T3 −11%, 64-seed −9%), but the 64-seed
  +3.1pp win signal did not survive: 128-seed −0.8pp, gate −2.3pp with 13/19
  flip split. The adaptive line is **stopped**: no default change
  (`g_convRootMinSims`/`g_convRootPatience` stay env-gated opt-in with
  conservative 250 defaults), no promotion to a recorded operating point,
  no baseline-table update. Phase 2 (context-adaptive rollout caps) remains
  parked per plan T6.
- **Artifacts:** per-seed CSVs
  `build/conv_flat_128.csv`, `build/conv_root_128.csv` (local),
  `build/conv_flat_256.csv`, `build/conv_root_256.csv` (copied back from GCP
  `/home/philippherrmann/sts_sweep/build/`); logs `build/conv_{flat,root}_{128,256}.log`.
  Server-side sources synced from local (rsync-copy tree, no commit).
- **Cost:** T2 ~2.5 min/arm wall local; T3 ~100 s/arm wall on GCP.

## §119 Phase 2 (context-adaptive rollout caps, STS_ROLLOUT_CAPS) paired gate: FALSIFIED — caps cut rollout length 18% but lose 5.9pp win; heuristic capped-leaf estimates are net-negative (2026-08-06, local + GCP)

- **What:** paired benchmark of Phase 2 of the adaptive-budget program: replace
  the flat rollout budget (unlimited, `g_maxRolloutDepth=0`) with per-context
  caps — boss encounters, turn 0, and act 2-3 (floors 17..50) capped at 8
  rollout actions each; short late-fight states (monsters alive <= 1) stay
  uncapped so decisive rollouts play to terminal. Leaf evaluation stays the
  heuristic `evaluateLeafState` (combat VNet rejected at the gates, §97).
  Env-gated opt-in: `STS_ROLLOUT_CAPS=1` + `STS_ROLLOUT_CAPS_{BOSS,TURN0,
  ACT23,LATE_ALIVE}` (defaults 8/8/8/1), parsed in `apps/one_combat.cpp::main`
  next to `STS_ROLLOUT_DEPTH`; `rolloutCapForContext` +
  `BattleScumSearcher2::playoutRandom` in
  `src/sim/search/BattleScumSearcher2.cpp`.
- **Before/after searchdiag measurement (fair @3k, 6 seeds 0-5, 24 threads,
  GCP sts-test, per plan T6):** flat baseline `build/sdiag_fair3k_flat.csv`:
  avgRolloutLen 8.76, rolloutDepthCapped 0, rollFrac 0.75, per-room len
  MONSTER 7.1 / ELITE 9.0 / BOSS 12.4, per-act len 7.6/9.5/9.3. Caps arm
  `build/sdiag_fair3k_caps.csv`: avgRolloutLen **7.15 (−18%)**, capped share
  of rollout calls **0.27** (BOSS 0.38, act2 0.33, act3 0.38, act1 0.12),
  rollFrac unchanged 0.75. Late-fight uncapping works: short monster fights
  keep short rollouts.
- **256-seed paired gate (T6 gate, GCP sts-test, 24 threads, same protocol as
  §118):** flat **22.3% / 57 wins** / floor 36.0 / hp 12.6 / cpu 8.64 s·run
  (wall 98 s) vs caps **16.4% / 42 wins** / floor 35.5 / hp 9.6 / cpu 7.97
  (−7.8%, wall 89 s). Paired: **215 same, 13 caps-better, 28 flat-better** →
  delta **−5.9pp (SE 2.3pp, 95% CI −5.9 ± 4.5pp, excludes zero)**.
- **Verdict:** ❌ **falsified.** The caps arm is net-negative with CI
  excluding zero on win rate (−5.9pp) and materially worse on hp (−3.0) and
  floor (−0.5). The ~18% rollout-length cut (and −7.8% cpu) does not pay: the
  heuristic capped-leaf estimate at depth 8 loses more decision quality than
  the saved sims gain, in both long (boss/act 2-3) and short contexts. The
  Phase 2 line is **stopped**: `STS_ROLLOUT_CAPS` stays env-gated opt-in with
  defaults off (no behavior change when unset — verified structurally: the
  context helper returns the flat `g_maxRolloutDepth` path), no promotion, no
  baseline-table update. Phase 3 (policy-guided rollouts) remains parked with
  the other phases (plan §5); the adaptive-budget program's remaining parked
  phases are unaffected by this gate.
- **Artifacts:** per-seed CSVs `build/rlc_flat_256.csv`, `build/rlc_caps_256.csv`
  (copied back from GCP `/home/philippherrmann/sts_sweep/build/`), searchdiag
  CSVs `build/sdiag_fair3k_flat.csv`, `build/sdiag_fair3k_caps.csv` (+
  `.fights.csv`), logs `build/rlc_{flat,caps}_256.log`,
  `build/sdiag_fair3k_{flat,caps}.log`. Code: `rolloutCapForContext` in
  `src/sim/search/BattleScumSearcher2.cpp`, env block in
  `apps/one_combat.cpp::main`.
- **Cost:** ~100 s/arm wall on GCP for the gate; 134-150 s per searchdiag arm.

## §120 Phase 5 (forced-action contraction, STS_FORCED_MOVE) paired gate: decision-neutral, −16% cpu — exact outcome equality on 256 paired seeds; promotion candidate (2026-08-06, GCP)

- **What:** paired benchmark of Phase 5 of the adaptive-budget program: the
  strictly-forced-only contraction — when the live root state has exactly ONE
  legal action (canonical enumeration, `BattleScumSearcher2::onlyLegalAction`),
  commit it directly without searching, instead of spending the flat sim
  budget on a single-edge tree. Narrower than Searcher3's deterministic chain
  compression, which was net-negative (§106). The shortcut previously existed
  only inside the falsified `STS_CONV_ROOT` arm (§118), confounded with the
  root-stability stop; Phase 5 isolates it behind its own env gate
  `STS_FORCED_MOVE=1` (default off), wired in both
  `ScumSearchAgent2::playoutBattleFair` and `playoutBattle` (fair path: fresh
  searcher, skip + takeAction; non-fair path: skip + takeAction + advanceRoot
  to keep the reused subtree).
- **Config (both arms):** commit `99d55dd` + this diff; `one_combat bestbench
  1000 256 0 0 <out.csv>`; Searcher2 fair (`STS_FAIR=1`), asc 0, 24 threads,
  GCP sts-test, native OOC, policy PUCT on (`build/policy_trees_c.txt`), no
  combat value/PVNet (floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`).
  Arm 2 adds `STS_FORCED_MOVE=1`.
- **Result (256 paired seeds @1k fair):** flat **22.3% / 57 wins** / floor
  36.0 / hp 12.6 / cpu 8.96 s·run (wall 102.6 s) vs forced **22.3% / 57 wins**
  / floor 36.0 / hp 12.6 / cpu 7.54 (−15.9%, wall 86.6 s). **Per-seed outcome
  equality: 0/256 seeds differ** on won, floor, act, hpEnd, fightsLost,
  deathCombat, or deathEncounter (`build/fm_flat_256.csv` vs
  `build/fm_forced_256.csv`; total sec 2295.0 → 1929.7).
- **Interpretation:** decision-neutral by construction (a single legal action
  is forced in every determinization), verified at 256 seeds with exact
  outcome equality; the cpu saving is real and large (forced moves skip the
  whole search). This also **reinterprets §118**: the STS_CONV_ROOT arm's
  −2.3pp is attributable to the root-stability stop / pool escalation, not to
  the forced-move shortcut, which this gate shows is neutral-or-better.
- **Verdict:** ✅ **promotion candidate — decision-neutral at −16% cpu.**
  Not a win-rate change (none is expected or observed); it is a free cost
  reduction with provably identical outcomes. Promotion rule per plan T5:
  env-only until two independent gates agree; the second gate should re-run
  this pair (any seed count) and also exercise the non-fair path
  (known-RNG bestbench seeds 10,11,13,14,16,17,18,19 — the fair gate covers
  only the fair path; the non-fair `advanceRoot` variant is wired but
  untested at scale).
- **Artifacts:** per-seed CSVs `build/fm_flat_256.csv`, `build/fm_forced_256.csv`
  (copied back from GCP `/home/philippherrmann/sts_sweep/build/`); logs
  `build/fm_{flat,forced}_256.log`. Code: `onlyLegalAction` +
  `g_forcedMoveSkip` (`include/sim/search/BattleScumSearcher2.h`,
  `src/sim/search/BattleScumSearcher2.cpp`), agent wiring
  (`src/sim/search/ScumSearchAgent2.cpp`), env
  (`apps/one_combat.cpp::main`).
- **Cost:** ~90-100 s/arm wall on GCP.

## §121 Phase 5 forced-action contraction: confirmation gate + non-fair scoping + hang fix — default flipped to ON (2026-08-06, local + GCP)

- **What:** second independent gate for the §120 promotion candidate
  (STS_FORCED_MOVE, strictly-forced-only contraction), a known-RNG non-fair
  diagnostic run, and the resulting deployment decision. **Found during the
  known-RNG run: a hang** in the non-fair path (infinite loop at seed 10
  floor 11) and **non-decision-neutrality in the non-fair regime** (3/8
  diagnostic seeds diverged, seed 13 flipped the win) — the persistent
  searcher reuses the tree across decisions, so skipping a forced-node
  search changes later trees and the shared RNG stream. The fair path builds
  a fresh searcher per decision, which is why it stays neutral there.
- **Hang root cause and fix:** the forced skip advanced the root but left the
  cached winning line (`bestActions`/`bestOutcomePlayerHp`) stale; a stale
  `bestOutcomePlayerHp > 0` then sent `stepThroughSolution` on an empty
  action list forever. Fix: clear `bestActions` and reset
  `bestOutcomePlayerHp = -1` on the non-fair forced path
  (`ScumSearchAgent2::playoutBattle`). This also fixed the latent hang in the
  §118 STS_CONV_ROOT non-fair wiring (which the plan noted was untested at
  scale).
- **Scoping decision:** `STS_FORCED_MOVE` is now **fair-path-only**. In
  `playoutBattle` (non-fair) the standalone flag is a no-op — the forced
  shortcut there fires only inside `g_convRootStop` (the falsified §118
  arm). Rationale: non-fair divergence is real (measured) and its cpu saving
  is negligible (non-fair makes ~2 decisions/fight vs ~123 fair), so the
  shortcut's value exists only in the fair regime.
- **Confirmation gate 2 (fair, independent seed block, fixed binary):**
  seeds 126700–126955, `STS_FAIR=1`, @1k, 24 threads, GCP: flat **19.9% /
  floor 36.1 / hp 13.4 / cpu 8.30 s·run** vs forced **19.9% / 36.1 / 13.4 /
  cpu 6.80 (−18.0%)**; **0/256 per-seed outcome diffs** on won/floor/act/
  hpEnd/fightsLost/deathCombat/deathEncounter (`build/fm2b_{flat,forced}_256.csv`,
  total sec 2125.1 → 1741.8).
- **Known-RNG non-fair run (fixed binary):** seeds 10,11,13,14,16,17,18,19
  @1k: flat vs `STS_FORCED_MOVE=1` **0/8 diffs** (flag is a no-op in the
  non-fair path by design; no hang, completes in seconds
  `build/fm2_kr_{flat,forced}.csv`).
- **Verdict:** ✅ **promoted to built-in default ON** (fair path only;
  `g_forcedMoveSkip = true`; `STS_FORCED_MOVE=0` disables). Two independent
  256-seed fair gates agree on exact outcome equality (§120 seeds 0–255,
  §121 seeds 126700–126955) at −16 to −18% cpu, and the non-fair path is
  unchanged byte-for-byte (0/8 diffs) with the hang fixed. All historical
  fair results remain valid (decision-neutral); current-baselines.md notes
  the deployed-config change without touching headline numbers.
- **Artifacts:** `build/fm2b_{flat,forced}_256.csv`, `build/fm2_kr_{flat,forced}.csv`
  (GCP → local), local debug logs `build/fm_dbg*.log` (instrumentation
  removed). Code: `ScumSearchAgent2::playoutBattle` (non-fair scoping +
  bestActions reset), `playoutBattleFair` (unchanged logic, comment updated),
  `g_forcedMoveSkip` default in `BattleScumSearcher2.cpp`, env parse in
  `apps/one_combat.cpp::main`.
- **Cost:** ~90-100 s/arm wall for the fair gate; seconds for the known-RNG
  runs.

## §122 Phase 4 (fair-tree structural fix, STS_LIVE_VALID): S3 instrumented (first measurement), live-valid re-selection implemented in both searchers — S3 direction positive at both budgets but cpu-positive; promotion candidate only (2026-08-06, local + GCP)

- **What:** Phase 4 of the adaptive-budget program. Two parts: (1) Searcher3
  rollout-usage instrumentation (first-ever S3 measurement — searchdiag
  previously refused S3), and (2) the live-valid-biased edge selection fix in
  both searchers: when the PUCT-chosen stored edge is illegal in the current
  determinization, re-select among stored edges valid in THIS world (same
  UCB/PUCT scoring) and continue tree descent; only when no stored edge is
  valid does the sim fall back to a random rollout (the recorded §117
  behavior). Env `STS_LIVE_VALID=1` (default off) in
  `apps/one_combat.cpp::main`; `selectBestValidEdgeToSearch` /
  `selectBestValidEdgePUCT` in
  `src/sim/search/BattleScumSearcher2.cpp` /
  `src/sim/search/BattleScumSearcher3.cpp`.
- **T0 — S3 instrumentation:** `SearchDiagnostics` moved to a shared header
  (`include/sim/search/SearchDiagnostics.h`); `BattleScumSearcher3` gains a
  `diag` member + step() counters (rollout cause split, treeActions,
  maxTreeDepth, simSeconds in search/searchToTotal); `searchdiag` accepts
  S3 with rowtype A only (probeEvery forced 0 — the B-stage probes are S2
  machinery); invariants verified on S2 and S3 rows.
- **T1 — first S3 illegal-stored measurement (fair @3k, 6 seeds, GCP):**
  **S3 default 59.5% of rollout calls are the illegal-stored fallback**
  (MONSTER 70%, ELITE 54%, BOSS 54%); **S3−belief−chain 58.4%** (MONSTER
  71%, ELITE 55%, BOSS 50%) — vs S2's 48% (§117). The fair-tree/
  determinization mismatch is real and WORSE in S3 (particle worlds diverge
  more than single-determinization S2 trees).
- **Fix effect (searchdiag before/after, fair @500):** S2 illegal-share
  0.26 → **0.00**; S3 0.38 → **0.10**; rollout fractions unchanged; both
  searchers keep the diag invariants (0 violations).
- **Paired gates (256 seeds, block 126700+, fair, GCP):**
  - **S2 @1k:** flat 19.9% (51) vs fix 20.3% (52) — **+0.4pp** (SE 2.2pp,
    19 up / 18 down), floor 36.1→36.6, hp 13.4→12.4, cpu **+5.6%**.
  - **S3−bc @1k:** flat 16.8% (43) vs fix 20.3% (52) — **+3.5pp** (SE 2.4pp,
    27 up / 18 down), floor 34.5→35.0, hp 7.0→8.0, cpu **+15.1%**.
  - **S3−bc @3k (recommended operating point):** flat 19.1% (49) vs fix
    **24.6% (63) — +5.5pp (SE 2.6pp, 95% CI +5.5 ± 5.1pp, barely excludes
    zero), flips 35 up / 21 down / 200 same**, floor 37.6→37.0, hp
    7.4→**11.5**, cpu **+7.9%**.
- **Verdict:** ⚠️ **promotion candidate, not promoted.** S3's win direction
  is positive and consistent at both budgets (+3.5pp @1k, +5.5pp @3k with
  hp +4.1), and the structural diagnosis is confirmed (share 0.58→0.10),
  but the plan's T3-style promotion rule requires win ≥ flat with CI
  excluding a meaningful loss **AND cpu ≤ flat** — all three S3/S2 arms
  cost cpu (+5.6 to +15.1%; re-selected descents go deeper, more tree work
  per sim), so the AND clause fails. S2 is neutral at @1k. `STS_LIVE_VALID`
  stays env-gated default off. Recommended next: a second S3 @3k gate
  (any seed block) to firm the CI before any default flip; S2 needs an @3k
  pair if S2 deployment is ever considered (S2's operating point is not the
  current recommendation, §113).
- **Artifacts:** `build/lv_s2_{flat,fix}_256.csv`, `build/lv_s3_{flat,fix}_256.csv`,
  `build/lv_s3_3k_{flat,fix}.csv` (GCP → local), S3 diag CSVs
  `build/sdiag_fair3k_s3.csv`, `build/sdiag_fair3k_s3nobc.csv`, smoke
  `build/sdiag_lv{,_3}_{off,on}.csv`. Code: `SearchDiagnostics.h`,
  `BattleScumSearcher{2,3}.{h,cpp}`, `apps/one_combat.cpp::main`,
  `sdiagMetricsOf3`/`sdiagOnSearchComplete3` in `apps/one_combat.cpp`.
- **Cost:** ~5-25 min/arm wall on GCP (S3 @3k ~13 min/arm).

## §123 STS_LIVE_VALID second independent S3 gate + first S3 forced-move gate: LIVE_VALID PROMOTED to default ON in the fair-S3 path (recorded cpu-trade call); S3 forced-move contraction confirmed decision-neutral 0/256 at −8.5% cpu (2026-08-07, local + GCP)

- **What:** the §122 follow-up (second independent S3 @3k gate for the
  STS_LIVE_VALID promotion candidate) plus the first S3-port gate of the
  promoted forced-move contraction (`BattleScumSearcher3::onlyLegalAction`,
  same §120/§121 design as S2). Three paired arms on a fresh seed block
  (250000–250255), 256 seeds each, fair, @3k, 24 threads on sts-test:
  **ctl** = fair S3 default (forced-move ON, live-valid OFF);
  **fix** = ctl + `STS_LIVE_VALID=1`; **flat** = ctl +
  `STS_FORCED_MOVE=0`. Gates A (live-valid) = ctl vs fix; gate B
  (forced-move) = flat vs ctl.
- **Config (all arms):** commit `588fd6e` + the §123 promotion diff (parse
  block only); `one_combat bestbench 3000 256 0 250000 <out.csv>`;
  `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=256`; asc 0; native OOC; policy PUCT on
  (`build/policy_trees_c.txt`); no combat value/PVNet
  (floor=`build/v_rich_trees.txt`, win=`build/v_win_trees.txt`). Metric
  formula = producer `bestbench` summary (win% = wins/seeds, avg_floor,
  avg_hp_end, cpu_sec/run); paired flips from per-seed outcome columns
  (won/floor/act/hpEnd/fightsLost/deathCombat/deathEncounter, sec excluded).
- **Gate A results (block 250000+):** ctl **16.0% / 41 wins** / floor 35.7 /
  hp 7.1 / cpu 61.85 s·run vs fix **21.9% / 56 wins** / floor 36.8 / hp 10.2
  / cpu 70.88 s·run. Paired: 215/256 outcome-column diffs, won flips 34 up /
  19 down → delta **+5.9pp (SE 0.92pp, 95% CI +5.9 ± 1.8pp, excludes zero)**,
  floor +1.1, hp +3.1, cpu **+14.6%**. This is the second independent gate
  agreeing with §122's S3−bc @3k (+5.5pp, hp +4.1, cpu +7.9%, block 126700+).
  Direction, magnitude, and hp effect are consistent across both gates;
  both CIs exclude a meaningful loss.
- **Gate B results (block 250000+):** flat (STS_FORCED_MOVE=0) **16.0% / 41
  wins** / floor 35.7 / hp 7.1 / cpu 67.60 s·run vs ctl (default forced ON)
  16.0% / 41 wins / floor 35.7 / hp 7.1 / cpu 61.85 s·run. **0/256 per-seed
  outcome diffs on all 8 outcome columns — exact outcome equality**, cpu
  **−8.5%** (smaller than S2's −16-18%, §120/§121, because the S3 searcher
  is constructed before the check: the per-decision particle-belief
  constructor cost is not skipped on forced moves).
- **Verdict — LIVE_VALID: ✅ promoted, default ON in the fair-S3 path.**
  The §122 promotion rule (win ≥ flat with CI excluding a meaningful loss)
  is now satisfied twice independently (+5.5pp and +5.9pp); the cpu clause
  fails both times (+7.9%, +14.6%), so **the recorded cpu-trade call is:**
  accept ~+8 to +15% cpu for a reproducible ~+5 to +6pp win with +3 to +4
  end-HP — the strongest win-rate result of the adaptive-budget program and
  well within the plan's stated envelope ("~+8-10% cpu for a ~+3pp+ win").
  Scoping: default applies only when `STS_FAIR=1` and `STS_SEARCHER3=1`
  (computed after the STS_FAIR/STS_SEARCHER3 env parse in
  `apps/one_combat.cpp::main`); `STS_LIVE_VALID=0` explicitly disables;
  `fairgen` datagen is NOT covered (it forces the regime after the parse) —
  datagen keeps the recorded §117 behavior unless the flag is set
  explicitly (open question: re-run fairgen datagen with the fix to align
  the policy-target distribution). S2 fair stays opt-in (S2 @1k neutral
  +0.4pp at +5.6% cpu, §122; S2 needs an @3k pair if S2 deployment is ever
  considered, §113). Non-fair paths unchanged unless the env flag is set
  explicitly. The §113 headline (44.5% @3k with the full V4 gate stack) was
  measured pre-flip and remains valid as recorded; a re-measurement with
  the full stack + live-valid default is an open follow-up.
- **Verdict — S3 forced-move: ✅ confirmed default ON (fair S3).** 0/256
  exact per-seed outcome equality at −8.5% cpu on the same standard as
  §120/§121; the port is decision-neutral in the particle regime as
  predicted. Local 8-seed pre-gate smoke: 0/8 diffs at −16%.
- **Artifacts:** `build/lv2_s3_{ctl,fix}_256.csv`, `build/fm3_s3_flat_256.csv`
  (GCP → local; logs `build/lv2_s3_{ctl,fix}_256.log`,
  `build/fm3_s3_flat_256.log` on sts-test), local smoke
  `build/fm3_s3_{flat,forced}_8.csv`, `build/smoke_lv_{default,explicit,lv0}.csv`.
  Code: `BattleScumSearcher3::onlyLegalAction`
  (`include/sim/search/BattleScumSearcher3.h`,
  `src/sim/search/BattleScumSearcher3.cpp`), agent wiring
  (`src/sim/search/ScumSearchAgent2.cpp::playoutBattleFair`), default
  (`apps/one_combat.cpp::main`). Decision logs:
  `2026-08-07-s3-forced-move.md`, `2026-08-07-live-valid-promotion.md`.
- **Cost:** 3 arms × ~12 min wall parallel on GCP (24 threads each,
  oversubscribed 3×); ~2 min/arm local at 8 seeds.
## §124 Winrate-wave baseline re-measurement + S3 feature-ablation re-derivation on the live-valid default binary (2026-08-07, local + GCP)

- **What:** the winrate-wave (§124-numbered) baseline wave
  (`docs/archive/research/plans/plan-winrate-ideas-2026-08-07.md`): re-measure the
  recorded §113/§115 references (44.5% @3k/256p, 37.5% @1k/64p) on the
  current binary (HEAD 7b1a8d2, live-valid + forced-move defaults ON, §123)
  — the §123 flip happened after the references were measured — and
  re-derive the §106 S3 feature-ablation deltas (belief/chain), which §113
  invalidated and §115 flagged for re-derivation.
- **Config (all arms):** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0` + full V4 gate stack (`STS_OOC_STRATEGIC_TOK_NN=
  selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`); block 126700–126955 (256
  seeds); asc 0; native OOC; policy PUCT on (`build/policy_trees_c.txt`);
  no combat value/PVNet; `bestbench` at 12 or 24 threads on sts-test.
- **Results (256 paired seeds, block 126700):**
  - **@1k/64p (S3−belief−chain, current binary): 37.9% / 40.2 floor / 21.9
    hp / 20.34 cpu-s·run** (`build/b2c_1k_64p.csv`) vs recorded reference
    37.5% (`honest_p64_1k_256.csv`): **−0.4pp (CI [−6.6,+5.9]), flips 36/35 —
    the §123 defaults are decision-neutral on the full stack @1k/64p.**
  - **@1k/256p: 41.4%** (`b3c_1k_256p.csv`) vs 64p: +3.5pp (CI [−10.2,+3.1],
    n.s.) — particles still flat-ish within noise on the new binary.
  - **@3k/256p: 46.9% / 42.9 floor / 26.1 hp / 35.49 cpu-s·run**
    (`b1c_3k_256p.csv`) vs recorded reference 44.5% (`honest_fix2_3k_256.csv`):
    **+2.3pp (CI [−9.0,+4.3], flips 40/34, n.s. directionally positive)** —
    new @3k headline on the current binary.
  - **@3k/64p: 42.6% / 24.79 cpu-s·run** (`b4_3k_64p.csv`) — 64p is ~2.6×
    cheaper than 256p at 3k with the same win rate as the pre-live-valid
    reference (42.6 vs 44.5, n.s.).
- **Ablation re-derivation (belief+chain ON vs OFF, accidentally clean
  config bug):** the original B1/B2/B3 runs launched without the
  `STS_S3_BELIEF=0 STS_S3_CHAIN=0` exports (config bug, banners read
  `S3-abl=11110`), producing full-S3-feature arms that pair directly with
  the correct S3−belief−chain arms: **belief+chain ON costs −11.3pp @64p
  (26.6 vs 37.9, CI [+5.1,+17.6]) and −12.1pp @256p (29.3 vs 41.4, CI
  [+5.5,+18.8])** — the §106 direction is confirmed with the honest
  enumerator + live-valid defaults, with a LARGER magnitude than the
  invalidated §106 deltas (+8.6/+4.7). The deployed S3−belief−chain config
  is re-confirmed; belief/chain stay off. @3k the same cost appears
  (−9.4pp: full-S3 37.5 vs S3−bc 46.9).
- **Verdict:** the recorded references reproduce on the current binary
  (flat @1k, n.s. +2.3pp @3k) — the §123 cpu-trade call does not transfer
  a loss to the full V4 stack. §115's "particles flat" holds within noise.
  New paired references for future gates: `b2c_1k_64p.csv` (@1k/64p),
  `b1c_3k_256p.csv` (@3k/256p), `b4_3k_64p.csv` (@3k/64p efficient).
- **Artifacts:** `build/{b1c_3k_256p,b2c_1k_64p,b3c_1k_256p,b4_3k_64p}.csv`
  (current binary, correct flags); `build/{b1_3k_256p,b2_1k_64p,b3_1k_256p}.csv`
  (full-S3-feature accidentals, kept as ablation data); logs on sts-test.
- **Cost:** ~2-20 min/arm wall on GCP; one GCP instance preemption killed
  and required relaunches (preemptible instance; no data lost — runs
  truncated before completion were re-run).

## §124a PVNet deployment-speed smoke (phase 6 of plan-value-targets-2026-08-07): conditional leaf gating + visible-state leaf cache implemented; behavior-preserving cache verified; gate pending on the §124 baseline (2026-08-07, local WSL)

- **What:** phase-6 speed work for the PVNet leaf in Searcher3, per
  `docs/archive/research/plans/plan-value-targets-2026-08-07.md` (user request;
  a phase-5 value-only trainer draft was reverted in the same session —
  nothing of it remains). Two mechanisms:
  1. `STS_PVNET_COND_{TURN,DEPTH,BOSS}` gate the per-expansion NN leaf
     (`BattleScumSearcher3::pvnetCondAllowed`): failing conditions make the
     sim use the ordinary rollout value only (α=0 for that sim); the NN fires
     for long/unresolved continuations (post-rollout and direct-eval
     `evaluateLeaf` calls stay ungated). Defaults off — behavior preserved.
  2. `STS_PVNET_CACHE` (default ON): PVNet leaf values cached by
     `node.obsHash` at the direct-eval sites (no-legal-action, invalid-edge,
     depth cap), where repeated sims re-evaluate the same visible state.
- **Config (all arms):** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64 STS_PVNET=build/v_combat_pvnet.txt`
  (α=1.0 default), `./build/one_combat bestbench 300 8 0 0 <out.csv>`, 12
  threads, seeds 0-7, asc 0, local WSL; full V4 OOC gate stack on (native
  OOC). Model `build/v_combat_pvnet.txt` (d128 h256 hds4 L2 nq11, Jul 26).
- **Results (8 seeds @300 sims — smoke only, not a gate):**
  | arm | win% | avg_floor | cpu_sec/run | note |
  |---|---|---|---|---|
  | cache ON (default) | 0.0 | 25.8 | 44.7 | reference |
  | `STS_PVNET_CACHE=0` | 0.0 | 25.8 | 44.5 | per-seed rows identical (only `sec` differs) |
  | `STS_PVNET_COND_DEPTH=2` | 0.0 | 28.9 | 69.3 | outcomes differ (gate fires) |
  | `STS_PVNET_COND_TURN=3` | 12.5 | 36.6 | 77.5 | outcomes differ (gate fires) |
  | `STS_PVNET_COND_BOSS=1` | 0.0 | 30.5 | 64.0 | outcomes differ (gate fires) |
  cpu differences between gated arms track run depth (deeper runs = more
  decisions = more search), not per-sim cost; timing conclusions require the
  real gate. All knobs print in the `[PVNet alpha = ...]` banner.
- **Verification:** cache-on vs cache-off per-seed outcomes identical
  (sorted-by-seed, all non-`sec` columns) — cache is behavior-preserving;
  `ctest` 5/5; `searchdiag 2 300 0` runs clean with `STS_PVNET_COND_TURN=3`.
- **Deferred (recorded reasons):** batched NN leaf calls (leaf evals are on
  effectively unique states — batching needs a `step()`/`backpropagate`
  restructure for BLAS-efficiency-only gain); GBM/MLP distillation (phase-5
  training line); rollout-skip at α=1.0 (observed `playoutRandom` still runs
  and its terminal value is discarded by the α=1.0 blend — wasted compute —
  but removing it changes `bestActionSequence` semantics; candidate knob).
- **Artifacts:** `build/pv6_cache_{on,off}.csv`, `build/pv6_cond_{depth,turn,boss}.csv`,
  `build/pv6_sdiag.csv`, logs `build/pv6_*.log`. Code:
  `BattleScumSearcher3.{h,cpp}` (`pvnetCondAllowed`, `evaluateLeaf` cache,
  blend-site gate), `apps/one_combat.cpp` env parse. Decision log:
  `2026-08-07-pvnet-deployment-speed.md`.
- **Next:** paired 256-seed gate @1k/64p vs the §124 baseline (winrate wave
  B1-B4 not yet recorded on GCP), then @3k if positive; pre-registered null
  at both budgets closes the PVNet leaf line (winrate-plan §4.3 rule).

## §125 Winrate-wave Wave-1/2 gates: cPUCT sweep, STS_S3_EXPAND, TERM_WIN+cpsi — all null or negative; the leaf-evaluator line flips POSITIVE with a fresh honest-data vnet (§126) (2026-08-07, local + GCP)

- **What:** the winrate-wave gated items that do not involve the vnet
  (`docs/archive/research/plans/plan-winrate-ideas-2026-08-07.md` §3.3/§4.1/§4.2).
  All arms: full V4 gate stack, S3−belief−chain, block 126700 (unless noted),
  asc 0, fair, paired with `paired_analysis.py` vs the §124 references.
- **cPUCT sweep (STS_CPUCT; §3.3):** 128-seed local probe @1k/64p:
  cPUCT 1.0 → 21.1%, 1.5 → 28.9%, **2.5 (default) → 39.1%**, 4.0 → 40.6%,
  6.0 → **42.2%** — monotone, higher exploration better (consistent with
  §26's UCB > PUCT at deep budgets). Gate 1 (256 seeds, block 126700):
  cPUCT=6.0 **42.2% vs 2.5 37.9% = +4.3pp (CI [−10.9,+2.3])**. Gate 2
  (fresh block 250000, paired control): 6.0 **39.8% vs 38.7% = +1.1pp
  (CI [−8.2,+5.9])**. Both n.s. → **not promotable; the cPUCT line is
  closed** (direction consistent but sub-significant at 256 seeds twice;
  `g_cPuct` default stays 2.5). Artifacts: `build/cpuct_*_128.csv`,
  `build/cpuct_{4,6}_256.csv`, `build/cpuct2_{2_5,6}_256.csv`.
- **STS_S3_EXPAND (§4.1, new code):** when no stored edge is valid in the
  current determinization (the live-valid residual, ~5.4% of rollouts at
  the deployed point), enumerate the live state's legal actions into the
  tree (action-keyed, priors on the new edges only, cap 32) instead of a
  random rollout; env `STS_S3_EXPAND=1`, `STS_S3_EXPAND_MAX` (default 32),
  requires live-valid semantics. searchdiag (6 seeds @3k/64p, deployed
  stack): illegal-stored share 0.054 → **0.0**, treeActions +10%. Gates:
  @1k/64p **35.5% vs 37.9% = −2.3pp (CI [−2.7,+7.4], flips 18/24, 16%
  discordant)**; @3k/64p **44.1% vs 42.6% = +1.5pp (CI [−6.6,+3.5], flips
  23/19)**. Mixed null at both budgets → **falsified, line closed per the
  pre-registered rule; the env stays opt-in** (`build/s3exp_{1k_64p,3k_64p}.csv`).
- **TERM_WIN + C_psi evaluator (§4.2):** the §110/§116 follow-up — terminal
  victory leaves priced with the counter-sensitive C_psi next-fight model
  (`STS_TERM_WIN=1 STS_TERM_WIN_EVAL=cpsi STS_CPSI_NN=build/v_combat_cpsi.txt`)
  instead of the counter-insensitive win tree (§110: 0 splits on counter
  features). @1k/64p: **29.3% vs 37.9% = −8.6pp (CI [+2.0,+15.2],
  SIGNIFICANT, flips 28/50) at 3.7× cpu (73.83 vs 20.34 cpu-s·run)** — the
  cross-combat setup pricing is decisively negative at the efficient point;
  **falsified, line closed** (the §116 win-tree variant was null; the cpsi
  variant is negative). Artifact `build/termcpsi_1k_64p.csv`.
- **Recording note:** the §124 config-bug accidentals (§124) double as the
  clean ablation data; this entry's arms were all verified by their
  `S3-abl[b,p,c,l,crn]=01010` banners.


## §126 Fresh honest-data combat V_combat leaf (STS_VNET, α=0.3): THREE significant gates (+12.5/+12.1/+12.5pp) — PROMOTED to default ON in the fair-S3 path (recorded cpu-trade call); §97's rejection reversed (2026-08-07, local + GCP)

- **What:** the winrate-wave boss-leaf item (§4.3 of
  `docs/archive/research/plans/plan-winrate-ideas-2026-08-07.md`), reframed by the
  evidence: a NEW combat value net trained on fresh honest trajectories,
  applied UNCONDITIONALLY at a LOW blend weight. §97's rejection (old
  1,500-tree vnet, old-era data, α0.3/0.5 under the pre-§113 stack) does not
  transfer: the boss-only conditioning idea was tested first (flat, see
  below) and the unconditional fresh model is strongly positive.
- **New labels:** `combatgen` 1,500 seeds @1k sims with the current honest
  searcher (`STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0`,
  live-valid default ON; heuristic-OOC run loop — `runCombatGenSeed`), seeds
  0-1499 → `build/vcombat_honest.csv`: **287,517 rows, 16,337 fights, 733
  features** (~3.5 min on GCP). `train_value_combat.py` (XGBoost, val-rmse
  7.99 endHp, scaling probe positive on Demon Form/Feel No Pain/etc.) →
  `export_combat_model.py` → **`build/v_combat_honest.txt`: 804 trees, 733
  features, base_score 25.97**.
- **New code:** `STS_VNET_COND_BOSS` / `STS_VNET_COND_ACT3` gate the vnet
  leaf to rollout-dominant contexts (boss fights / act 3, §117) via
  `vnetCondAllowed` (S3 `step()` leaf capture + `evaluateLeaf`); both unset
  = always on, byte-identical to pre-conditioning behavior.
- **Gates (256 seeds each, full V4 gate stack, S3−belief−chain, fair, asc 0;**
  vnet = `STS_VNET=build/v_combat_honest.txt`):
  | arm | config | win% | paired vs | Δ (95% CI) | flips | cpu |
  |---|---|---|---:|---:|---:|---:|
  | gate 1 @1k/64p | α=0.3 | **50.4%** | B2c 37.9% | **+12.5 [+5.5,+19.5]** | 60/28 | 41.2 s·run |
  | gate 2 @1k/64p (block 250000+) | α=0.3 | **50.8%** | ctl 38.7% | **+12.1 [+4.7,+19.5]** | 65/34 | 49.8 (contended) |
  | win point @3k/64p | α=0.3 | **55.1%** | B4 42.6% | **+12.5 [+6.2,+18.8]** | 52/20 | 85.5 (contended) |
  | @1k/64p | α=0.5 | 43.4% | B2c 37.9% | +5.5 [+1.2,+12.5] | 47/33 | 43.9 |
  | @3k/64p | α=0.5 | 47.7% | B4 42.6% | +5.1 [−11.7,+2.0] | 47/34 | 87.3 (contended) |
  | @1k/64p | α=0.7 | 43.8% | B2c 37.9% | +5.9 [−1.2,+12.9] | 47/31 | 42.6 |
  | @1k/64p | α=0.3 + cond-boss | 38.7% | B2c 37.9% | +0.8 [−5.5,+3.9] | 20/18 | 38.1 |
  | @1k/64p | α=0.5 + cond-boss | 38.3% | B2c 37.9% | +0.4 [−4.7,+3.9] | 17/16 | 39.2 |
  The α curve is monotone down (12.5 → 5.5 → 5.9 pp from α0.3 → 0.5 → 0.7
  at 1k): a noisy-but-right leaf blended lightly is the operating point.
  **Boss-only conditioning KILLS the benefit** (flat at both α, 13-15%
  discordance) — the vnet's value is spread across all rollout-heavy
  contexts, not just bosses.
- **Verdict: ✅ PROMOTED — default ON in the fair-S3 path.** Three
  independent significant gates (two blocks × @1k/64p, plus the @3k/64p win
  point) at α=0.3; the §123-style two-gate rule is exceeded. **Recorded
  cpu-trade call:** accept ~2-2.4× cpu (43.9-49.8 vs ~20 cpu-s·run at 1k;
  contended 3k reads inflated) for a reproducible **~+12pp win, +2-3 floor,
  +4-6 end HP** — the strongest win-rate result of the project (honest
  top: 55.1% @3k/64p vs the pre-vnet 46.9%). Scope mirrors the live-valid
  default: fires only when `STS_FAIR=1` and `STS_SEARCHER3=1` after the
  env parse; `STS_VNET` unset → default model `build/v_combat_honest.txt`
  at α=0.3; any explicit `STS_VNET=…` overrides (e.g. `STS_VNET=1` → the
  legacy `build/v_combat_trees.txt` 100-tree model at α=0.5, or
  `STS_VNET=<missing-path>` → load failure → vnet off, usable as a disable).
  `fairgen` datagen is not covered (regime forced after parse);
  `combatgen` IS covered (envs set during parse) — future combat datagen
  includes the vnet by default, aligning the label distribution with the
  deployed leaf.
- **Known caveats:** the model is trained on the heuristic-OOC run
  distribution (combatgen's own loop, not the V4 gate stack); the transfer
  to the gate-stack distribution is measured empirically (it works) but a
  gate-stack-distribution retrain is the natural follow-up. S2 fair and
  non-fair paths unchanged (env-only). The vnet leaf adds ~0.2-0.3 ms per
  blended leaf eval (804 trees).
- **Artifacts:** `build/vcombat_honest.csv` (1 GB, ignored),
  `build/v_combat_honest.{json,txt,val.csv}`, per-seed gate CSVs
  `build/vnet_{all_a03_1k,all_a05_1k,all_a07_1k,boss_a03_1k,boss_a05_1k,a03_3k,all_a05_3k}.csv`,
  `build/vnet2_{ctl,a03}_250k.csv`; code `vnetCondAllowed`,
  `g_vnetCondBossOnly`/`g_vnetCondAct3` (`BattleScumSearcher3.cpp`,
  `apps/one_combat.cpp`). Model sha256 in
  `docs/knowledge-base/evaluation/current-baselines.md`.
- **Cost:** datagen ~3.5 min + training ~10 min + export on the desktop;
  each 256-seed arm ~7-30 min wall on GCP.
## §124b Prior-guided S3 rollouts (STS_S3_ROLLOUT_POLICY): implemented opt-in; smoke fires, ~2.4× cpu; paired 256-seed gate pending vs the §126 vnet default (2026-08-07, local WSL)

- **What:** revives the parked §119 "Phase 3 (policy-guided rollouts)": with
  `STS_S3_ROLLOUT_POLICY=1`, `BattleScumSearcher3::playoutRandom` samples
  rollout actions from the **GBM policy prior** (`computeEdgePriors` — the
  same distribution PUCT priors use, `build/policy_trees_c.txt` auto-loaded)
  instead of the static `rolloutWeight` heuristic (ATTACK=8/POWER=3/other=2/
  END_TURN+POTION=1 — the rollout was never truly uniform; this replaces the
  hand-authored bias with the learned prior). Restricted to the GBM policy
  net (`g_usePolicyNet && loaded()`, not shadowed by a PVNet policy head) —
  a PVNet-head forward per rollout step would cost ~14-18× a sim. Default
  off; the heuristic branch is untouched, so unset = byte-identical.
  Rationale: with the §126 vnet leaf (α=0.3) the rollout outcome carries 70%
  of the leaf blend — rollout quality matters more than pre-vnet.
- **Config (smoke):** `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64` (vnet α=0.3 default ON; no PVNet),
  `./build/one_combat bestbench 300 8 0 0 <out.csv>`, seeds 0-7.
- **Results (8 seeds @300 sims — smoke only):**
  | arm | win% | avg_floor | cpu_sec/run |
  |---|---|---|---|
  | control (heuristic rollout) | 12.5 | 38.2 | 7.5 |
  | `STS_S3_ROLLOUT_POLICY=1` | 25.0 | 44.0 | 18.2 |
  Outcomes differ on most seeds (won differs on seed 6); banner prints
  `[S3 rollout-policy = ON]`. 2.4× cpu = per-step GBM prior evals; win-rate
  deltas are 8-seed noise, not evidence. `ctest` 5/5.
- **Pre-registered gate (pending, GCP):** paired 256-seed @1k/64p on the
  §126 config vs `build/vnet_all_a03_1k.csv` (50.4%); then @3k if positive.
  Known risk: prior-guided rollouts may collapse rollout diversity and make
  Q estimates self-consistent but overconfident — a null or negative closes
  the line. A temperature/mixture knob with the heuristic is the obvious
  follow-up if the pure-prior version collapses.
- **Artifacts:** `build/pri0_{ctl,pol}.csv` + logs. Code:
  `BattleScumSearcher3::playoutRandom` (`src/sim/search/BattleScumSearcher3.cpp`),
  `apps/one_combat.cpp` env parse, header extern. Decision log:
  `2026-08-07-prior-guided-rollouts.md`. KB: `combat-search.md` (rollout
  section).
## §124c Prior-guided S3 rollouts — paired 256-seed gate: SIGNIFICANTLY NEGATIVE (−7.0pp) — line closed (2026-08-07, GCP sts-test)

- **What:** the §124b pre-registered gate for `STS_S3_ROLLOUT_POLICY=1`
  (rollout actions sampled from the GBM policy prior instead of the static
  `rolloutWeight` heuristic). Pre-registered rule: null or negative closes
  the line (diversity-collapse risk was the known failure mode).
- **Config (both arms):** full V4 gate stack (`STS_OOC_STRATEGIC_TOK_NN=
  selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/
  BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`), `STS_FAIR=1 STS_SEARCHER3=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, vnet α=0.3 default ON,
  block 126700–126955 (256), asc 0, 24 threads; policy arm adds
  `STS_S3_ROLLOUT_POLICY=1`. Commit 3f04e82 + the §124b source sync
  (BattleScumSearcher3.{h,cpp}, one_combat.cpp).
- **Results (paired, `paired_analysis.py`):**
  | metric | control (heuristic rollout) | policy-prior rollout | delta |
  |---|---|---:|---:|
  | win | **50.4%** (129/256) | **43.4%** (111/256) | **−7.0pp, 95% CI [−13.7, −0.4]** |
  | avg floor | 44.1 | 42.8 | −1.3 (CI [−2.6, 0.0]) |
  | avg HP end | 29.4 | 22.7 | −6.7 |
  | cpu-s/run | 30.5 | 83.8 | +2.7× (mostly uncontended reads) |
  Discordant 76/256 (30%): control-only 47, policy-only 29.
- **Sanity:** the control arm reproduces the §126 reference exactly (50.4%,
  129/256 — same block/config), so the pairing is clean. Banner confirms
  `[S3 rollout-policy = ON]` on the policy arm.
- **Verdict: ❌ falsified, line closed per the pre-registered rule.** The GBM
  prior — trained on older-policy visit distributions — actively HURTS
  rollouts: −7.0pp significant at 2.7× cpu. No @3k re-gate (pre-registered:
  only if positive). The env stays opt-in (no behavior change unset);
  follow-ups (temperature/mixture with the heuristic) are NOT pursued unless
  the prior is retrained on current-stack data (the §126-vnet-era policy
  prior v2 line in winrate-plan §3.4 is the natural prerequisite).
- **Artifacts:** `build/pri1_ctl_256.csv` (control; md5
  4106e1deb6a76e094a87b70ba9c9ea64), `build/pri1_pol_256.csv` (policy arm;
  md5 4ef1416c17a1790d0dfb16c3942dd760), logs on sts-test
  `build/pri1_{ctl,pol}_256.log`; local smoke `build/pri0_{ctl,pol}.csv`
  (§124b). KB: `combat-search.md` (prior-guided rollouts section updated to
  the verdict). Decision log: `2026-08-07-prior-guided-rollouts.md` (verdict
  appended).
## §127 Policy prior v2 pipeline (winrate-plan §3.4+§3.5): fairgen datagen (1000 seeds, vnet-α0.3-aligned, 22-action-feature producer) + v2 prior trained + policystats bug fix; paired gate pending (2026-08-07, GCP + local)

- **What:** the merged §3.4/§3.5 pipeline. Datagen: `fairgen 1000 1000 0 0.3
  build/fair34_{v,p,o}.csv 400000` on GCP with `STS_LIVE_VALID=1
  STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64` **plus explicit
  `STS_VNET=build/v_combat_honest.txt STS_VNET_ALPHA=0.3`** (recorded
  deviation: §3.4 predates the §126 promotion; aligns the policy rows with the
  deployed controller; without the alpha the explicit env defaults to the
  legacy 0.5). Producer is the §3.5 22-action-feature build (1766 state + 22
  action): `aSelectSize, aSelTotalCost, aSelAtk/Skl/Pow, aSelUpgraded,
  aSelPlayOrder, aSelObtainWeight` appended after the original 14 (PVNet
  first-14 and old model-nfeat paths unaffected). Output: 225,057 value +
  933,458 policy (1793 cols) + 21,319 ooc rows in 431s; CSVs pulled to
  `build/fair34_{v,p,o}.csv`.
- **Training:** `train_policy.py build/fair34_p.csv build/policy_v2.json
  build/policy_trees_c_v2.txt` (100 trees, 751 non-constant features, GPU) —
  in-sample top1 0.544, visit-share 0.477.
- **Policystats bug found + fixed (pre-existing, not introduced here):** the
  mode stored the action block only in `act` (the optional PVNet comparison)
  and never into `feat`, so the GBM `predictVec` path always saw zeroed action
  features → uniform per-group softmax (CE == gbmEntropy) for every policy
  model. Fixed: action block now also fills `feat`; `actionN` is derived from
  the actual CSV header (14 pre-§3.5, 22 since) instead of the current
  producer count, so old and new CSVs both analyze. This is the first honest
  offline prior comparison the tool has produced.
- **Offline comparison (both models, all 933,458 rows of the new data):**
  | metric | tracked `policy_trees_c.txt` | v2 `policy_trees_c_v2.txt` |
  |---|---|---:|
  | top1 agreement | 0.5522 | 0.5454 |
  | CE | 1.3327 | **1.2397** |
  | KL | 0.6209 | **0.5279** |
  | regret (1 − p\*) | 0.5192 | 0.5225 |
  | gbmEntropy | 1.4359 | 1.3072 |
  v2 clearly better on CE/KL (≈0.09), tied on top1/regret. Note: tracked was
  trained on old-distribution rows, so this overstates v2's edge; the paired
  gate decides.
- **Gate (running on GCP):** two arms @1k/64p, block 126700, full V4 stack +
  vnet default: control (default tracked prior) vs `STS_POLICY=
  build/policy_trees_c_v2.txt`; provenance verified via `/proc/PID/environ`.
  Pre-registered (§3.4): a null closes the prior-v2 line.
- **Artifacts:** `build/fair34_{v,p,o}.csv` (3.4 GB p CSV, 822 MB v, local +
  sts-test), `build/policy_trees_c_v2.txt` (179 KB; sha256 recorded at gate
  close), `build/policy_v2.json`, `build/ptrain_v2.log`, GCP logs
  `build/fair34.log`, `build/pri2_{ctl,v2}_256.log`. Code:
  `combatFillActionFeatures` (§3.5 features), policystats fix
  (`apps/one_combat.cpp`). Decision log:
  `2026-08-07-policy-prior-v2-pipeline.md`.
- **Gate verdict (appended, 2026-08-07): ❌ NULL — line closed per the
  pre-registered rule.** Paired 256-seed @1k/64p, block 126700, full V4 stack
  + vnet default: v2 prior **48.4% vs tracked 50.4% = −2.0pp (95% CI
  [−8.2,+4.3])**, floor −1.5 (CI [−2.9,−0.1]), HP −4.2, cpu equal (73.8 vs
  75.7 s/run). Discordant 71/256 (tracked-only 38, v2-only 33). Control
  reproduced the §126 reference exactly (129/256 = 50.4%) — clean pairing.
  The better offline CE/KL (−0.09) does not transfer to the deployed PUCT
  stack — the same pattern as §124c (prior-guided rollouts): prior-quality
  improvements measured offline do not translate online at this configuration.
  v2 artifact kept for reference (`build/policy_trees_c_v2.txt`, 100 trees,
  751 feats, sha256 30ea8598…). No @3k re-gate (pre-registered: only if
  positive).
## §128 Value-only utility-distribution model (plan-value-targets phase 5): trained on the §3.4 fairgen rows; ~4× better win calibration than the tracked PVNet on the same held-out rows (2026-08-07, local)

- **What:** phase 5 of `docs/archive/research/plans/plan-value-targets-2026-08-07.md`:
  a value-only transformer (same 14-token encoder as CombatPVNet, NO policy
  head) predicting a 51-bin categorical over the MCTS terminal utility
  R = 0 on loss, 50 + endHp on win (bin 0 = loss; bins 1-50 = endHp/maxHp
  fraction on wins, mapped by maxHp at inference). Loss = CE; win prob =
  1 − p(bin 0); EV = Σ p_b·(50 + maxHp·mid_b). New trainer
  `train_combat_utility.py` + eval `eval_combat_utility.py`; native export
  format `combat_utility_v1` (encoder section identical to `combat_pvnet_v1`,
  single `util` head) with Python-side loader support added to
  `combat_pvnet_parity.py`. No C++ integration (deployment is not part of
  this phase; the vnet owns the leaf, §126).
- **Data:** `build/fair34_v.csv` (225,057 rows, §127 datagen: vnet-era,
  live-valid, current controller, rich labels). 12 epochs, D=128, 2 layers,
  4 heads, AdamW 1e-4, batch 1024, GPU (RTX 3060 Ti); held-out val CE 2.69
  (ln(51)=3.93 random). Checkpoint selection = val-seed CE (sibling
  ranking/regret later). Artifacts: `build/v_combat_utility.txt`
  (combat_utility_v1), `build/train_utility5.log`,
  `build/eval_utility_fair34.json`.
- **Results (same 30,000 held-out val rows of fair34_v.csv, seed%100<20):**
  | metric | tracked PVNet `v_combat_pvnet.txt` (old fair_v data) | utility model (fresh data, 51-bin) |
  |---|---|---:|
  | win Brier | 0.2505 | **0.0647** |
  | win ECE | 0.3298 | **0.0688** |
  | death BCE | 2.2076 | **0.2287** |
  | bin CE | — | 2.6917 |
  | EV MAE (terminal scale) | — | 13.3 |
  - **Finding 1 (distribution gap):** the tracked PVNet is badly
    miscalibrated on the new distribution — 0.2505 Brier / 0.33 ECE vs its
    0.107/0.002 recorded on its own (old, weaker-controller) training data.
    Direct evidence for the phase-2-4 premise of the value-targets plan.
  - **Finding 2 (target+data):** fresh data + direct terminal-utility
    distribution beats the old-data win/quantile reconstruction ~4× Brier,
    ~5× ECE, ~10× death BCE on identical rows. Caveat: data and target
    changed together — a clean target-only ablation (same data) and the
    shared-encoder variant (does policy sharing hurt value?) are follow-ups.
- **Scope note:** nothing deployed changes; the PVNet and VNet artifacts are
  untouched. The phase's purpose is offline research that informs the next
  vnet retrain (the §126 gate-stack-distribution follow-up, in progress by
  another agent): the fresh-data + direct-target recipe is transferable to
  GBM training (`train_value_combat.py`).
- **Deferred:** shared-encoder variant (needs the dual-CSV policy pass),
  C++ `CombatPVNet::load`/`leafValue` support for `combat_utility_v1`
  (only useful when a deployment gate exists), sibling-ranking eval (needs
  phase-2/3 data).
- **Artifacts:** `build/v_combat_utility.txt`, `build/v_combat_utility_smoke.txt`,
  `build/eval_utility_fair34.json`, `build/eval_pvnet_fair34.json` (PVNet
  reference on the same rows), logs. Code: `train_combat_utility.py`,
  `eval_combat_utility.py`, `combat_pvnet_parity.py` (utility-format
  parsing). Decision log: `2026-08-07-value-only-utility-net.md`.

## §129 Gate-stack-distribution vnet retrain (STS_DATAGEN_GATES): NULL vs the deployed model at both operating points; the α optimum shifts 0.3→0.5, confirming better calibration but no replacement (2026-08-07, local + GCP)

- **What:** the §126 follow-up — retrain the combat value leaf on labels from
  the DEPLOYED run-level distribution (V4 one-ply gate stack) instead of
  `combatgen`'s heuristic-OOC loop, and gate whether the gate-stack model
  replaces the deployed honest-data model. New code: `STS_DATAGEN_GATES=1`
  routes `runCombatGenSeed`'s OOC decisions through the same opt-in one-ply
  gate chain as `bestbench` (`datagenGateStack` dispatch + the card-reward
  gate in the REWARDS branch; each gate self-guards on its env flag + model
  load; unset behavior verified byte-identical on 10 seeds).
- **New labels:** `combatgen` 1,500 seeds @1k sims (fresh offset 1500-2999)
  with the gates ON (plus the §126 vnet default, which combatgen covers) →
  `build/vcombat_gated.csv`: **499,089 rows, ~1.74× the heuristic-OOC set
  (gated runs survive longer → more fights)**. Trained (val-rmse 10.83
  endHp — higher than the heuristic set's 7.99, reflecting the harder
  long-run label distribution; scaling probe positive on all tested
  powers) → exported `build/v_combat_gated.txt`: **738 features, 733 trees,
  base_score 36.41, sha256 `5322c9f1…`**.
- **Gates (256 seeds, block 126700, full V4 gate stack, S3−belief−chain,
  64p, fair; paired vs the no-vnet §124 references and vs the deployed
  honest model's best points):**
  | arm | win% | vs no-vnet | vs deployed (honest α0.3) |
  |---|---|---|---|
  | @1k/64p α0.3 | 46.1% | +8.2pp (CI [+0.8,+15.6]) | **−4.3pp (CI [−10.9,+2.3])** |
  | @1k/64p α0.5 | **53.1%** | +15.2pp (CI [+8.2,+22.3]) | **+2.7pp (CI [−9.4,+3.5])** |
  | @1k/64p α0.7 | 47.3% | +9.4pp | −3.1pp |
  | @3k/64p α0.3 | 52.7% | +10.1pp | −2.4pp |
  | @3k/64p α0.5 | **52.0%** | +9.4pp (CI [+2.0,+16.4]) | **−3.1pp (CI [−3.5,+9.4])** |
  The gated model's α optimum shifts UP (0.5 vs the honest model's 0.3) —
  consistent with better calibration on the deployment distribution — but at
  its own optimum it does not beat the deployed model: **−4.3pp @1k/α0.3,
  +2.7pp @1k/α0.5, −3.1pp @3k/α0.5 — all n.s., direction mixed.**
- **Verdict: NULL for replacement — the deployed honest-data model
  (`build/v_combat_honest.txt` @α0.3) STAYS.** Both models strongly beat
  no-vnet at both operating points (the §126 result is robust to the label
  distribution); the gate-stack retrain adds nothing significant and is
  not promoted. `STS_DATAGEN_GATES` stays opt-in (useful if datagen
  distribution alignment is wanted for other labels).
- **Artifacts:** `build/vcombat_gated.csv` (ignored),
  `build/v_combat_gated.{json,txt,val.csv}`, per-seed gate CSVs
  `build/gv_{a03_1k,a05_1k,a07_1k,a03_3k,a05_3k_final}.csv` (the α0.5 @3k
  arm was resumed mid-run at 24 threads: 171+81+4 gap seeds merged by seed —
  a kill/restart resume pattern that works because `bestbench` rows are
  per-seed and seed-order-independent; issue 46's append-without-dedup
  applies). Code: `datagenGateStack`, `g_datagenGates`
  (`apps/one_combat.cpp`, `runCombatGenSeed`).
- **Cost:** datagen ~40 min local (12 threads); training + export ~15 min
  local; gates ~3×22 min + 2×45 min (8 threads) + 1×4 min resume (24
  threads) on GCP.

## §130 5.2 counter-aware OOC pricing — CLOSED on evidence, no retrain gate (2026-08-07, local diagnostic only)

- **What:** plan `plan-winrate-ideas-2026-08-07.md` §5.2 (counter-aware OOC
  pricing): the deployed win tree has zero counter-relic sensitivity (§110:
  0/1,060 splits on the eight counter features despite all being among its
  448 selected features), and the plan proposed fixing it by (a) retraining
  the win GBM on a corpus with populated counter columns, or (b) a C_psi
  next-fight survival term for rest/event decisions. Closed **without** a
  retrain gate by user decision after the diagnostic below.
- **Diagnostic (this session, read-only):** the fresh deployed combat vnet
  (`build/v_combat_honest.txt`, 804 trees, 287,517 honest `combatgen` rows)
  assigns the counter features ~0.01% of total split gain (Happy Flower
  0.0047%, Incense Burner 0.0073%, Ink Bottle 0.0009%; Nunchaku/Pen Nib/
  Sundial/Panache below that) — and its training data HAD real counter
  variance: happyFlowerCtr 0-2 (6,075 nonzero rows), incenseBurnerCtr 0-5
  (3,086), inkBottleCtr 0-9 (3,577), nunchakuCtr 0-9 (7,879), penNibCtr
  −1..8 (7,160), sundialCtr 0-2 (2,677), panacheCtr −5..5 (148); only
  inserterCtr was constant 0 (correctly — Inserter is a Defect-only relic
  and the agent plays Ironclad).
- **Evidence chain (four independent readings):** (1) §110 win tree
  0/1,060 splits; (2) this diagnostic — a second, fresh-data GBM also
  reads no signal in counters conditional on HP/gold/potions/deck; (3)
  §116 — the controlled forced-Happy-Flower benchmark found no winrate or
  stall-behavior benefit from counter-aligned play; (4) §125 — the
  counter-SENSITIVE evaluator (C_psi) applied at the combat leaf was
  significantly NEGATIVE (−8.6pp, CI [+2.0,+15.2]).
- **Verdict:** the counter-insensitivity is the models correctly reading
  "no signal", not a data artifact; OOC decisions (rest vs upgrade, events,
  shop, pathing) barely depend on counter state, and the in-combat
  energy-tick signal the counters carry is already visible to the deployed
  combat vnet (§126). The §110 open question ("counter pricing requires a
  counter-aware terminal model") is answered negatively for the OOC side;
  the combat-side counter-pricing line was already closed (§116, §125).
  **5.2 closed; no retrain gate, no code change, nothing deployed.**
- **Artifacts:** none (diagnostic only; computed from the tracked
  `build/v_combat_honest.txt` JSON and `build/vcombat_honest.csv`).
- **Cost:** ~15 min local, read-only.

## §131 Target-vs-data ablation (phase-5 follow-up): fresh data is the big lever (2.7×), the 51-bin utility target still adds 31% on identical data (2026-08-07, local)

- **What:** isolates the two changes conflated in §128. Trained the
  old-style PVNet (win/death/quantile/potion/turns heads, shared encoder) on
  the SAME fresh rows as the §128 utility model (`train_combat_pvnet.py` on
  `build/fair34_v.csv` + `build/fair34_p.csv`, 10 epochs, batch 1024, best
  val 1.487 → `build/v_pvnet_fresh.txt`). Trainer fixed for the §3.5
  22-action-feature policy CSV (slices the first 14 for the PVNet action
  encoder, mirroring the eval/parity scripts).
- **Results (identical 30,000 held-out val rows of fair34_v.csv):**
  | metric | old PVNet (old fair_v data) | fresh PVNet (fresh data, old target) | utility 51-bin (fresh data, new target) |
  |---|---|---:|---:|
  | win Brier | 0.2505 | 0.0940 | **0.0647** |
  | win ECE | 0.3298 | 0.0987 | **0.0688** |
  | death BCE | 2.2076 | 5.2731 | **0.2287** |
  - Data effect: fresh-data-only retrain 0.2505 → 0.0940 Brier (2.7×) —
    the distribution-gap finding (§128) stands; training on the current
    controller's rows is the bigger lever.
  - Target effect: the 51-bin terminal-utility head on IDENTICAL data still
    beats the win/quantile heads: 0.0940 → 0.0647 Brier (−31%), ECE −30%.
  - The fresh PVNet's separate death head collapsed (death BCE 5.27, predicts
    ≈0 death always) while its win head is fine — the utility head gets death
    probability for free from bin 0 (0.2287) — evidence for the single-head
    design.
- **Interplay with §129 (gate-stack vnet retrain, NULL):** the parallel
  session's fresh-data retrain kept the endHp-regression target and did NOT
  replace the deployed vnet — so on the GBM side a data-only retrain is
  already exhausted. This ablation shows the target change is a separate,
  measurable lever (31% Brier on identical transformer rows) — the untested
  combination is a GBM with a distribution/quantile target over
  R = 0 | 50+endHp instead of endHp regression (`train_value_combat.py`
  endHp target; `train_combat_cpsi.py` already uses fraction targets).
  Same GBM architecture, better target — the cheap deployable path.
- **Artifacts:** `build/v_pvnet_fresh.txt`, `build/eval_pvnet_fresh.json`,
  `build/train_pvnet_fresh.log`. Decision log:
  `2026-08-07-value-only-utility-net.md` (appended).

## §132 Target experiment on the GBM leaf: quantile regression on the terminal utility R vs raw endHp — same rows, same model class; EV on-scale (10.1 vs 45.9) (2026-08-07, local)

- **What:** the §131-recommended deployable test: does the target change
  (not the model) transfer to the GBM? Two 9-quantile XGBoost models
  (τ=0.1..0.9, 150 rounds, depth 6, `reg:quantileerror`) on the SAME rows
  as the deployed vnet (`build/vcombat_honest.csv`, 287k rows, same
  GroupShuffleSplit val 0.15/random_state 0), differing only in label:
  utility_R = won ? 50+endHp : 0 vs raw endHp. The R target also cleans the
  493 abandoned-fight rows (loss with endHp>0 in the old target). A 51-class
  softprob port would cost ~50× the trees; 9 quantiles of R is the cheap
  distributional equivalent (low quantiles = death mass, P(win) ≈
  mean(q_τ > 0)).
- **Results (val, 43k rows; deployed model evaluated on the identical rows):**
  | model | EV-MAE vs R | win Brier (from quantiles) |
  |---|---|---:|
  | deployed vnet (endHp regression, 804 trees) | 45.90 | — |
  | quantile endHp (old target, 9×150 trees) | 45.89 | 0.0739 |
  | **quantile utility_R (new target, 9×150 trees)** | **10.10** | 0.0851 |
  - The utility target's mean-of-quantiles is directly on the leaf's terminal
    scale; both endHp variants miss R by ~50·P(win) ≈ 46 — the scale
    mismatch the deployed stack compensates via the α-blend and
    rank-sensitivity (and the §123 HP-scale saga).
  - Win-prob-from-quantiles is slightly worse for the R target (0.085 vs
    0.074) — the endHp quantiles split the 0 boundary marginally better;
    the leaf would use EV (and optionally CVaR) directly, not this coarse
    win estimate.
  - Quantile coverage well calibrated for both (L2 ≈ 0.02).
- **Interpretation:** the §128/§131 finding (direct utility target beats
  the reconstructed target) transfers to the deployable GBM class. The
  deployed vnet's endHp prediction is ≈46 HP off the utility scale; an
  EV-on-scale leaf could allow a higher α (cf. §129: gated model's α
  optimum shifted 0.3→0.5 with better calibration).
- **Next (deployment experiment, not run):** export the 9 quantile tree sets
  in a C++-consumable format + `leafValue` = mean-of-quantiles (± CVaR risk
  term), α sweep, paired 256-seed gate vs the deployed vnet §126 config.
  Tree cost: 9×150 ≈ 1350 trees ≈ 1.7× the deployed 804-tree eval —
  acceptable at the §126 cpu-trade bar.
- **Artifacts:** `build/vcombat_q{,_150}_results.json`, `train_vcombat_quantile.py`.
  Decision log: `2026-08-07-vnet-target-experiment.md`.
## §133 Rollout-leaf estimator experiments A1/A4 (STS_S3_ROLLOUT_K, STS_S3_ROLLOUT_TURN_STOP): implemented opt-in with structural-equality check; gates held for the §131/§132 leaf-net verdict (2026-08-07, local WSL)

- **What:** two opt-in Searcher3 rollout-leaf estimators (plan: A1 + A4 of the
  rollout-ideas session; gates deferred per the split decision until the
  other session's leaf-net verdict lands, because both arms modify the same
  α-blend leaf the new net would redeploy):
  - **A1 (`STS_S3_ROLLOUT_K`, default 1):** run K independent rollouts from
    the same pre-rollout leaf state and average their outcomes; backprop once
    (single visit). Reduces rollout-outcome variance without changing PUCT
    visit counts or tree exploration. `BattleScumSearcher3::multiRollout`
    (`src/sim/search/BattleScumSearcher3.cpp`), used at both rollout sites in
    `step()` (leaf-expansion blend site and the fair-illegal-stored-edge
    fallback). The first rollout's actions go into `actionStack` so
    `bestActionSequence` stays replayable; caller `state` is left unmutated
    (each rollout runs on its own `BattleContext` copy).
  - **A4 (`STS_S3_ROLLOUT_TURN_STOP=N`, default 0):** stop the rollout after
    N completed player turns (turn boundary = `bc.turn` increment inside the
    END_TURN action chain, `BattleContext::afterMonsterTurns`); the
    non-terminal endpoint is then evaluated by the learned leaf, giving
    `α·VNet(s0) + (1−α)·VNet(s1)` — an n-step bootstrap, distinct from the
    §119 capped-rollout gate (which used the pre-vnet heuristic endpoint on
    Searcher2).
- **Verification (local smoke, 8 seeds @300 sims + searchdiag3, 2 seeds
  @300):** structural equality — `STS_S3_ROLLOUT_K=1` reproduces the unset
  arm byte-identically on all 8 seeds (all game columns); behavior fires —
  K=2 rolloutActions ≈ 2.03× control (1,946,275 → 3,952,264; per-leaf
  rollouts independent, 7/8 seeds' outcomes differ); turn-stop=1 collapses
  avgRolloutLen 13.94 → 2.50 (rolloutActions 232,681) and differs on 8/8
  seeds. `ctest` 5/5. Artifacts: `build/rk_{ctl,k1b,k2b,ts1}_8.csv`,
  `build/rk_sd_{ctl,k2b,ts1}.csv`. Banner + BEST-stack provenance:
  `S3-rollK=` / `S3-turnStop=`.
- **Pre-registered gates (pending, GCP):** paired 256-seed @1k/64p on the
  §126 config vs `build/vnet_all_a03_1k.csv` (50.4%): (1) K=2 @500 sims
  (equal rollout-action budget — the deployment question), (2) K=2 @1000 only
  if (1) is positive/neutral (same tree size, ~2× cpu), (3) turn-stop N=1
  @1k (and an equal-CPU reinvestment arm if positive/neutral). Gate ordering
  after the §131/§132 leaf-net verdict: a promoted net re-bases the pairing.
  Decision log: `2026-08-07-rollout-leaf-estimators.md`.
- **Gate verdicts (appended, 2026-08-07, GCP sts-test):** the §131/§132
  quantile-R leaf was **SIGNIFICANTLY NEGATIVE at every α — deployed vnet
  STAYS** (see the second §133 entry), so the pairing baseline is unchanged
  (`build/vnet_all_a03_1k.csv`, 50.4% @1k/64p). Three paired 256-seed gates
  ran (block 126700–126955, full V4 stack, S3−belief−chain/64p, fair, asc 0,
  24 threads, vnet α0.3 default ON):
  | arm | config | win% | Δ vs ctl (95% CI) | floor Δ | HP Δ | cpu-s/run |
  |---|---|---|---:|---:|---:|---:|
  | A1 gate 1 | K=2 @500 sims (equal rollout budget) | 49.2% | −1.2 [−7.4,+5.1] | −0.5 | −4.0 | 16.8 (−59%) |
  | A1 gate 2 | K=2 @1000 sims (equal tree size) | 48.4% | −2.0 [−8.2,+4.7] | −0.1 | −2.3 | 32.4 (−21%) |
  | A4 gate | turn-stop N=1 @1k | 34.0% | **−16.4 [−23.0,−9.4]** | −2.4 [−3.9,−1.0] | −10.9 | 33.6 (−18%) |
  | A1 gate 3 | K=10 @100 sims (equal rollout budget, extreme) | 35.5% | **−14.8 [−21.1,−8.2]** | −3.5 [−5.0,−2.1] | −10.3 | 7.7 (−81%) |
  Discordance 69/256 (27%), 71/256 (28%), 90/256 (35%), 80/256 (31%) respectively.
- **A1 verdict: ❌ NULL — line closed.** Averaged K-rollouts are neutral at
  both operating points (slightly negative direction, CIs span zero): at
  equal rollout-action budget the variance reduction roughly offsets the
  halved tree (−1.2pp), and at equal tree size there is no measurable gain
  (−2.0pp; K=2 also died in 8 more combat fights, 111→119, at −21% wall
  time — fewer decisions per run, consistent with slightly worse play, not
  a speedup from variance reduction). The user-requested extreme point
  K=10 @100 sims (equal rollout budget, 10× smaller tree) is
  **SIGNIFICANTLY NEGATIVE: −14.8pp (CI [−21.1,−8.2])** — tree size
  dominates: reducing the search tree 10× while holding rollout work
  constant collapses win rate, so the α0.3 blend's 70% rollout share is not
  variance-bound at this operating point and variance reduction does not
  pay for lost tree traversals at any tested ratio. Pre-registered K=4 not
  run (only if K=2 positive). Env stays opt-in.
- **A4 verdict: ❌ FALSIFIED — line closed.** One turn + VNet bootstrap is
  significantly worse than the full terminal rollout: −16.4pp (CI excludes
  zero), floor −2.4 (CI excludes zero), HP −10.9, and cpu barely drops
  (−18% — the endpoint vnet evals dominate, not the skipped rollout
  actions). This is the second falsification of the short-rollout family
  (§119 caps −5.9pp with the pre-vnet heuristic endpoint; this is worse
  because the rollout here is ~1 turn long, avgRolloutLen 2.50 in the
  local smoke, vs §119's 8-action caps). Long-horizon terminal grounding
  through the full rollout is load-bearing for the leaf blend; per the
  pre-registered decision tree, B1 (turn-beam) must continue across turns.
  Env stays opt-in.

## §133 Quantile-R GBM leaf (target experiment, §132 deployment gate): SIGNIFICANTLY NEGATIVE at every α — deployed vnet stays; offline EV calibration does not transfer (2026-08-07, GCP)

- **What:** the §132-recommended deployment gate for the quantile-R GBM
  leaf: `combat_quantile_v1` native format (9 tree sets, τ=0.1..0.9, 150
  rounds, depth 6, over R = won ? 50+endHp : 0), C++ loader +
  `predictQuantileEV` (mean of quantiles, on the terminal scale; dispatch in
  `CombatValueNet::predictVec`, so no searcher changes), parity PASS vs
  Python (max diff 0.0005, `vnettest` on 1999 val rows). Trained on the same
  rows as the deployed vnet (`build/vcombat_honest.csv`); val EV-MAE vs R
  10.10, quantile coverage L2 0.022 (vs 45.90 for the deployed endHp model).
- **Gates (256 seeds, block 126700, full V4 stack, S3−belief−chain/64p,
  paired vs the §126 deployed-vnet control `build/vnet_all_a03_1k.csv`,
  50.4% — reproduced twice on this block, §124c/§127):**
  | arm | win% | Δ (95% CI) | floor Δ | HP Δ | cpu-s/run |
  |---|---|---:|---:|---:|---:|
  | quantile-R α0.3 | 37.5% | −12.9pp [−19.9, −6.2] | −2.4 | −5.5 | 68.5 |
  | quantile-R α0.5 | 40.2% | −10.2pp [−17.2, −3.1] | −3.4 | −6.0 | 85.6 |
  | quantile-R α0.7 | 32.0% | −18.4pp [−25.4, −11.3] | −3.7 | −11.0 | 80.9 |
  All three SIGNIFICANTLY negative, at 1.7-2× the deployed cpu
  (41.2 s/run). The α curve is inverted vs §129's gated model (which
  improved with α 0.3→0.5): here higher α is worse — the EV-on-scale
  leaf's in-tree ranking is worse than the deployed endHp model's, and
  heavier blending makes it worse.
- **Verdict: ❌ line closed; the deployed honest-data vnet (§126)
  STAYS.** The §132 offline finding (EV-MAE 10.1 vs 45.9) does not
  transfer — the third consecutive offline≠online falsification
  (§124c prior-guided rollouts, §127 prior v2, now the target
  experiment). Hypothesis: the deployed endHp model's under-scaled value
  blended at α0.3 acts as a ranking-friendly prior over the rollout's
  terminal scale; the "correctly scaled" EV value is not better at ranking
  tree states, and the mean-of-9-quantiles estimator is crude for the
  bimodal R distribution (90% wins). The transformer 51-bin CE model
  (§128/§131) remains the best offline value signal but has no
  deployable GBM port yet; the §126 vnet-retrain line (data side) stays
  as recorded.
- **Artifacts:** `build/v_combat_quantile.txt` (kept as reference), gate CSVs
  `build/vq_{a03,a05,a07}_256.csv`, logs on sts-test, parity
  `/tmp/vq_parity.csv`. Code: `CombatValueNet::load`/`predictQuantileEV`
  (`src/sim/search/CombatValueNet.{h,cpp}`), `combat_quantile_v1` exporter
  `train_export_vcombat_quantile.py`. Decision log:
  `2026-08-07-vnet-target-experiment.md` (verdict appended).

## §134 Audit of §132/§133 + faithful target-only ablation on the direct utility-R GBM: §132 was NOT a target-only test; a same-recipe direct-R model is ALSO SIGNIFICANTLY NEGATIVE at α0.1 — deployed vnet stays; tooling hardened (2026-08-07, local)

- **What:** a methodological audit of the §132/§133 records (user-requested),
  tooling hardening, and one narrowly scoped follow-up that tests the §132
  target hypothesis without its confounds. The §133 deployment verdict is
  preserved; §132's offline narrative is corrected by this addendum (historical
  rows above are NOT silently rewritten).
- **§132 audit (confounds found):** §132 claimed "same rows, same model class —
  differing only in label". That is not what was implemented:
  `train_vcombat_quantile.py` / `train_export_vcombat_quantile.py` replaced the
  deployed recipe (`train_value_combat.py`, depth 8, eta 0.05,
  early-stopping up to 1500 rounds, weighted squared error, 804 exported
  trees) with nine unweighted `reg:quantileerror` models (depth 6, eta 0.1,
  fixed 150 rounds, 1350 trees). So the §132 comparison confounded target
  with recipe/capacity/objective-class. The headline "EV on-scale (10.1 vs
  45.9)" is also partly a scale artifact: an end-HP predictor is ~50·P(win) ≈
  46 off the R = 0 | 50+endHp scale by construction, so its MAE vs R is a
  scale mismatch, not evidence it ranks search states worse. The
  mean-of-9-quantiles is a coarse numerical approximation of the expectation,
  especially for the bimodal R distribution. None of this invalidates the
  §133 online gate — the quantile leaf was rejected on paired gameplay, which
  is independent of the offline EV-MAE framing.
- **§133 audit (verdict preserved, wording scoped):** the quantile deployment
  gate itself is decisive for the implemented candidate: native/Python parity
  was checked, the fair Searcher3 config matched the §126 control, and the
  recorded α values were all significantly negative. The claim "every α" is
  scoped to **the three tested α (0.3, 0.5, 0.7)** — not a statement about all
  possible α. The A1 rollout verdict is also narrower than the §133 text
  implied: `BattleScumSearcher3::multiRollout` copies one `BattleContext`
  (including all simulator RNG streams) for every replicate, so the K rollouts
  are independent action-policy samples conditional on **copied simulator
  RNG**, NOT fully independent environment samples; the null verdict applies
  to this correlated same-leaf estimator, not to variance-reduction schemes in
  general.
- **Tooling hardening (same change):**
  - `paired_analysis.py` is now strict and deterministic: pairing is by seed
    only, duplicate seeds or unequal seed sets are hard errors, bootstrap CIs
    use one fixed-seed NumPy generator per report (repeated analysis of the
    same inputs → identical intervals), and `--allow-partial` is an explicit
    diagnostic-only escape with a loud warning (never a promotion gate).
    Self-test `python3 paired_analysis.py --self-test`; registered as CTest
    `paired_analysis_selftest` (`CMakeLists.txt`).
  - `one_combat vnettest` is now an asserting parity check: it validates that
    the model and CSV open, that the header is exactly the canonical combat
    features followed by `pyPred`, rejects empty/malformed/short/extra-column
    rows, requires every feature and `pyPred` cell to be a complete finite
    numeric token (no trailing junk, no NaN/Inf — previously `std::stof`/
    `std::stod` accepted trailing junk and a NaN `pyPred` silently compared as
    in-tolerance), rejects a feature whose value overflows the native float
    feature vector (finite doubles beyond float range become Inf on
    conversion), rejects a non-finite native prediction or prediction
    difference (a malformed model can predict Inf/NaN; `std::max` ignores NaN
    so the row previously compared as in-tolerance and printed PASS), rejects
    a non-finite or negative tolerance argument, takes
    an absolute tolerance (default 0.001), and returns nonzero when
    max|diff| exceeds it. Regression coverage:
    `vnettest_selftest.py --self-test` (CTest `vnettest_selftest`,
    `CMakeLists.txt`) asserts a non-finite native prediction (MLP whose finite
    tokens overflow float in the hidden layer), a float-overflow feature, and
    out-of-tolerance evidence all exit nonzero while clean finite parity
    evidence exits 0.
  - `bestbench` mode staleness guard (issue 46 producer side): the first
    verification round's strict analysis rejected the gate CSV because
    `bestbench` had appended the same 256-row block twice (append-without-dedup
    trap). The `bestbench` mode handler in `apps/one_combat.cpp::main` now
    exits nonzero with a clear message when the results file already contains
    any requested seed, instead of silently doubling rows; disjoint batch
    appends (self-play gates) are unaffected, and the stale CSV was deleted so
    the verification gate regenerates it cleanly.
  - `train_value_combat.py` gained an opt-in target selector:
    `VCOMBAT_TARGET=endhp|utility_r` (default `endhp` — unset behavior trains
    the identical end-HP objective as before) and `VCOMBAT_WIN_BONUS`
    (default 50); `utility_r` labels R = 0 on a loss (even an abandoned fight
    with positive current HP) and win_bonus+endHp on a win. Rows, fight-group
    split, critical-state weights, feature filtering, XGBoost parameters,
    early stopping, and device selection are identical between targets; the
    trainer now reports val RMSE/MAE against BOTH endHp and utility R and
    writes a sidecar `<model>_metrics.json` (target semantics, win bonus,
    row/fight counts, split seed, features, params, best iteration, metrics).
- **Faithful target-only ablation (the corrected §132 test):** two fresh
  models trained on the same 287,517-row / 16,337-fight
  `build/vcombat_honest.csv` artifact with the identical canonical recipe,
  differing ONLY in the label, same device (CUDA) and package environment:
  | model | target | trees exported | val RMSE vs endHp | val MAE vs endHp | val RMSE vs R | val MAE vs R | best_iter |
  |---|---|---|---:|---:|---:|---:|---:|
  | `build/v_combat_control_endhp.txt` | endHp | 1500 | 7.88 | 5.58 | 48.59 | 45.82 | 1479 |
  | `build/v_combat_utility_direct.txt` | utility R | 611 | 45.87 | 43.58 | 15.35 | 9.73 | 570 |
  The control is the same-recipe end-HP arm (val RMSE 7.88 vs the recorded
  7.99 for the deployed §126 model — the small delta is consistent with
  CUDA-vs-GCP-device tree differences; sha256 of the deployed
  `v_combat_honest.txt` is `e69d64cf…`). The utility-R model fits R (MAE 9.73
  vs the quantile-R's 10.10 on the same rows — the two are comparable now,
  same recipe family, no 50·P(win) scale gap). Offline metrics are
  diagnostics only — the dataset is on-policy trajectory states, so
  regression error does not establish MCTS action-ranking quality.
- **Native parity:** `export_combat_model.py` (standard `nfeat` single-ensemble
  format; quantile aggregation is NOT part of this ablation) →
  `build/v_combat_utility_direct.txt` (sha256 `a81404b5…`),
  `build/v_combat_control_endhp.txt` (sha256 `9c1b6061…`); asserting
  `one_combat vnettest` PASSES for both (max|diff| 1.2e-4 / 1.6e-4 vs tol
  0.001, 200 val rows each). Both arms were trained/exported/parity-checked in
  the same local CUDA environment and package set; the fresh end-HP control
  retrain is deterministic (same `best_iter` 1479, same val RMSE 7.88, same
  exported-tree sha256 `9c1b6061…` as the first run), and the sidecars
  (`v_combat_control_endhp_metrics.json` vs
  `v_combat_utility_direct_metrics.json`) confirm identical rows (287,517),
  fights (16,337), split (GroupShuffleSplit test_size 0.15 random_state 0),
  feature list, XGBoost params (depth 8, eta 0.05, subsample 0.8,
  colsample 0.7, min_child_weight 20, max_bin 256), 1500 boost rounds, early
  stopping 40, and device (cuda) — the label is the only recipe difference.
- **Gate (pre-registered α0.1 first, because R is on the larger terminal
  scale):** 256 paired seeds, block 126700–126955 (exactly the §126 control's
  seeds), full V4 gate stack, `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0
  STS_S3_CHAIN=0 STS_S3_PARTICLES=64`, vnet =
  `STS_VNET=build/v_combat_utility_direct.txt STS_VNET_ALPHA=0.1`, asc 0,
  1000 sims, native OOC ON. Startup banner printed `[V_combat leaf value ON:
  build/v_combat_utility_direct.txt, 611 trees, alpha 0.1]` (candidate
  observed loaded and used). Strict paired analysis
  (`python3 paired_analysis.py build/vnet_all_a03_1k.csv
  build/v_combat_utility_direct_a01_256.csv deployed utility-direct-a01`):
  | metric | deployed (§126 control) | utility-direct α0.1 | Δ (95% CI) |
  |---|---|---:|---:|
  | win% | 50.4% | **38.3%** | **−12.1pp [−18.8, −5.1]** |
  | avg floor | 44.1 | 41.1 | −3.0 [−4.5, −1.4] |
  | avg HP end | 29.4 | 24.3 | −5.0 |
  Discordant 83/256 (32%), deployed-only 57 vs candidate-only 26. Local
  cpu_sec/run 17.5 (12 threads, 379 s wall); cpu figures are machine-dependent
  and the independent verification re-run provides the authoritative cpu
  comparison.
- **Verdict: ❌ line closed — the direct utility-R GBM is SIGNIFICANTLY
  NEGATIVE at its pre-registered first operating point α0.1 (95% CI excludes
  zero below).** Per the pre-registered rule, α0.3 is NOT tested and the
  deployed `build/v_combat_honest.txt` STAYS. The §132 hypothesis
  (same-model-class target change transfers online) is therefore falsified
  even when the recipe is held fixed and the label is fit directly — the
  fourth consecutive offline≠online falsification (§124c, §127, §133
  quantile, now §134). Combined with §133's α curve (heavier blending worse),
  the evidence says the deployed endHp leaf's ranking behavior is not
  reproduced by a correctly scaled R-expectation leaf at any tested blend.
  No promotion; no alpha-0.3 test; no disjoint-block confirmation run (only
  required if the first gate had been non-negative).
- **Recording notes:** the §133 revalidation under the strict analyzer
  reproduces the recorded point estimates exactly on all three recorded α
  values, each on the exact 256-seed block 126700–126955 (identical seed sets
  on both sides, no duplicates): quantile α0.3 50.4% vs 37.5% (−12.9pp),
  α0.5 50.4% vs 40.2% (−10.2pp), α0.7 50.4% vs 32.0% (−18.4pp). CI bounds
  differ slightly from the originally recorded unseeded bootstrap (e.g. α0.3
  upper bound −6.2 → −5.9, α0.7 upper bound −11.3 → −10.9) because the
  bootstrap is now deterministic. The B1 'beam' idea in
  `docs/archive/research/plans/plan-rollout-experiments-2026-08-07.md` was NOT
  implemented: as written it simultaneously requires beam pruning and forbids
  scoring partial beam states, which is not a complete algorithm; it needs a
  revised spec before any implementation.
- **Artifacts (ignored build outputs, not promoted):**
  `build/v_combat_utility_direct.{json,txt,val.csv,_metrics.json}`,
  `build/v_combat_control_endhp.{json,txt,val.csv,_metrics.json}`,
  train logs `/tmp/opencode/train_utility_direct.log`,
  `/tmp/opencode/train_control_endhp.log`, local gate CSV
  `/tmp/opencode/utility_direct_a01_256_local.csv`; the verification-run gate
  CSV `build/v_combat_utility_direct_a01_256.csv` is produced by the
  orchestrator's independent run. Code: `train_value_combat.py`
  (VCOMBAT_TARGET/VCOMBAT_WIN_BONUS), `export_combat_model.py`,
  `apps/one_combat.cpp::main` (vnettest), `paired_analysis.py`. Decision log:
  `2026-08-07-experiment-132-133-audit.md`.

## §135 Leaf-state diagnostic infrastructure: measure the §126-vs-§134 gap on actual Searcher3 leaf states (2026-08-08, local — infrastructure only, no gameplay result)

- **What:** the handover cycle's diagnostics for "why does the deployed end-HP
  vnet beat the direct utility-R vnet online (§126 +12.1pp vs §134 −12.1pp)
  despite fitting its target worse offline (val MAE 9.73 vs 45.82)". This
  entry records the TOOLING, not a verdict — the task explicitly forbids a new
  model before the diagnostics exist. The measurement cycle runs next; its
  results will be appended here.
- **Implemented:**
  - `search::g_onS3LeafQuery` / `S3LeafDiagnostic` (thread_local, nullptr by
    default) fire at the Searcher3 leaf-expansion blend site in
    `BattleScumSearcher3::step` — the states the learned leaf actually scores.
    The leaf identity is the leaf state's own `visibleHash` (computed inside
    the hook guard; `cur->obsHash` would be the PARENT's, which predates the
    committed action). Defaults byte-identical when unset.
  - `one_combat leafdiag NSEEDS SIMS ASC OUTFILE [SEEDOFFSET]`: per-stratum
    reservoir (10 strata: 3 HP bands × 3 difficulties + 1 deep-tree;
    `STS_LEAFDIAG_PER_STRATUM` default 50/seed, `STS_LEAFDIAG_DEEP_DEPTH`
    default 20) of leaf states with canonical combat features + deployed
    end-HP prediction + `STS_DIAG_VNET2` secondary prediction (never read by
    the search) + raw/blended rollout evals + provenance + per-fight labels.
    Sampling deterministic per seed (row SET reproducible; row order follows
    seed completion order like fairGen).
  - `one_combat leafref INFILE OUTFILE HIGH_BUDGET_SIMS NSEEDSREF ASC
    [REPLAY_SIMS]`: deterministic replay of the recorded decisions; the
    regenerated leaves match the recorded ones by obsHash (smoke: 450/450);
    each recorded leaf gets a FRESH high-budget Searcher3 root mean evaluation
    with per-group CRN reseeding (rng+belief+particles from one group seed).
    Reference value = `root.evaluationSum/simulationCount` — documented as an
    approximation (`referenceValue`), never ground truth. The per-group CRN
    reseeding gives PARTIALLY shared determinization draws only (the
    belief/particle shuffle prefix consumes a state-dependent number of RNG
    draws, so the streams diverge after the prefix). The reference search runs
    with the same learned-leaf environment as the leafdiag run (deployed
    `STS_VNET` @ configured alpha), so the reference is NOT model-free — run
    the sensitivity checks (rank vs `rawRolloutEval`, or a leafref run with
    `STS_VNET` pointed at a missing path) before drawing the central verdict.
    Replay config (particles, `STS_VNET`+alpha, OOC env arms, ascension) must
    match the leafdiag run; a mismatch shows as a re-capture WARNING.
  - `one_combat rollouttrace INFILE OUTFILE NSEEDSREF ASC [REPLAY_SIMS]`:
    actual search-policy rollout state sequences per recorded leaf
    (`search::g_onRolloutStep` fires inside `playoutRandom` after every
    executed action); same config-match requirement as leafref.
  - leafdiag CSV provenance carries the encounter as its UPPER_CASE enum NAME
    (`encounterName` column); numeric `encounter`/`turn` encodings live in the
    canonical feature block only (no duplicate columns). The 10 capture strata
    have no dedicated disagreement/close-decision stratum (raw |endHp − utilityR|
    is dominated by the +50-on-win scale offset); disagreement is stratified
    post-hoc in `tools/leaf_ranking.py`.
  - Analysis: `tools/leaf_ranking.py` (within-group pairwise ranking
    accuracy / top-1 / regret / MAE-RMSE-Pearson-Spearman / stratified,
    deterministic bootstrap CIs, `--self-test` works under `python3 -I`),
    `tools/leaf_distribution_shift.py` (per-feature KS + held-out logistic
    classifier combatgen-vs-search-leaf, ROC-AUC, `--write-ood`),
    `tools/leaf_split_check.py` (fight-level vs seed-level validation split
    for both targets, §134 recipe), `tools/leaf_smoothness.py` (delta-V
    smoothness/shaping per model).
- **Local smoke validation (not evidence of any gameplay effect):**
