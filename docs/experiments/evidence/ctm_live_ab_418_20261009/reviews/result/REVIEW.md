# Independent review: #418 live CTM A/B combined result (2026-10-09)

**Verdict: PASS.** The claimed result `NO_DIFFERENCE_DETECTED` + `NONINFERIOR_AT_10PP` reproduces exactly and follows
PREREG.md. One correction is required to the D9 note: the trace damage is larger than "7 lines" (see finding 2). It
cannot change the verdict, the flags or any primary/boss-death number.

Reviewed: branch `claude/new-ctm-stack-8h7edy` at `a159119d` (PREREG.md `3e62bef7…`, live_ab_analyze.py `510ccf0d…`,
cloud_worker.sh, DEVIATIONS D1–D8); raw units in `/mnt/project-files/ctm-pathb/live-ab-cloud/w01..w04/run`;
combined output `combined/report.json` (`9486c582…`), `report.summary.json`, `D9-TORN-TRACE-LINES.md`.
All work on local copies; no shared file was modified. Python 3.13.16, numpy 2.5.3 (same as the workers).

## 1. Reproduction

* Copied the 336 unit files (48 units × csv/meta/log/trace/done + 32 × mcts.csv/support/actions) from w01..w04.
  Each worker's `DONE.txt` sha256 list (84 files each) verifies against the current files, so nothing changed after
  the workers finished; the torn lines were present at DONE time.
* Frozen analyzer extracted from `a159119d` (sha256 `510ccf0d…`) on the untouched originals: crashes with
  `JSONDecodeError` in the trace loader, as D9 says.
* My own D9 handling (drop every non-blank JSONL line that fails `json.loads`, nothing else): exactly 7 of 95,486
  lines dropped, the same 7 files/lengths D9 lists. Unchanged analyzer on that copy gives a `report.json` identical to
  the combined one in every field except `runDir`; `report.summary.json` is byte-identical.

## 2. D9: acceptable, but the note understates the loss

The torn lines are not isolated fragments. Each trace record is written by open(append)/write/close
(`apps/one_combat/run_driver.cpp:102`), and on the network share some appends landed at a stale offset and
overwrote earlier records. A per-seed contiguity audit (`trace_gap_audit.py`, here) of `fight` and `idx` numbers
finds whole records silently lost:

| Unit (arm) | Seed | Lost battle rows | Lost ooc rows | CSV outcome |
|---|---|---|---|---|
| off-63000064 | 63000066 | fights 23, 27–31 (incl. act-2 boss) | idx 121 | won |
| off-63000112 | 63000115 | fights 10, 14–23 (incl. act-1 and act-2 boss) | idx 58 | won |
| off-63000120 | 63000126 | last fight (act-3 boss; only the torn tail remains) | – | won |
| prod-63000072 | 63000073 | fight 27 (non-boss) | idx 128 | won |

No `cand` trace and no other seed is affected; seed 63000127's Guardian row is out of order but present.
The `actions.jsonl` tear (cand-63000088) is in a file the analyzer never reads.

**Why it cannot change the verdict.**
* Primary metric, pairing, McNemar and the stall sensitivity read only the CSVs. All 48 CSVs parse, have 8 unique
  in-unit seeds in order, and agree with each unit's own `BEST win%= … avg_floor= …` log line (0/48 mismatches).
* All four affected seeds are wins with `fightsLost=0`; for all 384 runs the trace's lost-fight count equals the
  CSV `fightsLost`. So no death row was lost, boss deaths per arm (cand 19, prod 26, off 18) are exact, and
  `BOSS_DEATH_EXCESS` (cand−prod boss-death CI) is unaffected. `bossDeathCrossCheck` is 0/0/0.
* Trace integrity checks still hold: every completed seed has battle rows; a lost record can only remove, not
  create, a "won seed with a lost fight" error, and the CSV rules that out independently.

**What it does change (descriptive only).** `off` `bossesEnteredByAct` reads 127/124/118 where the CSV implies
128/126/119; `off` mean start HP and Smoke counts miss those rows; `prod` seed 63000073 misses one non-boss fight in
its mean start HP. The cand−prod boss-entry HP pairing is unaffected (the prod loss is not a boss row).

