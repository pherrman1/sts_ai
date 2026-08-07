# Session continuation plan — adaptive-combat-search (searchdiag Phase 0 + STS_CONV_ROOT Phase 1)

Date: 2026-08-06. Status: **COMPLETE (T1–T6 executed 2026-08-06; §118–§120)** —
Phase 0 (rollout-cause split + timing) and Phase 1 (root-stability adaptive
search) were implemented, built, and locally measured on 64 fair seeds @1k
(encouraging but provisional). The continuation session ran T1 (smoke), T2
(128-seed local paired run), T3 (256-seed GCP gate on sts-test), T4
(EXPERIMENTS.md §118), T5 (defaults decision), and T6 (Phase 2
context-adaptive rollout caps: flat @3k baseline measured for the first
time, caps implemented as `STS_ROLLOUT_CAPS`, measured before/after, and
gated at 256 paired seeds — falsified, §119). **Phase 5 (forced-action
contraction, `STS_FORCED_MOVE`) was then executed, gated twice, and
PROMOTED to built-in default ON (fair path only) — the one positive result
of the program (§120/§121):** exact per-seed outcome equality on two
independent 256-seed fair gates (0/256 diffs each) at −16 to −18% cpu.
The known-RNG confirmation run found a real non-fair hang (stale winning
line after a forced skip → infinite `stepThroughSolution` loop) and non-fair
divergence (persistent tree reuse + shared RNG), so the standalone flag is
fair-only by design; the non-fair path stays byte-identical and the hang is
fixed. Both adaptive-budget arms were FALSIFIED at their paired
gates: STS_CONV_ROOT (Phase 1) flat 22.3% vs 19.9% (−2.3pp, 95% CI −2.3 ±
4.1pp) at −11% cpu; STS_ROLLOUT_CAPS (Phase 2) flat 22.3% vs 16.4% (−5.9pp,
95% CI −5.9 ± 4.5pp, excludes zero) at −7.8% cpu. The 64-seed Phase-1 win
signal did not survive 128 or 256 seeds; Phase 2's rollout cut loses more
decision quality than the saved sims gain. The falsified lines are stopped,
their env gates stay default-off; the remaining parked phase (3) is not
started. Historical record below; current instruction lives in
`EXPERIMENTS.md` §118–§120 and
`docs/knowledge-base/architecture/combat-search.md`.

## 0. Session summary (what is already done)

- **Phase 0 — rollout-cause split + timing (shipped in the current diff):**
  `SearchDiagnostics` now splits rollout calls into `rolloutLeafCalls`
  (newly expanded leaf) and `fairIllegalStoredEdge` (stored edge invalid in
  the current determinization) and carries `simSeconds` (chrono around the
  sim loops in `search`/`searchToTotal`/`searchToTotalAdaptive`).
  `searchdiag` CSV gains columns `rolloutLeafCalls`, `fairIllegalStoredEdge`,
  `simSeconds`, `simsPerSec`; invariant `rolloutCalls == rolloutLeafCalls +
  fairIllegalStoredEdge` is asserted in `sdiagMetricsOf`
  (`apps/one_combat.cpp`) and validated by the smoke checks.
- **Phase 1 — root-stability adaptive search (shipped in the current
  diff):** `BattleScumSearcher2::searchToTotalRootStable(target, minSims,
  patience)` — chunked search (start `g_convRootStart`=250, grow
  `g_convRootGrow`=2.0), stability check every `g_convRootCheck`=100 sims on
  (most-visited root action, visit share within `g_convRootShare`=0.05,
  windowed root mean value within `g_convRootValue`=1.0), stop after
  `patience` stable sims past `minSims`. Env gate `STS_CONV_ROOT=1` plus
  `STS_CONV_ROOT_{START,GROW,CHECK,SHARE,VALUE,MIN,PATIENCE,MAX_FRAC}`,
  parsed in `apps/one_combat.cpp::main` next to `STS_CONVERGE`.
