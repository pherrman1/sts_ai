# Pre-run review: #418 live CTM A/B pre-registration (2026-10-09)

Reviewed: commit 5ff7e557 (branch claude/new-ctm-stack-8h7edy),
`docs/experiments/evidence/ctm_live_ab_418_20261009/{PREREG.md, live_ab_analyze.py}`.
Share copies are byte-identical (PREREG 609a876b…, script 2d4e2ec3…). Code checked at origin/main 35de5b03
(source identical to 648334e3). No seeds run, nothing pushed.

## Verdict: NOT PASSED — one blocking issue, one required wording fix

### Blocking

**B1. A crashed or killed unit is silently dropped instead of INVALID.** The prereg says any non-stall seed failure
makes the verdict INVALID, but a process that dies mid-unit (segfault, abort, OOM kill) writes no
`[bestbench-seed-failure]` line. Its remaining seeds become `census.missing`, are dropped as pairs, and raise no
integrity error. The analyzer never reads `<tag>.done` (rc) or the log's `BEST`/`bestbench: FAILED` tail.
Reproduced with the script's own `_synth`: truncating `cand-63000016.csv` after 3 seeds gives
`NO_DIFFERENCE_DETECTED`, `integrityErrors: []`, 5 missing seeds (below the 6-pair PROVISIONAL limit).
A crash is arm-specific and informative (the candidate loads new artifacts and a new escape path), so it must not
be censored silently.
Fix (small, before 7.3): require `<tag>.done` per unit and parse `rc`; rc 0 is fine; rc 1 only when every failure
line in the log matches STALL_RX; rc 124 (timeout) lists the unit under `census.<arm>.timeouts` (keep the drop rule
if Philipp wants it, but make it visible); any other rc, or a missing seed in a unit whose rc is not 124, is an
integrity error. Add a selftest case for the truncated-CSV crash. Update the script sha256 in PREREG §5 and §7.2.

### Required wording fix

**W1. The power statement is optimistic.** Simulated exact McNemar (α 0.05, n 128, 4000 reps):
80% power needs Δ ≈ 13 pp at 25% discordance and ≈ 16 pp at 35%. §384's MCTS-vs-off had 41% discordance (12+40);
§384 flat10k-vs-learned had 31%. Two MCTS stacks whose OOC decisions diverge early may well be at 35-45%, which
needs ≈ 16-18 pp. CI half-width ≈ ±8.5-10.5 pp is right. Replace "±12-14 pp" with "about 13-18 pp, depending on
discordance". The "NO_DIFFERENCE_DETECTED is not parity" sentence is correct and should stay.

## Checked and fine

* **Arms.** `arm_env.sh` shared part equals §384 `arm_env.sh` base plus `flat10k`/`mcts` settings verbatim; prod/cand
  differ only by the five CTM variables under `env -i`. `STS_CTM_RESEARCH_CANDIDATE_MANIFEST*` is read only in
  `combat_transition_runtime.cpp:253-254`; the override variables only in `ooc_mcts_adapter.cpp:1687-1698`.
* **Lizard flag.** `activeLizardEnabled=automaticDefaultStack` (:1699) so the override arm must set
  `STS_OOC_MCTS_ACTIVE_LIZARD=1`; it does, and the banner (:1724-1744) prints `active_lizard_correction=`, which the
  analyzer requires as `=1` in both arms. The Lizard r model is inline in the manifest, so no extra file is needed.
* **Banner/log checks** match real output: §384 `mcts*.log` has exactly one banner per process with the same knobs;
  `configureLiveOocMcts` runs once (`one_combat.cpp:3160`); the candidate line is printed only for a research
  candidate. Startup failure exits before the CSV exists, so it is INVALID ("missing results CSV").
* **Seed guard.** `bestbench` seed index 3 in `tools/seed_guard.sh`; `one_combat bestbench 10000 N 0 LO CSV` puts N
  there. Every unit and the smoke go through it. Canary flags exist in `check_benchmark_canary.py`.
* **Sidecar checks.** Keys and value types match `BestBenchMeta.h:120-190`; the sidecar is written before the seed
  loop (`one_combat.cpp:~1330`), so a killed unit still has one record.
* **Stall regex** matches the two real messages (`NativeSilverBackend.cpp:407` via `fail()` → runtime_error;
  `SilverSearcher.cpp:389`); bestbench catches per seed (`one_combat.cpp:1361-1395`).
* **Traces.** `oocTraceState` emits `room` from `roomStrings` ("BOSS"), potions as `SMOKE_BOMB`; MCTS trace header
  contains every `MCTS_SUM` key plus `mctsCpuSec`. Boss floors 16/33/50 match §384 death floors (68 of 83 deaths).
* **Statistics.** Paired percentile bootstrap and exact two-sided McNemar are correct; verdict needs both to agree,
  which is conservative. Selftest passes (1.8 s). Determinism check included.
* **Seeds.** No 63M seed range in main, open branches, ledgers, KB or project share; only hash/float fragments.
* **Carry-forward notes** from the offline review: boss deaths per arm and per act, boss-entry HP and the
  `BOSS_DEATH_EXCESS` flag cover note 2; the hand-back tarball includes logs (note 3).

## Non-blocking notes

1. Stall drops are outcome-dependent (fights differ by arm). §384 had 0 failures in 384 runs, so expect few; add a
   descriptive sensitivity row counting a stalled seed as a loss for the stalling arm.
2. With CI half-width ≈ 9-10 pp, `NONINFERIOR_AT_10PP` effectively needs a point estimate ≥ about 0.
3. The decision traces are new relative to §384; code only reads state (`run_driver.cpp:404-434`), so `prod − off`
   still replicates §384 in kind.
4. `escapes` is a proxy (Smoke Bomb count drop in a won non-boss fight); it stays descriptive, as written.

## Delta re-review of 3b5d77c2 (parent 5ff7e557): PASSED

* B1 fixed: each unit's `.done` rc decides (missing `.done`, rc 0 with failures/missing rows, rc 1 with a non-stall
  failure or a missing row, any rc other than 0/1/124 → INVALID; rc 124 listed under `census.<arm>.timeouts`).
  bestbench returns 1 on per-seed failures (`one_combat.cpp:4071`), so rc 1 = stalls only is the right rule.
  Selftests cover rc 139/1/0/124 on the truncated unit and a missing `.done`; `selftest OK`.
* W1 fixed: power now "about 13-18 pp, depending on discordance".
* Stall-as-loss sensitivity row added (descriptive only).
* Hashes: file 510ccf0d…8d3c = §5 = §7.2 expect line = the heredoc pasted in §7.2 = share copy; PREREG 3e62bef7…e081
  = share copy.