**Required correction:** D9's "may miss at most these records" is wrong; record the table above in D9 / the ledger.
**Recommendation (future runs):** write traces to local disk and copy them to the share at unit end.

## 3. Verdict and labels vs PREREG §5

| Rule | Value | Result |
|---|---|---|
| Integrity errors | none | not INVALID |
| CANDIDATE_BETTER: CI lower > 0 and p < 0.05 | lower −2.34 pp, p 0.2295 | no |
| CANDIDATE_WORSE: CI upper < 0 and p < 0.05 | upper +13.28 pp | no |
| → `NO_DIFFERENCE_DETECTED` | | yes |
| `NONINFERIOR_AT_10PP`: CI lower > −10 pp | −2.34 pp | set |
| `BOSS_DEATH_EXCESS`: boss-death CI lower > 0 | [−12.5, +1.6] pp | not set |
| `_PROVISIONAL`: > 6 dropped pairs | 0 dropped | not set |

Independent recomputation from the CSVs: wins cand 103, prod 96, off 105 of 128; discordant cand/prod 16/9, exact
two-sided McNemar p 0.2295; cand/off 17/19 p 0.868; prod/off 14/23 p 0.188. Constants in the report equal PREREG
(10,000 reps, rng 418063, α 0.05, margin −0.10, max 6 drops). PREREG §3: NDD is not evidence of parity; the CI
half-width (~±8 pp) is as pre-registered.

## 4. Integrity

* Binary: all four `PREREG-FROZEN.txt` record `one_combat` sha256 `dddb09f0…` (= PREREG §6); freeze records
  identical across workers (lines 4+); run checkout HEAD `a159119d` on all four.
* Candidate: `FAST-final.native` `90806c25…`, `STD1-escape.native` `b9188de0…`, `candidate-v3.json` `d9d8377e…`
  (frozen records and share `SHA256SUMS.txt`). Production CTM `abb2a9ea…`/`e9a18951…` and the 5 OOC models match §6.
  Scripts arm_env/run_unit/launch/units.all match the pinned hashes.
* Logs: exactly one MCTS banner per MCTS unit with sims 2048, active_lizard 1, screengbm, cpuct 1.5, visits, early
  stop; prod banner names the production paths, cand names FAST-final/STD1-escape; `candidate_id=pathb-r2` in all 16
  cand logs and in no prod/off log; no banner in off logs. No `startup failure`, segfault, abort or
  `bestbench-seed-failure` line anywhere.
* Exit status: all 48 `.done` have rc=0; no RESTARTS/aborted units. w01 has one setup re-run (`RESUMES.txt`,
  15:05:31Z, before the smoke and any launch), harmless. Smoke passed (w01/SMOKE_PASS).
* Coverage: 128 rows per arm, seeds exactly 63000000..63000127, no stalls, missing, timeouts or drops; sidecars one
  record each and pass the analyzer's config checks (sims, A0, 1 thread, fair, native_silver, cap 32768, exact root,
  no learned stop/adaptive/root prior, keys off, executableGitSha 648334e3).

## 5. Observations (not blocking)

* `prod` won 75.0% versus §384's MCTS arm at 56%; `prod − off` is −7.0 pp [−16.4, +2.3] versus §384's −21.9 pp.
  `cand − off` is −1.6 pp [−10.9, +7.8]. Neither MCTS arm beats `off`; per PREREG only a `cand − off` CI lower > 0
  would justify an OOC-MCTS-on confirmation, so none is indicated.
* Some won runs end below floor 50 (e.g. 63000052, 63000090: floor 49; 63000099 cand: 43), presumably via an act-3
  shortcut. The trace boss rows are right; `BOSS_FLOORS` is only a death cross-check, so this has no effect here.
* Promotion under NDD is Philipp's decision (PREREG §5): `NONINFERIOR_AT_10PP` holds and `BOSS_DEATH_EXCESS` does not.