- **Budget-neutral reinvestment pool (agent side):** in both
  `ScumSearchAgent2::playoutBattleFair` and `playoutBattle`, each decision
  credits its flat budget to a per-fight `fightPool`; the root-stable search
  may escalate up to `min(pool, g_convRootMaxFrac * flatTarget)` (default
  MAX_FRAC=3.0); sims used are deducted. Total sims per fight stay at or
  below the flat total. Plus the **forced-move shortcut**:
  `BattleScumSearcher2::onlyLegalAction` (canonical enumeration; fires only
  when exactly one legal action) commits directly without searching.
- **Key lesson already learned:** a naive "escalate to frac x target with no
  pool" arm cost 1.9x cpu (overdraw); the pool version is budget-neutral.

## 1. Interim results (provisional — 64 seeds @1k fair, local WSL, 8 threads,
   commit `4325c03` + this diff, asc 0, Searcher2 fair, native OOC, policy
   PUCT on, no combat value/PVNet; per-seed CSVs `build/conv_{flat,root,
   root500,root750,root500f1}_64.csv` — machine-local, not in git)

| Arm (all STS_CONV_ROOT=1 unless noted) | win% | wins/64 | floor | hp | cpu_sec/run |
| --- | --- | --- | --- | --- | --- |
| flat (env off) | 23.4 | 15 | 36.8 | 13.6 | 23.3 |
| MIN=250 PATIENCE=250 MAX_FRAC=3 | 17.2 | 11 | 36.2 | 11.3 | 19.0 (−19%) |
| **MIN=500 PATIENCE=500 MAX_FRAC=3** | **26.6** | **17** | **36.8** | **14.1** | **21.2 (−9%)** |
| MIN=750 PATIENCE=500 MAX_FRAC=3 | 23.4 | 15 | 36.7 | 13.1 | 21.2 (−9%) |
| MIN=500 PATIENCE=500 MAX_FRAC=1.0 (stop-only) | 20.3 | 13 | 35.8 | 13.8 | 17.4 (−25%) |

- Interpretation: stopping alone (frac 1.0) loses ~3pp; the pool-funded
  escalation recovers ~6pp and the 500/500 point nets **+3.1pp at −9% cpu**
  vs flat (all deltas within 64-seed noise, SE ≈ 7pp, but direction is
  consistent across arms). **Candidate operating point: `STS_CONV_ROOT=1`
  `STS_CONV_ROOT_MIN=500` `STS_CONV_ROOT_PATIENCE=500` (MAX_FRAC default
  3.0).** 500/500 flip counts vs flat: 54 same, 6 up, 4 down.
- Phase 0 finding (fair @3k, all rooms): **~half of fair rollouts are the
  illegal-stored-edge fallback**, not leaf rollouts (per decision: 3417 leaf
  vs 3577 illegal-stored; share of rollout calls grows 28%@100 → 68%@30k
  act 1). This confirms the fair-tree/determinization mismatch is real (not
  noise); see parked Phase 4. Timing works: ~165k sims/s per search.

## 2. Handoff state (working tree, uncommitted at session end)

- Modified: `apps/one_combat.cpp`, `include/sim/search/BattleScumSearcher2.h`,
  `src/sim/search/BattleScumSearcher2.cpp`,
  `src/sim/search/ScumSearchAgent2.cpp`, `EXPERIMENTS.md` (existing §117),
  `docs/knowledge-base/architecture/combat-search.md`.
- New (untracked): `docs/knowledge-base/decision-log/2026-08-06-searchdiag-rollout-usage.md`
  (searchdiag decisions + §117 addendum),
  `docs/knowledge-base/decision-log/2026-08-06-conv-root-stable-search.md`
  (this session's Phase 1 decisions), this plan file.
- `analysis_s2s.py` is a pre-existing untracked helper — leave it.
- Build artifacts and raw CSVs under `build/` are git-ignored and
  machine-local; the key numbers are quoted above. If per-seed rows are
  needed elsewhere, scp them explicitly (AGENTS.md convention).
- Searchdiag analysis scripts (`build/sdiag_group.py`, `build/sdiag_by_act.py`,
  `build/sdiag_by_encounter.py`) are machine-local; the split analysis was
  ad-hoc. Re-create `build/sdiag_split.py` from this plan's §5 if needed.

## 3. Environment quickstart

- Windows repo `C:\Users\pherrman\projects\sts_ai`; build in WSL Ubuntu:
  `wsl bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai && cmake --build build -j"`
- Long sweeps: GCP `sts-test` via the full-path gcloud.cmd (plink/IAP);
  exact workflow in `docs/knowledge-base/operations/build-and-debugging.md`.
  Plain ssh/WSL do not resolve it.
- Traps: `git diff --check` flags every added line (checkout-wide CRLF —
  pre-existing, not real whitespace). `ctest` `selfplay_syntax` fails on CRLF
  (`$'in\r'`) — pre-existing. Known-RNG Searcher2 bestbench aborts
  pre-existing at CARD_SELECT EXHAUST_MANY with empty hand (seeds 0–7@floor
  13, seed 12@floor 21); use `STS_FAIR=1` for benchmarks, or known-RNG seeds
  10,11,13,14,16,17,18,19 for diagnostics.

## 4. Next steps (T1..T6) — exact commands and decision rules

**T1 — smoke/regression on the new tree (cheap, do first).**
```bash
wsl bash -lc "cd /mnt/c/Users/pherrman/projects/sts_ai && cmake --build build -j"
STS_FAIR=1 ./build/one_combat searchdiag 1 500 0 build/sdiag_check.csv 2 0
```
Verify: header has `rolloutLeafCalls,fairIllegalStoredEdge,simSeconds,
simsPerSec`; per row `sims == terminalInTree+rolloutCalls+leafDirectEval`
and `rolloutCalls == rolloutLeafCalls+fairIllegalStoredEdge`; fractions in
[0,1]. Then `ctest --test-dir build --output-on-failure` (expect the known
CRLF `selfplay_syntax` failure only).

**T2 — 128-seed local paired confirmation of the candidate point.**
```bash
cd /mnt/c/Users/pherrman/projects/sts_ai
rm -f build/conv_flat_128.csv build/conv_root_128.csv   # a partial flat run was aborted; truncate first
STS_FAIR=1 ./build/one_combat bestbench 1000 128 0 0 build/conv_flat_128.csv
STS_FAIR=1 STS_CONV_ROOT=1 STS_CONV_ROOT_MIN=500 STS_CONV_ROOT_PATIENCE=500 \
  ./build/one_combat bestbench 1000 128 0 0 build/conv_root_128.csv
```
Compare win%, floor, hp, cpu; also flip counts (per-seed `won` diff). At
128 seeds the delta SE is ≈ 5pp. Decision rule: if win ≥ flat and cpu ≤
flat → proceed to T3; if win < flat by > 5pp → falsified, record §22-style
and stop the adaptive line; if within noise → proceed to T3 anyway (the
GCP 256-seed gate is the arbiter).

**T3 — GCP 256-seed paired gate (the arbiter).** Follow
`operations/build-and-debugging.md`: git pull on `sts-test`, build, run both
arms at the recommended S2-fair block (256 seeds @1k, 24 threads) with
results files, copy CSVs back. Decision rule (per current-baselines
conventions): promote to a recorded operating point only if win ≥ flat with
CI excluding a meaningful loss and cpu ≤ flat; else record as
neutral/falsified and stop. Optionally also @3k (the recommended operating
point) — the stop should fire more there (chunks 250→3000; obvious
decisions stop ~1000–1500; ambiguous escalate toward 3000+).

**T4 — write the §118 EXPERIMENTS.md entry** with full provenance (per the
recording rules: date, executable mode, env flags incl. all
STS_CONV_ROOT_*, model paths/hashes, budgets, ascension, seeds, thread
count, fair regime, searcher, artifact location, metric formula) and the
decision-log/combat-search.md updates. Update the baseline table only if
promoted.

**T5 — decide defaults.** If T3 confirms: change the built-in defaults of
`g_convRootMinSims`/`g_convRootPatience` to 500 (keeping the env-gated
`STS_CONV_ROOT=1` flag) OR keep env-only; recommend env-only until two
independent gates agree. If the known-RNG regime matters later, note the
non-fair pool wiring exists and is untested at scale.

**T6 — Phase 2 (context-adaptive rollout caps) — EXECUTED 2026-08-06, FALSIFIED (§119).**
The flat fair-@3k baseline was measured for the first time (`build/sdiag_fair3k_flat.csv`:
avgRolloutLen 8.76, MONSTER 7.1 / ELITE 9.0 / BOSS 12.4, act 7.6/9.5/9.3,
rollFrac 0.75, capped 0). Per-context caps implemented (`STS_ROLLOUT_CAPS=1`
+ `STS_ROLLOUT_CAPS_{BOSS,TURN0,ACT23,LATE_ALIVE}`; boss/turn-0/act-2-3 →
8, monsters alive ≤ 1 uncapped; leaf evaluation stays the heuristic —
combat VNet rejected §97; `rolloutCapForContext` in
`src/sim/search/BattleScumSearcher2.cpp`, env in `apps/one_combat.cpp::main`).
After-measurement (`build/sdiag_fair3k_caps.csv`): avgRolloutLen 7.15 (−18%),
27% of rollout calls capped (BOSS 38%, act2 33%, act3 38%). Paired 256-seed
gate @1k (24 threads): flat **22.3%** vs caps **16.4%** — delta **−5.9pp
(95% CI −5.9 ± 4.5pp, excludes zero)**, flips 13 up / 28 down, cpu −7.8%.
**Verdict: falsified — the heuristic capped-leaf estimate at depth 8 loses
more decision quality than the saved sims gain. Line stopped, env gate stays
default-off.** No resweep of the ±2-action range is warranted (verdict far
outside noise). Phase 2 is not revisited without a different leaf-estimation
strategy.

## 5. Parked phases (Phase 2 executed and falsified 2026-08-06, §119; Phase 5 executed 2026-08-06, §120 — promotion candidate; Phase 3 remains parked)

- **Phase 3 — policy-guided rollout** (`STS_ROLLOUT_POLICY=uniform|attack|
  eps|prior`): attack-bias already exists when capped; extend to uncapped;
  prior mode only with node-cached priors (§23 per-step cost warning).
  Note: the capped-rollout line just failed (§119) — Phase 3's premise
  (rollout composition matters for quality) is now weaker; re-justify before
  starting.
- **Phase 4 — fair-tree structural fix — EXECUTED 2026-08-06 (§122, decision
  log `2026-08-06-live-valid-phase4.md`).** Searcher3 was instrumented for
  the first time (illegal-stored share 58-60% at fair @3k — worse than S2's
  48%) and `STS_LIVE_VALID` (live-valid-biased edge re-selection, both
  searchers) was implemented and gated. S3 direction positive at both
  budgets (+3.5pp @1k, +5.5pp @3k with hp +4.1, CI barely excludes zero)
  but every arm costs cpu (+5.6 to +15.1%) — **promotion candidate, not
  promoted**; default stays off. Next: a second independent S3 @3k gate to
  firm the CI plus an explicit cpu-trade policy call.
- **Phase 5 — forced-action contraction/dominance — EXECUTED and PROMOTED
  2026-08-06 (§120/§121, decision log `2026-08-06-forced-move-phase5.md`).**
  Strictly-forced-only `STS_FORCED_MOVE` is **default ON in the fair path**:
  two independent 256-seed fair gates show exact outcome equality (0/256
  diffs each) at −16 to −18% cpu; `STS_FORCED_MOVE=0` disables. Non-fair
  path is a no-op by design (persistent tree reuse diverges; §121), and the
  forced-skip hang found there is fixed (stale winning-line bookkeeping).

## 6. Exit criteria for this program

Confirmed (256-seed gate) win ≥ flat at ≤ flat cpu for the adaptive arm, or
a falsification recorded with the evidence chain (§22/§102 style), plus:
EXPERIMENTS.md §118 with full provenance, decision log entries, and
combat-search.md current. Every policy-affecting arm gets its own paired
gate; never mix fair and known-RNG rows.
