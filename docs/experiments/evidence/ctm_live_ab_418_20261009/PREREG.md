# #418 CTM retrain: pre-registered live 128-pair A/B (production CTM vs pathb-r2 inside live OOC MCTS)

Written 2026-10-09, before any cohort seed ran, from a read-only pass over `origin/main` `35de5b03` (branch
`claude/new-ctm-stack-8h7edy` at `72ebd7d1` adds only the offline runbook). `git diff 648334e3 35de5b03 -- apps src
include CMakeLists.txt models selfplay/models tools/seed_guard.sh third_party` is empty, so every citation below also
holds for the offline A/B binary (`$OC`, built at `648334e3`, sha256 `dddb09f0…`). This is the last step of
FULL-RETRAIN-PLAN.md item 10, after the offline A/B (PASS) and its independent review (PASSED, 2026-10-09).

**Venue: Philipp's machine (local), 10 workers, about 1.5 h wall in total.** Every command, script and constant needed
there is in this file (section 7); that machine cannot read `/mnt/project-files`.

## 1. How the CTM is used in live play (code facts)

* The CTM is used live **only by OOC MCTS**. `run_driver.cpp:453-462`: each out-of-combat step goes chest rule → relic
  rule → match-and-keep → `oocMctsPolicyStep` → the ordinary policy chain. `oocMctsPolicyStep`
  (`ooc_mcts_adapter.cpp:1928-1942`) returns false unless `STS_OOC_MCTS=1`. When on, it searches with the live sampler
  `liveSampler`; match-and-keep also delegates to it (`run_driver.cpp:224-227`). OOC MCTS owns every OOC screen it
  supports: card rewards, events, shops, campfires, boss relics and the map/path. Real combat is always native Silver
  and never reads the CTM.
* **OOC MCTS is off by default.** §384 (`ooc_mcts_vs_off_pilot_20261006`) found it −21.9 pp [−32.0, −11.7] versus
  MCTS off on 128 pairs, and kept it off. It named "a refreshed CTM (#418) followed by a repeat of this pilot" as a
  next step. So this A/B compares two OOC MCTS stacks, and a reference arm (MCTS off) is needed to say whether either
  of them is worth turning on.
* **Preconditions** (`run_driver.cpp:360-363`, `ooc_mcts_adapter.cpp:1576-1601`): live OOC MCTS needs ordinary flat
  exact-10k Silver (`STS_SILVER_EXACT_ROOT_BUDGETS=1`, no learned stop, no adaptive), reuse cap 32768, the native V4
  policy (`STS_OOC_STRATEGIC_TOK_NN`) and native `v_win`.
* **CTM selection** (`ooc_mcts_adapter.cpp:1687-1720`):
  * Production: `STS_OOC_MCTS_COMBAT_MODEL` unset. That is the automatic default stack: fast
    `selfplay/models/combat_transition_deepsets_lizard_t2.native` (abb2a9ea), Brew fallback
    `…near_full_except_smoke_v2.native` (e9a18951), active-Lizard correction on.
  * Override: `STS_OOC_MCTS_COMBAT_MODEL` and `STS_OOC_MCTS_BREW_FALLBACK_MODEL`. **With an override the active-Lizard
    correction defaults to off** (`activeLizardEnabled=automaticDefaultStack`, :1699). The candidate arm must set
    `STS_OOC_MCTS_ACTIVE_LIZARD=1`, as ctmscorerows did with `LIZARD=1`.
* **Research-candidate mode works in the live driver.** The live sampler is the same
  `EntropicBrewFallbackCombatTransitionSampler` that `ctmscorerows` uses. Each `CombatTransitionRuntime` reads
  `STS_CTM_RESEARCH_CANDIDATE_MANIFEST` + `_SHA256` (`combat_transition_runtime.cpp:252-258`). It accepts stamped
  artifacts only when their bytes and capabilities are in the manifest (:351-369). The pair checks (:936-966) pin
  STD1E through the manifest, require `FINAL_SUPPORT_EXPOSURE_DEVELOPMENT_PASS` and agreement on escape, and require
  the fast header's Lizard correction. With a candidate loaded the driver prints
  `[ctm-research-candidate] candidate_id=pathb-r2` (:1719-1722). Production prints no such line. All refusals throw
  at startup: `[live OOC MCTS startup failure]`, exit 1 (`one_combat.cpp:3160-3163`).
* **Escape changes the OOC MCTS Smoke masking.** `OocGameContextModel` wraps the sampler in `maskInitialSmokeBomb`
  (`ooc_mcts_adapter.cpp:337-341, 431`). For a sampler that does not model the escape (production), every imagined
  combat that starts with a held Smoke Bomb is valued as if the slot were empty, and the bomb is handed back unused
  (`InitialSmokeBombMaskingSampler`, :262-336). An escape-capable sampler (`modelsSmokeBombEscape()` = the fast
  child's escape capability, `combat_transition_runtime.h:175`) passes through unmasked. It can then sample ESCAPE,
  which `applySampledCombatExit` applies (:343-351): no rewards and, on bosses, no escape.
  * **Inference:** the live difference between the arms is (a) imagined escapes in non-boss fights with a held Smoke
    Bomb, (b) the Path B teacher's predictions (about 12 HP lower at bosses, review note 1), (c) the wider HP domain
    (maxHP to 220: fewer unsupported combats), and (d) the refit fast Lizard r.
  * Whether Silver uses a Smoke Bomb in a real fight does not depend on the arm.
* **The live harness** is §384's (`docs/experiments/evidence/ooc_mcts_vs_off_pilot_20261006/`, run as
  `ooc-mcts-pilot-417`): `bestbench 10000 N 0 LO CSV`, one thread per process, the §377 live profile, act-3 stop,
  OOC MCTS knobs from §383, all through `tools/seed_guard.sh`. This A/B reuses its environment and its `mcts` arm
  verbatim. It adds the CTM variables, clean `env -i` environments, two read-only traces and 8-seed units.
* **Read-only traces** (added to every arm; they do not change play):
  * `STS_OOC_DECISION_TRACE` (`run_driver.cpp:30-33, 404-434`): one JSON line per battle with pre/post HP, maxHP,
    room and potions. It gives boss deaths, HP at fight starts, and Smoke Bomb holding and escapes.
  * `STS_OOC_MCTS_TRACE` (MCTS arms only, `ooc_mcts_adapter.cpp:2116-2212`): per-seed owned/fallback decisions,
    unsupported combats, support aborts and Brew fallback, plus `<trace>.support.jsonl` with support reasons.
* **Per-seed failures.** `bestbench` catches an exception per seed, writes no row, and prints
  `[bestbench-seed-failure] seed=S error=…`. It then exits nonzero after finishing the other seeds
  (`one_combat.cpp:1361-1395`). The Path B "Silver stall" (`native Silver backend: stall: exceeded 1000 decisions`,
  `SilverSearcher::step descent exceeded depth bound`) therefore drops one seed, not the unit. Unlike in
  `combattransitiongen`, no worker dies.

## 2. Hypothesis and arms

**Question.** Inside live OOC MCTS, does the pathb-r2 CTM (escape capability only) win more runs than the production
CTM stack?

**Hypothesis (H1).** The candidate's teacher-aligned predictions and its escape modelling improve OOC MCTS decisions.
§384 attributed MCTS's losses to over-trusting imagined combats on the way to bosses, so the candidate should win more
runs, mostly through fewer boss deaths. **Counter-hypothesis (review note 2).** The candidate is slightly more
optimistic about survival (+0.002 overall, +0.013 on bosses). That could make MCTS greedier and cause more boss
deaths.

| Arm | Environment (on top of the shared profile, section 7.2) | Role |
|---|---|---|
| `prod` | §384 `mcts` arm verbatim: `STS_OOC_MCTS=1`, 2048 sims, cpuct 1.5, visits root selection, early stop, V4 prior and leaf policy, widening 2/0.5, depth 32, default `screengbm` leaf; CTM variables **unset** (automatic production stack) | baseline |
| `cand` | `prod` + `STS_OOC_MCTS_COMBAT_MODEL=$FASTF`, `STS_OOC_MCTS_BREW_FALLBACK_MODEL=$STD1E`, `STS_OOC_MCTS_ACTIVE_LIZARD=1`, `STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$M`, `STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=d9d8377e…` | **treatment** (differs from `prod` only in the CTM environment) |
| `off` | §384 `flat10k` arm: identical Silver, `STS_OOC_MCTS=0` | descriptive reference (is either MCTS stack worth turning on?) |

Same binary, same checkout, same seeds, one thread per process. Per-seed results do not depend on order or
concurrency (§384 plan; fair Silver is deterministic per seed). Writhing Mass + Ritual Dagger stays excluded, and
Fairy/Brew active-Tail states keep production's boundary behaviour, as offline.

## 3. Seeds and sample size

* Cohort: **`63000000..63000127`** (128 paired seeds), Ironclad A0. The highest ranges in use are `61001000..61001127`
  (§406) and `62000000..62100255` (§408 v1/v2, project share). The ledgers, KB, open branches and project share have
  no 63M seed range: the only matches are hash fragments (`potion_decoder_v1` line 70, an offline-A/B JSON).
* Smoke: `63009000` (one seed per arm, not pooled).
* Units: 16 blocks of 8 seeds × 3 arms = 48 `bestbench` invocations, each through `tools/seed_guard.sh`.
* Power (**Inference**, simulated exact McNemar at α 0.05, n = 128; pre-run review W1). §384's MCTS arm won 56%.
  The discordance between the two CTM stacks is unknown (§384 MCTS vs off: 41%; flat10k vs learned: 31%). 80% power
  needs a difference of about 13 pp at 25% discordant pairs and about 16 pp at 35%: **about 13–18 pp, depending on
  discordance**. The 95% CI half-width is about ±8–10 pp. **NO_DIFFERENCE_DETECTED is not evidence of parity.**

## 4. Venue and cost

Per-run CPU from §384 (cloud, 4 runs in parallel, one thread each): `mcts` 114.1 s, `flat10k` 57.6 s. **Inference:**
the candidate costs about the same as production (±20%). Escapes end imagined fights early, but the candidate
supports more combats and so aborts fewer searches.

| Item | CPU |
|---|---|
| `prod` 128 × 114 s | 4.06 h |
| `cand` 128 × ~114 s | ~4.06 h |
| `off` 128 × 58 s | 2.05 h |
| smoke (3 arms, 1 seed) | ~5 min |
| **total** | **~10.2 CPU-h** (8.1 without `off`) |

| Option | Setup | Wall time |
|---|---|---|
| **A. Philipp's machine, 10 workers (recommended)** | Nothing to build or upload. Reuses `$OC` (`dddb09f0…`, the offline A/B binary) and the candidate files in `$R2/durable`. | smoke ~5 min + cohort ~65–80 min (10.2 h / 10 plus the last unit's tail of ≤ 20 min); **~1.5 h** including preflight; ~1.1 h without `off` |
| B. One cloud container (4 CPU, 15 GB) | Philipp uploads the 3 candidate files (~4 MB) to the project share; one ~25 min Release build (serial LTO link) | ~2.6 h run + 0.5 h build ≈ **3.2 h** |
| C. Four cloud containers | as B, plus one shared binary (`/mnt/project-files` is noexec: copy it) and 4 coordinated sessions | ~0.7 h run + 0.5 h build ≈ **1.3 h**, most coordination |

**Why A.** It needs no file transfer: the candidate files exist only on that machine. The run uses the exact binary
whose loader accepted the candidate offline. It is the fastest single-session option, and the run's RAM is small
(§384: well under 1 GB per process). **Inference:** per-core speed is similar to the cloud. Path B planned the same
~8 h per worker for local and cloud workers. The smoke measures it (7.4), and its projected wall time is recorded
before launch. The arms run interleaved by block, so a busy machine slows both arms alike. Timing is reported but is
not a metric.

## 5. Pre-registered analysis and decision rule

The analysis script is `live_ab_analyze.py` (sha256 `510ccf0dbb35c8caeb1203526a9e4aa8f41d29975eeb392d1e2731d9534d8d3c`, pasted in 7.2, stdlib + numpy). Its
constants are part of this pre-registration.

**Pairs.** These are the seeds with a result row in both `cand` and `prod`. A seed that fails or is missing in either
arm is dropped from the pair (stall handling, below). The `off` comparisons pair separately with each MCTS arm.

**Primary metric.** Run win (`won` = cleared the act-3 boss; `STS_STOP_AFTER_ACT=3`, keys off). The estimand is
Δwin = mean(cand.won − prod.won) over pairs.

**Tests.**
* Paired seed bootstrap of Δwin: 10,000 replicates, `numpy.random.default_rng(418063)`, 95% percentile CI.
* Exact two-sided McNemar test on the discordant pairs (b = cand wins and prod loses, c = the reverse), with
  α = 0.05.

**Verdict** (`report.json: verdict`):

| Verdict | Condition | Consequence |
|---|---|---|
| `INVALID` | any integrity error (below) or any **non-stall** seed failure | stop; no interpretation; report the errors |
| `CANDIDATE_BETTER` | CI lower > 0 **and** McNemar p < 0.05 | candidate qualifies for the production-pin swap PR (separately reviewed). Whether OOC MCTS is turned on is decided by the `cand − off` reading and a separate confirmation, not by this verdict. |
| `CANDIDATE_WORSE` | CI upper < 0 **and** McNemar p < 0.05 | no promotion; production CTM stays; ledger entry |
| `NO_DIFFERENCE_DETECTED` | otherwise (including a CI and McNemar that disagree) | no automatic promotion. Philipp decides. Promotion on teacher alignment and escape coverage is eligible only with flag `NONINFERIOR_AT_10PP` (CI lower > −10 pp) and without `BOSS_DEATH_EXCESS`. A larger confirmation needs a new pre-registration. |

* Suffix `_PROVISIONAL` if more than 6 primary pairs (about 5%) are dropped.
* Flag `BOSS_DEATH_EXCESS`: the paired CI for boss death (cand − prod) has lower bound > 0. This is the review's
  calibration diagnostic. It does not change the verdict, and the reviewer must address it.

**Integrity errors** (any one makes the verdict INVALID):
* A unit is missing its CSV, sidecar, log or trace, or has more than one sidecar record.
* A sidecar disagrees with the frozen configuration: seed block, 10000 sims, A0, 1 thread, fair, `native_silver`,
  reuse cap 32768, exact root budgets on, no learned stop, not adaptive, keys off, no root prior, or
  `executableGitSha` ≠ `648334e38dc5c92bc57a9b531f2f9f3308a732ff`.
* An MCTS arm lacks exactly one `[live OOC MCTS ON sims=2048 …]` banner with the §383 knobs and
  `active_lizard_correction=1`.
* The `prod` banner does not name the production paths. The `cand` banner does not name `FAST-final.native` and
  `STD1-escape.native`, or names a production path.
* `[ctm-research-candidate] candidate_id=pathb-r2` is missing from a `cand` log or present in a `prod` log.
* The `off` log has any MCTS banner.
* A completed seed has no battle trace rows, or (MCTS arms) no MCTS trace row.
* A won seed has a lost fight in its trace.
* A duplicate seed, or a seed outside its unit.
* **Unit exit status** (pre-run review B1). A crashed or killed process (segfault, abort, OOM kill) prints no failure
  line, so the exit code in `<tag>.done` decides. These are integrity errors:
  * a unit without `<tag>.done` or without `rc=` in it;
  * rc 0 with any failure line or any seed lacking a row;
  * rc 1 unless every failure line in the unit is a stall (`stall|depth bound`), or rc 1 with a seed that has neither
    a row nor a failure line;
  * any rc other than 0, 1 and 124 (crash, signal, startup failure).

  rc 124 (the 3 h `timeout` killed the unit) is not an error. Its unfinished seeds are dropped and listed under
  `census.<arm>.timeouts`. A seed missing from a unit that did not time out is always an integrity error, never a drop.

**Stall handling** (as in the Path B cloud runs, RESUME.md):
* A seed whose failure message matches `stall|depth bound` (Silver stall or depth bound) is **dropped**. It is listed
  under `census.<arm>.stalls`, and the pair is dropped.
* A seed with neither a row nor a failure line is dropped only if its unit timed out (rc 124). It is listed under
  `census.<arm>.missing` and `census.<arm>.timeouts`. In any other unit such a seed is a crash, and the verdict is
  INVALID (integrity errors above).
* No seed is rerun with changed settings and no replacement seeds are drawn.
* A unit interrupted by a reboot is rerun whole from scratch by the same launch command. Its partial files are moved to
  `run/aborted-<UTC>/` and the restart is logged in `logs/RESTARTS.txt`. Per-seed results are deterministic, so this
  does not bias the result.

**Secondaries** (descriptive, never part of the verdict; `report.json: secondary`, `descriptive`):
1. Floor reached: paired Δfloor CI. Also `floor + 10·won`, as in §367.
2. **Boss deaths per arm**, the review's note 2. Deaths are counted where the first lost fight's room is BOSS, per act,
   with bosses entered per act and the paired boss-death CI. The CSV floor ∈ {16, 33, 50} serves as a cross-check
   (`bossDeathCrossCheck` mismatches).
3. HP at fight starts: the per-run mean of pre-fight HP (paired CI), and HP entering the act 1/2/3 boss, paired on
   seeds where both arms reached that boss.
4. Smoke Bomb, per arm:
   * fights started with a Smoke Bomb in a usable slot (all, and non-boss), and runs with any such fight;
   * escapes: a won non-boss fight whose Smoke Bomb count drops (**approximate**, because the trace has no escape bit);
   * paired per-run Δescapes and Δsmoke-held fights.
5. OOC MCTS internals per arm: owned and fallback decisions, unsupported combats, support aborts, imagined combats,
   Brew-fallback preparations, support-failure counters, support reasons, MCTS CPU per run.
6. `cand − off` and `prod − off`: Δwin, McNemar, Δfloor and boss deaths. `prod − off` replicates §384 on fresh
   seeds. `cand − off` answers whether the refreshed CTM closes the §384 gap. Reading (not a verdict): only a
   `cand − off` CI lower bound > 0 would justify a separately pre-registered OOC-MCTS-on confirmation.
7. CPU s/run per arm and the time ratios.
8. Stall sensitivity (`sensitivity_stall_as_loss`; pre-run review note 1). A stalled seed counts as a loss for the
   stalling arm instead of being dropped. The row reports Δwin with its CI, the discordant counts and McNemar p.
   Stall drops depend on the outcome, because the fights differ by arm. This row shows whether they matter.

**Expected values** (**Inference**, for plausibility only): `prod` ≈ 56% wins and `off` ≈ 78% (§384). The candidate
should hold a Smoke Bomb at the start of a few percent of fights. Offline, Path B TEST had about 0.8% held-Smoke rows.

## 6. Frozen provenance (recorded by 7.3 before the smoke)

| Item | Value |
|---|---|
| Source | `648334e38dc5c92bc57a9b531f2f9f3308a732ff` (binary build commit; apps/src/include/CMake/models identical to `origin/main` `35de5b03`); `STS_EXECUTABLE_GIT_SHA` set to it |
| Binary | `$OC` copied to `$LAB/bin/one_combat`, sha256 must equal PREREG-FROZEN of the offline A/B: `dddb09f099a3a88994b23178b96e70346ac877c4d4deaf2d786df184972c7169` |
| Candidate | `FAST-final.native` `90806c25d784f7100b35ec755ad93756bf34d5aa297591891d5d3bb4314ba4f3`, `STD1-escape.native` `b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf`, `candidate-v3.json` `d9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d` (schema `ctm_research_candidate_v3`, `pathb-r2`, capabilities escape/escape) |
| Production CTM | `abb2a9ead6efd6b97ee64192e0459eb08ceff7fd93f2b5f4b87a0bf379e571ab` (fast), `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd` (Brew fallback) |
| OOC models | `ooc_strategic_tok_final.native` `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`; `models/v_win_trees.txt` `fc52c14cb7239a33b3c1f9d0477ccb6c895fd51a07240fe804744e605067ad70`; `models/v_rich_trees.txt` `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3`; screen-leaf anchor `models/candidates/v_win_x2b_trees.txt` `a251b33d4f71c1aa3fca529801da23ea9740dd0ded58abfb1a90fe69da7c9acf`; `models/candidates/screen_leaf_gbm_v1.trees` `8e2f9dc78cb31de382c876888a33007efc8a0526103b2c274d3980fc0915e051` |
| Scripts | `arm_env.sh`, `run_unit.sh`, `launch.sh`, `units.txt`, `live_ab_analyze.py` — sha256s written to `PREREG-FROZEN.txt` |
| Environment | full per-arm `env -i` list in `arm_env.sh`; `OMP_NUM_THREADS=1`; one process per unit; `J=10` concurrent units |
| Seeds | cohort `63000000..63000127`; smoke `63009000` |

## 7. Commands (Philipp's machine; paste in order)

### 7.0 Variables

```sh
WT=/home/philippherrmann/Documents/sts/wt-ctm-retrain   # the offline-A/B worktree; run everything from here
cd "$WT"
R2=$WT/build/ctm-retrain-a69f8862
OC=$WT/build/linux-gcc-release/one_combat
LAB=$WT/build/ctm-live-ab-20261009                       # new; nothing else writes here
GITSHA=648334e38dc5c92bc57a9b531f2f9f3308a732ff
J=10                                                     # concurrent units (one CPU each)
unset STS_CTM_PINS STS_CTM_RESEARCH_CANDIDATE_MANIFEST STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256
if [ -e "$LAB" ]; then echo "STOP: $LAB exists (resume only via 7.5)"; else mkdir -p "$LAB"/{bin,cand,run,smoke,logs}; fi
```

### 7.1 Preflight (seconds)

```sh
cp "$OC" $LAB/bin/one_combat && chmod +x $LAB/bin/one_combat      # basename one_combat: seed_guard needs it
cp $R2/durable/FAST-final.native $R2/durable/STD1-escape.native $R2/durable/candidate-v3.json $LAB/cand/
sha256sum $LAB/bin/one_combat $LAB/cand/FAST-final.native $LAB/cand/STD1-escape.native $LAB/cand/candidate-v3.json \
  selfplay/models/combat_transition_deepsets_lizard_t2.native \
  selfplay/models/combat_transition_near_full_except_smoke_v2.native selfplay/models/ooc_strategic_tok_final.native \
  models/v_win_trees.txt models/v_rich_trees.txt models/candidates/v_win_x2b_trees.txt \
  models/candidates/screen_leaf_gbm_v1.trees | tee $LAB/logs/inputs.sha256 | cut -c1-8
# expect, in order: dddb09f0 90806c25 b9188de0 d9d8377e abb2a9ea e9a18951 e62abd83 fc52c14c 3a342046 a251b33d 8e2f9dc7
git status --porcelain -- models selfplay/models tools/seed_guard.sh tools/agent/check_benchmark_canary.py   # expect nothing
git rev-parse HEAD | tee $LAB/logs/worktree.head
nproc; free -g | head -2; uptime        # need >= J idle cores; nothing else heavy running
```
Stop on any mismatch. Do not rebuild `$OC`. A different binary hash voids the "same binary as offline" provenance,
and needs a recorded amendment before 7.3.

### 7.2 Paste the scripts

```sh
cat > $LAB/arm_env.sh <<'ARM_ENV'
# #418 live A/B arm environments (LIVE-AB-PREREG.md section 2). Sourced by run_unit.sh.
# arm_env_args ARM BASE LAB -> KEY=VALUE lines for `env -i`. Shared part = §384 arm_env.sh (§377 live profile).
arm_env_args() {
  local arm=$1 base=$2 lab=$3
  printf '%s\n' "PATH=/usr/local/bin:/usr/bin:/bin" "HOME=$HOME" \
    STS_EXECUTABLE_GIT_SHA=648334e38dc5c92bc57a9b531f2f9f3308a732ff \
    STS_FAIR=1 STS_SEARCHER3=0 STS_SILVER_SEARCH=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_VNET_LEAF_DIRECT=0 \
    OMP_NUM_THREADS=1 OMP_DYNAMIC=FALSE \
    STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native \
    STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1 \
    STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0 \
    STS_COLLECT_KEYS=0 STS_REST_WIN=0 STS_STOP_AFTER_ACT=3 \
    STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=0 \
    "STS_OOC_DECISION_TRACE=$base.trace.jsonl"
  case $arm in
    off) echo STS_OOC_MCTS=0 ;;
    prod|cand) printf '%s\n' STS_OOC_MCTS=1 STS_OOC_MCTS_SIMS=2048 STS_OOC_MCTS_CPUCT=1.5 STS_OOC_MCTS_EARLY_STOP=1 \
        STS_OOC_MCTS_LEAF_COMBATS=0 STS_OOC_MCTS_LEAF_POLICY=v4 STS_OOC_MCTS_MAX_DEPTH=32 \
        STS_OOC_MCTS_PRIOR=policy STS_OOC_MCTS_ROOT_SELECTION=visits STS_OOC_MCTS_TEMPERATURE=1 \
        STS_OOC_MCTS_WIDEN_ALPHA=0.5 STS_OOC_MCTS_WIDEN_K=2 "STS_OOC_MCTS_TRACE=$base.mcts.csv" ;;
    *) echo "unknown arm $arm" >&2; return 1 ;;
  esac
  if [ "$arm" = cand ]; then printf '%s\n' \
    "STS_OOC_MCTS_COMBAT_MODEL=$lab/cand/FAST-final.native" \
    "STS_OOC_MCTS_BREW_FALLBACK_MODEL=$lab/cand/STD1-escape.native" \
    STS_OOC_MCTS_ACTIVE_LIZARD=1 \
    "STS_CTM_RESEARCH_CANDIDATE_MANIFEST=$lab/cand/candidate-v3.json" \
    STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=d9d8377e19a37fd3a76dc3ebae0c882706d11d4bd0b4a3df41691e3cf4d39d5d
  fi
}
ARM_ENV

cat > $LAB/run_unit.sh <<'RUN_UNIT'
#!/usr/bin/env bash
# usage: run_unit.sh WT LAB OUTDIR ARM LO N   -- one guarded bestbench unit; resumable via <tag>.done
set -uo pipefail
WT=$1 LAB=$2 OUT=$3 ARM=$4 LO=$5 N=$6
tag=$ARM-$LO base=$OUT/$ARM-$LO
[ -f "$base.done" ] && exit 0
if compgen -G "$base.*" > /dev/null; then          # interrupted unit: keep its files, rerun it whole
  ts=$(date -u +%Y%m%dT%H%M%SZ); mkdir -p "$OUT/aborted-$ts"; mv "$base".* "$OUT/aborted-$ts/"
  echo "$tag moved to aborted-$ts" >> "$LAB/logs/RESTARTS.txt"
fi
source "$LAB/arm_env.sh"
mapfile -t E < <(arm_env_args "$ARM" "$base" "$LAB") || exit 2
cd "$WT" || exit 2
start=$(date -u +%FT%TZ)
env -i "${E[@]}" timeout 3h bash tools/seed_guard.sh "$LAB/bin/one_combat" \
  bestbench 10000 "$N" 0 "$LO" "$base.csv" > "$base.log" 2>&1
rc=$?
echo "tag=$tag rc=$rc start=$start end=$(date -u +%FT%TZ)" > "$base.done"
exit 0
RUN_UNIT

cat > $LAB/launch.sh <<'LAUNCH'
#!/usr/bin/env bash
# usage: launch.sh WT LAB J   -- runs every unit in LAB/units.txt into LAB/run with J in parallel; rerun to resume
set -uo pipefail
WT=$1 LAB=$2 J=$3
n=$(wc -l < "$LAB/units.txt")
xargs -P "$J" -L 1 bash "$LAB/run_unit.sh" "$WT" "$LAB" "$LAB/run" < "$LAB/units.txt"
done_n=$(ls "$LAB"/run/*.done 2>/dev/null | wc -l)
if [ "$done_n" = "$n" ]; then
  { echo "finished=$(date -u +%FT%TZ) units=$done_n"; cat "$LAB"/run/*.done
    grep -h "bestbench-seed-failure" "$LAB"/run/*.log || true
    grep -h "^BEST " "$LAB"/run/*.log | sort | uniq -c | sort -rn | head -3; } > "$LAB/run/DONE"
fi
LAUNCH

{ for b in $(seq 0 15); do lo=$((63000000 + 8 * b))
    if [ $((b % 2)) -eq 0 ]; then echo "prod $lo 8"; echo "cand $lo 8"; else echo "cand $lo 8"; echo "prod $lo 8"; fi
  done
  for b in $(seq 0 15); do echo "off $((63000000 + 8 * b)) 8"; done; } > $LAB/units.txt
wc -l $LAB/units.txt     # expect 48 (MCTS units first so the short off units fill the tail)

cat > $LAB/live_ab_analyze.py <<'LIVE_AB_PY'
#!/usr/bin/env python3
"""#418 live A/B: production CTM stack vs the pathb-r2 research candidate inside live OOC MCTS.

Pre-registered protocol: LIVE-AB-PREREG.md (written before any cohort seed ran). The
constants below are part of the pre-registration; do not edit them after the cohort starts.
Reads bestbench outputs only; runs no seeds. stdlib + numpy.

Run directory layout (one file set per unit = arm x block of seeds):
  <arm>-<lo>.csv  .csv.meta.json  .log  .trace.jsonl  .done  [.mcts.csv  .mcts.csv.support.jsonl]
  <tag>.done is written by run_unit.sh: "tag=... rc=N start=... end=..." (rc of timeout+seed_guard+bestbench)
  arms: prod (OOC MCTS + production CTM), cand (OOC MCTS + candidate CTM), off (MCTS off, flat 10k)

usage:
  live_ab_analyze.py check   RUN_DIR --seed-lo N --seed-count N --git-sha SHA [--block 8]
  live_ab_analyze.py analyze RUN_DIR --seed-lo N --seed-count N --git-sha SHA [--block 8] --out REPORT.json
  live_ab_analyze.py selftest
"""
from __future__ import annotations

import argparse
import csv
import glob
import hashlib
import json
import math
import os
import re
import sys
import tempfile
from pathlib import Path

import numpy as np

SCHEMA = "ctm_live_ab_v1"
# ---- pre-registered constants (LIVE-AB-PREREG.md section 5) ----
REPS, RNG_SEED = 10000, 418063   # paired seed bootstrap, percentile 95% CI
ALPHA = 0.05                     # exact two-sided McNemar on discordant pairs
NONINF_MARGIN = -0.10            # NO_DIFFERENCE_DETECTED sub-flag: CI lower bound above -10 pp
MAX_DROPPED_PAIRS = 6            # more dropped primary pairs (stall/missing) -> verdict _PROVISIONAL
CANDIDATE_ID = "pathb-r2"
PROD_FAST = "selfplay/models/combat_transition_deepsets_lizard_t2.native"
PROD_STD = "selfplay/models/combat_transition_near_full_except_smoke_v2.native"
BOSS_FLOORS = {16, 33, 50}       # A0 act 1-3 boss floors (cross-check of the trace)
STALL_RX = re.compile(r"stall|depth bound")
TIMEOUT_RC = 124                 # `timeout 3h` killed the unit: its unfinished seeds are dropped and listed
# -----------------------------------------------------------------
ARMS = ("prod", "cand", "off")
MCTS_ARMS = ("prod", "cand")
CSV_HEADER = ["seed", "won", "floor", "act", "hpEnd", "maxHp", "fightsLost", "deathCombat", "deathEncounter", "sec"]
FAIL_RX = re.compile(r"^\[bestbench-seed-failure\] seed=(\d+) error=(.*)$")
RC_RX = re.compile(r"(?:^|\s)rc=(-?\d+)(?:\s|$)")
MCTS_SUM = ("oocDecisions", "mctsOwned", "mctsFallback", "unsupportedCombats", "mctsSupportAborts",
            "imaginedCombats", "transitionSamples", "simulations", "hybridFallbackPreparations",
            "hybridFastSupportFailures", "hybridFallbackSupportFailures", "continuationLimitAborts")


def sha256(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


# ------------------------------------------------------------------ loading
def unit_los(seed_lo: int, seed_count: int, block: int) -> list[int]:
    return list(range(seed_lo, seed_lo + seed_count, block))


def load_unit(run: Path, arm: str, lo: int, n: int, git_sha: str, errors: list) -> dict:
    """One unit's rows, failures, traces, and integrity errors (appended to errors)."""
    base = run / f"{arm}-{lo}"
    tag = f"{arm}-{lo}"
    out = {"rows": {}, "failures": {}, "battles": {}, "mcts": {}, "support": {}, "present": False,
           "timeout": None, "rc": None}
    csv_path = Path(str(base) + ".csv")
    if not csv_path.exists():
        errors.append(f"{tag}: missing results CSV")
        return out
    out["present"] = True
    expected = set(range(lo, lo + n))
    with csv_path.open(newline="") as f:
        r = csv.DictReader(f)
        if r.fieldnames != CSV_HEADER:
            errors.append(f"{tag}: CSV header {r.fieldnames}")
            return out
        for x in r:
            s = int(x["seed"])
            if s not in expected:
                errors.append(f"{tag}: seed {s} outside unit")
            if s in out["rows"]:
                errors.append(f"{tag}: duplicate seed {s}")
            out["rows"][s] = {"won": int(x["won"]), "floor": int(x["floor"]), "act": int(x["act"]),
                              "hpEnd": int(x["hpEnd"]), "maxHp": int(x["maxHp"]),
                              "fightsLost": int(x["fightsLost"]), "deathEncounter": int(x["deathEncounter"]),
                              "sec": float(x["sec"])}
    # sidecar: exactly one invocation record with the frozen configuration
    meta_path = Path(str(base) + ".csv.meta.json")
    metas = [json.loads(l) for l in meta_path.open()] if meta_path.exists() else []
    if len(metas) != 1:
        errors.append(f"{tag}: expected 1 sidecar record, found {len(metas)}")
    else:
        m, c = metas[0], metas[0].get("config", {})
        checks = {"seedBlock": m.get("seedBlock") == {"lo": lo, "hi": lo + n - 1}, "sims": m.get("sims") == 10000,
                  "asc": m.get("asc") == 0, "threads": m.get("threads") == 1, "fair": c.get("fairPlay") is True,
                  "backend": c.get("effectiveCombatBackend") == "native_silver",
                  "reuseCap": c.get("silverReuseCap") == 32768, "exactRoot": c.get("silverExactRootBudgets") is True,
                  "noLearnedStop": c.get("silverLearnedStopModel", "") == "",
                  "noAdaptive": c.get("silverAdaptiveEnabled") is False, "keysOff": c.get("collectKeys") is False,
                  "gitSha": c.get("executableGitSha") == git_sha, "noRootPrior": c.get("silverRootPrior", "") == ""}
        bad = [k for k, ok in checks.items() if not ok]
        if bad:
            errors.append(f"{tag}: sidecar mismatch {bad}")
    # log: failures and arm identity
    log_path = Path(str(base) + ".log")
    text = log_path.read_text(errors="replace") if log_path.exists() else ""
    if not text:
        errors.append(f"{tag}: missing or empty log")
    for line in text.splitlines():
        mm = FAIL_RX.match(line)
        if mm:
            out["failures"][int(mm.group(1))] = mm.group(2)
    # unit exit status: a crashed or killed process prints no failure line, so the rc decides
    done_path = Path(str(base) + ".done")
    rc_m = RC_RX.search(done_path.read_text()) if done_path.exists() else None
    if rc_m is None:
        errors.append(f"{tag}: missing .done or no rc in it")
    else:
        rc = out["rc"] = int(rc_m.group(1))
        missing = sorted(expected - set(out["rows"]) - set(out["failures"]))
        nonstall = [s for s, m in out["failures"].items() if not STALL_RX.search(m)]
        if rc == TIMEOUT_RC:
            out["timeout"] = {"unit": tag, "missingSeeds": missing}
        elif rc == 0:
            if out["failures"] or missing:
                errors.append(f"{tag}: rc=0 but {len(out['failures'])} failure lines and {len(missing)} missing seeds")
        elif rc == 1:
            if not out["failures"] or nonstall:
                errors.append(f"{tag}: rc=1 needs only stall failure lines (stall {len(out['failures']) - len(nonstall)}, other {len(nonstall)})")
            if missing:
                errors.append(f"{tag}: rc=1 with {len(missing)} seeds lacking a row and a failure line (crash)")
        else:
            errors.append(f"{tag}: unit rc={rc} (crash, signal or startup failure); missing seeds {missing}")
    banner = [l for l in text.splitlines() if l.startswith("[live OOC MCTS ON ")]
    cand_line = f"[ctm-research-candidate] candidate_id={CANDIDATE_ID}" in text
    if arm == "off":
        if banner or "[ctm-research-candidate]" in text:
            errors.append(f"{tag}: MCTS or candidate active in the off arm")
    else:
        if len(banner) != 1:
            errors.append(f"{tag}: expected one live OOC MCTS banner, found {len(banner)}")
        else:
            b = banner[0]
            need = ["sims=2048", "active_lizard_correction=1", "leaf_value=screengbm", "cpuct=1.5",
                    "root_selection=visits", "early_stop=1", "merge_outcomes=0", "dispatch=precombat_entropic_brew"]
            if arm == "prod":
                need += [f"combat_model={PROD_FAST}", f"brew_fallback_model={PROD_STD}"]
            else:
                need += ["FAST-final.native", "STD1-escape.native"]
                if PROD_FAST in b or PROD_STD in b:
                    errors.append(f"{tag}: candidate arm loaded a production artifact path")
            miss = [k for k in need if k not in b]
            if miss:
                errors.append(f"{tag}: banner lacks {miss}")
        if (arm == "cand") != cand_line or (arm == "prod" and "[ctm-research-candidate]" in text):
            errors.append(f"{tag}: research-candidate log line {'missing' if arm == 'cand' else 'present'}")
    # decision trace: battle rows per seed
    tr = Path(str(base) + ".trace.jsonl")
    if not tr.exists():
        errors.append(f"{tag}: missing decision trace")
    else:
        for line in tr.open():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("kind") == "battle":
                out["battles"].setdefault(int(row["seed"]), []).append(row)
    # MCTS per-seed trace (MCTS arms only)
    if arm in MCTS_ARMS:
        mp = Path(str(base) + ".mcts.csv")
        if not mp.exists():
            errors.append(f"{tag}: missing MCTS trace")
        else:
            with mp.open(newline="") as f:
                for x in csv.DictReader(f):
                    out["mcts"][int(x["seed"])] = {k: float(x[k]) for k in x if k != "seed"}
        sp = Path(str(mp) + ".support.jsonl")
        if sp.exists():
            for line in sp.open():
                if line.strip():
                    row = json.loads(line)
                    out["support"][int(row["seed"])] = row.get("reasons", {})
    return out


def load_arm(run: Path, arm: str, a) -> dict:
    errors: list[str] = []
    arm_d = {"rows": {}, "failures": {}, "battles": {}, "mcts": {}, "support": {}, "errors": errors, "timeouts": []}
    for lo in unit_los(a.seed_lo, a.seed_count, a.block):
        n = min(a.block, a.seed_lo + a.seed_count - lo)
        u = load_unit(run, arm, lo, n, a.git_sha, errors)
        for k in ("rows", "failures", "battles", "mcts", "support"):
            arm_d[k].update(u[k])
        if u["timeout"]:
            arm_d["timeouts"].append(u["timeout"])
    for s in arm_d["rows"]:
        if s in arm_d["failures"]:
            errors.append(f"{arm}: seed {s} has both a row and a failure line")
    return arm_d


# ------------------------------------------------------------------ statistics
def boot_ci(x: np.ndarray, reps: int = REPS, seed: int = RNG_SEED) -> list[float] | None:
    """Mean and percentile 95% CI of a paired per-seed difference; fresh generator per statistic."""
    x = np.asarray(x, dtype=float)
    if len(x) == 0:
        return None
    rng = np.random.default_rng(seed)
    means = x[rng.integers(0, len(x), size=(reps, len(x)))].mean(axis=1)
    lo, hi = np.percentile(means, [2.5, 97.5])
    return [float(x.mean()), float(lo), float(hi)]


def mcnemar_exact(b: int, c: int) -> float:
    """Two-sided exact McNemar (binomial on discordant pairs, p = 1/2)."""
    n = b + c
    if n == 0:
        return 1.0
    k = min(b, c)
    tail = sum(math.comb(n, i) for i in range(k + 1)) / 2 ** n
    return float(min(1.0, 2 * tail))


# ------------------------------------------------------------------ per-run features
def run_features(battles: list[dict], row: dict) -> dict:
    bs = sorted(battles, key=lambda r: r["fight"])
    boss = [b for b in bs if b["pre"]["room"] == "BOSS"]
    died = [b for b in bs if not b["won"]]
    smoke_fights = [b for b in bs if "SMOKE_BOMB" in b["pre"]["potions"]]
    escapes = [b for b in smoke_fights if b["won"] and b["pre"]["room"] != "BOSS"
               and b["post"]["potions"].count("SMOKE_BOMB") < b["pre"]["potions"].count("SMOKE_BOMB")]
    boss_hp = {}
    for b in boss:
        boss_hp.setdefault(int(b["pre"]["act"]), (b["pre"]["hp"], b["pre"]["maxHp"]))
    return {
        "fights": len(bs),
        "boss_death": int(bool(died) and died[0]["pre"]["room"] == "BOSS"),
        "boss_death_act": int(died[0]["pre"]["act"]) if died and died[0]["pre"]["room"] == "BOSS" else 0,
        "boss_death_csv": int(row["won"] == 0 and row["floor"] in BOSS_FLOORS),
        "death_room": died[0]["pre"]["room"] if died else "",
        "bosses_entered": len(boss),
        "boss_hp": boss_hp,
        "mean_start_hp": float(np.mean([b["pre"]["hp"] for b in bs])) if bs else float("nan"),
        "mean_start_hp_frac": float(np.mean([b["pre"]["hp"] / b["pre"]["maxHp"] for b in bs])) if bs else float("nan"),
        "smoke_fights": len(smoke_fights),
        "smoke_fights_nonboss": sum(b["pre"]["room"] != "BOSS" for b in smoke_fights),
        "smoke_runs": int(bool(smoke_fights)),
        "escapes": len(escapes),
        "trace_won_last": int(bs[-1]["won"]) if bs else -1,
    }


def summarize(x) -> float:
    return float(np.mean(x)) if len(x) else float("nan")


# ------------------------------------------------------------------ report
def build_report(a) -> dict:
    run = Path(a.run_dir)
    data = {arm: load_arm(run, arm, a) for arm in ARMS}
    expected = set(range(a.seed_lo, a.seed_lo + a.seed_count))
    errors = [e for arm in ARMS for e in data[arm]["errors"]]
    census, dropped = {}, {}
    for arm in ARMS:
        d = data[arm]
        stalls = {s: m for s, m in d["failures"].items() if STALL_RX.search(m)}
        other = {s: m for s, m in d["failures"].items() if not STALL_RX.search(m)}
        missing = sorted(expected - set(d["rows"]) - set(d["failures"]))
        census[arm] = {"rows": len(d["rows"]), "stalls": {str(s): m for s, m in sorted(stalls.items())},
                       "otherFailures": {str(s): m for s, m in sorted(other.items())}, "missing": missing,
                       "timeouts": d["timeouts"]}
        if other:
            errors.append(f"{arm}: {len(other)} non-stall seed failures (see census)")
        dropped[arm] = set(d["failures"]) | set(missing)
        # trace / CSV consistency on completed seeds
        for s, row in d["rows"].items():
            bl = d["battles"].get(s, [])
            if not bl:
                errors.append(f"{arm}: seed {s} has no battle trace rows")
            elif row["won"] == 1 and any(not b["won"] for b in bl):
                errors.append(f"{arm}: seed {s} won but the trace has a lost fight")
            if arm in MCTS_ARMS and s not in d["mcts"]:
                errors.append(f"{arm}: seed {s} has no MCTS trace row")
    feats = {arm: {s: run_features(data[arm]["battles"].get(s, []), r) for s, r in data[arm]["rows"].items()}
             for arm in ARMS}

    def pairs(x, y):
        return sorted((set(data[x]["rows"]) & set(data[y]["rows"])) - dropped[x] - dropped[y])

    def compare(x, y, primary=False) -> dict:
        ps = pairs(x, y)
        wx = np.array([data[x]["rows"][s]["won"] for s in ps])
        wy = np.array([data[y]["rows"][s]["won"] for s in ps])
        fx = np.array([data[x]["rows"][s]["floor"] for s in ps])
        fy = np.array([data[y]["rows"][s]["floor"] for s in ps])
        b, c = int(((wx == 1) & (wy == 0)).sum()), int(((wx == 0) & (wy == 1)).sum())
        bdx = np.array([feats[x][s]["boss_death"] for s in ps])
        bdy = np.array([feats[y][s]["boss_death"] for s in ps])
        out = {"pairs": len(ps), "winRate": [summarize(wx), summarize(wy)],
               "win": boot_ci(wx - wy), "discordant": [b, c], "mcnemarP": mcnemar_exact(b, c),
               "floor": boot_ci(fx - fy), "score_floor_plus_10won": boot_ci((fx + 10 * wx) - (fy + 10 * wy)),
               "bossDeaths": [int(bdx.sum()), int(bdy.sum())], "bossDeath": boot_ci(bdx - bdy),
               "secRatio": summarize([data[x]["rows"][s]["sec"] for s in ps]) /
                           max(summarize([data[y]["rows"][s]["sec"] for s in ps]), 1e-9)}
        if primary:
            out["droppedPairs"] = sorted((expected - set(ps)))
        return out

    primary = compare("cand", "prod", primary=True)
    lo, hi = primary["win"][1], primary["win"][2]
    p = primary["mcnemarP"]
    if errors:
        verdict = "INVALID"
    elif lo > 0 and p < ALPHA:
        verdict = "CANDIDATE_BETTER"
    elif hi < 0 and p < ALPHA:
        verdict = "CANDIDATE_WORSE"
    else:
        verdict = "NO_DIFFERENCE_DETECTED"
    flags = []
    if verdict == "NO_DIFFERENCE_DETECTED" and lo > NONINF_MARGIN:
        flags.append("NONINFERIOR_AT_10PP")
    if primary["bossDeath"] and primary["bossDeath"][1] > 0:
        flags.append("BOSS_DEATH_EXCESS")
    if verdict != "INVALID" and len(primary["droppedPairs"]) > MAX_DROPPED_PAIRS:
        verdict += "_PROVISIONAL"

    # descriptive sensitivity: a stalled seed counts as a loss for the stalling arm (not part of the verdict)
    stalled = {arm: {s for s, m in data[arm]["failures"].items() if STALL_RX.search(m)} for arm in MCTS_ARMS}
    sens_seeds = sorted(s for s in expected
                        if all(s in data[arm]["rows"] or s in stalled[arm] for arm in MCTS_ARMS))
    won = {arm: np.array([data[arm]["rows"][s]["won"] if s in data[arm]["rows"] else 0 for s in sens_seeds])
           for arm in MCTS_ARMS}
    sb, sc = int(((won["cand"] == 1) & (won["prod"] == 0)).sum()), int(((won["cand"] == 0) & (won["prod"] == 1)).sum())
    sensitivity = {"rule": "stall counts as a loss for the stalling arm", "pairs": len(sens_seeds),
                   "win": boot_ci(won["cand"] - won["prod"]), "discordant": [sb, sc], "mcnemarP": mcnemar_exact(sb, sc)}

    # secondaries (descriptive)
    ps = pairs("cand", "prod")
    sec = {"perArm": {}, "bossEntryHp": {}, "bossDeathCrossCheck": {}}
    for arm in ARMS:
        rows, f = data[arm]["rows"], feats[arm]
        s_arm = [s for s in rows if s not in dropped[arm]]
        bosses = {act: sum(act in f[s]["boss_hp"] for s in s_arm) for act in (1, 2, 3)}
        boss_deaths_act = {act: sum(f[s]["boss_death_act"] == act for s in s_arm) for act in (1, 2, 3)}
        per = {"runs": len(s_arm), "winRate": summarize([rows[s]["won"] for s in s_arm]),
               "meanFloor": summarize([rows[s]["floor"] for s in s_arm]),
               "cpuSecPerRun": summarize([rows[s]["sec"] for s in s_arm]),
               "meanHpAfterWin": summarize([rows[s]["hpEnd"] for s in s_arm if rows[s]["won"]]),
               "deaths": sum(1 - rows[s]["won"] for s in s_arm),
               "bossDeaths": sum(f[s]["boss_death"] for s in s_arm),
               "bossesEnteredByAct": {str(k): v for k, v in bosses.items()},
               "bossDeathsByAct": {str(k): v for k, v in boss_deaths_act.items()},
               "meanStartHp": summarize([f[s]["mean_start_hp"] for s in s_arm if f[s]["fights"]]),
               "meanStartHpFraction": summarize([f[s]["mean_start_hp_frac"] for s in s_arm if f[s]["fights"]]),
               "smokeHeldFights": sum(f[s]["smoke_fights"] for s in s_arm),
               "smokeHeldNonBossFights": sum(f[s]["smoke_fights_nonboss"] for s in s_arm),
               "runsWithSmokeHeldAtAFight": sum(f[s]["smoke_runs"] for s in s_arm),
               "escapes": sum(f[s]["escapes"] for s in s_arm)}
        if arm in MCTS_ARMS:
            m = data[arm]["mcts"]
            per["mcts"] = {k: float(sum(m[s].get(k, 0.0) for s in s_arm if s in m)) for k in MCTS_SUM}
            per["mcts"]["mctsCpuSecPerRun"] = summarize([m[s]["mctsCpuSec"] for s in s_arm if s in m])
            reasons: dict[str, float] = {}
            for s in s_arm:
                for k, v in data[arm]["support"].get(s, {}).items():
                    reasons[k] = reasons.get(k, 0) + v
            per["mcts"]["supportReasons"] = dict(sorted(reasons.items()))
        sec["perArm"][arm] = per
        sec["bossDeathCrossCheck"][arm] = sum(f[s]["boss_death"] != f[s]["boss_death_csv"] for s in s_arm)
    for act in (1, 2, 3):
        both = [s for s in ps if act in feats["cand"][s]["boss_hp"] and act in feats["prod"][s]["boss_hp"]]
        sec["bossEntryHp"][str(act)] = {
            "pairs": len(both),
            "hp": boot_ci([feats["cand"][s]["boss_hp"][act][0] - feats["prod"][s]["boss_hp"][act][0] for s in both]),
            "means": [summarize([feats[a_][s]["boss_hp"][act][0] for s in both]) for a_ in ("cand", "prod")]}
    sec["meanStartHp"] = boot_ci([feats["cand"][s]["mean_start_hp"] - feats["prod"][s]["mean_start_hp"] for s in ps])
    sec["escapesPerRun"] = boot_ci([feats["cand"][s]["escapes"] - feats["prod"][s]["escapes"] for s in ps])
    sec["smokeHeldFightsPerRun"] = boot_ci([feats["cand"][s]["smoke_fights"] - feats["prod"][s]["smoke_fights"] for s in ps])

    script = Path(__file__).resolve()
    return {"schema": SCHEMA, "runDir": str(run.resolve()), "seedLo": a.seed_lo, "seedCount": a.seed_count,
            "gitSha": a.git_sha, "scriptSha256": sha256(script), "numpy": np.__version__,
            "constants": {k: v for k, v in globals().items() if k.isupper() and isinstance(v, (int, float, str))
                          and k not in ("SCHEMA",)},
            "verdict": verdict, "flags": flags, "integrityErrors": errors, "census": census,
            "primary_cand_minus_prod": primary, "sensitivity_stall_as_loss": sensitivity,
            "descriptive": {"cand_minus_off": compare("cand", "off"), "prod_minus_off": compare("prod", "off")},
            "secondary": sec}


def cmd_check(a) -> int:
    run = Path(a.run_dir)
    errors = []
    for arm in ARMS:
        d = load_arm(run, arm, a)
        errors += d["errors"]
        print(json.dumps({"arm": arm, "rows": len(d["rows"]), "failures": d["failures"],
                          "secPerRun": summarize([r["sec"] for r in d["rows"].values()]),
                          "battleRows": sum(len(v) for v in d["battles"].values()),
                          "mctsRows": len(d["mcts"])}))
    print(json.dumps({"integrityErrors": errors}, indent=1))
    return 1 if errors else 0


# ------------------------------------------------------------------ self-test (synthetic data)
def _write_unit(run: Path, arm: str, lo: int, n: int, git_sha: str, outcome, fail=None) -> None:
    base = run / f"{arm}-{lo}"
    with open(str(base) + ".csv", "w") as f:
        f.write(",".join(CSV_HEADER) + "\n")
    meta = {"objective": "bestbench", "seedBlock": {"lo": lo, "hi": lo + n - 1}, "nSeeds": n, "asc": 0,
            "sims": 10000, "threads": 1,
            "config": {"fairPlay": True, "effectiveCombatBackend": "native_silver", "silverReuseCap": 32768,
                       "silverExactRootBudgets": True, "silverLearnedStopModel": "", "silverAdaptiveEnabled": False,
                       "collectKeys": False, "executableGitSha": git_sha}}
    Path(str(base) + ".csv.meta.json").write_text(json.dumps(meta) + "\n")
    log = ["[collect keys OFF]"]
    if arm == "cand":
        log.append(f"[ctm-research-candidate] candidate_id={CANDIDATE_ID}")
    if arm != "off":
        fast = PROD_FAST if arm == "prod" else "/x/cand/FAST-final.native"
        std = PROD_STD if arm == "prod" else "/x/cand/STD1-escape.native"
        log.append(f"[live OOC MCTS ON sims=2048 combat_model={fast} brew_fallback_model={std} "
                   "dispatch=precombat_entropic_brew active_lizard_correction=1 prior=policy temperature=1 "
                   "cpuct=1.5 widen_k=2 widen_alpha=0.5 max_depth=32 root_selection=visits early_stop=1 "
                   "gap_stop_20=0 merge_outcomes=0 leaf_value=screengbm leaf_combats=0 leaf_policy=v4]")
    trace, mcts = [], []
    rows = []
    for s in range(lo, lo + n):
        if fail and s in fail:
            log.append(f"[bestbench-seed-failure] seed={s} error={fail[s]}")
            continue
        won, death_floor, smoke = outcome(arm, s)
        floors = [3, 6, 10, 16, 20, 25, 33, 40, 45, 50]
        hp = 70
        last = len(floors) if won else floors.index(death_floor) + 1
        for i, fl in enumerate(floors[:last]):
            room = "BOSS" if fl in BOSS_FLOORS else "MONSTER"
            pots = ["SMOKE_BOMB"] if smoke and i == 1 else []
            lost = (not won) and i == last - 1
            post = [] if (pots and room != "BOSS") else pots
            trace.append({"seed": s, "kind": "battle", "fight": i + 1, "encounter": "X", "won": not lost,
                          "pre": {"act": 1 + (fl > 16) + (fl > 33), "floor": fl, "room": room, "hp": hp,
                                  "maxHp": 80, "potions": pots},
                          "post": {"act": 1, "floor": fl, "room": room, "hp": hp - 5, "maxHp": 80, "potions": post}})
            hp -= 3 if arm == "cand" else 4
        trace.append({"seed": s, "kind": "ooc", "idx": 0})
        rows.append([s, int(won), 50 if won else death_floor, 3, 30 if won else 0, 80, 0 if won else 1,
                     -1 if won else last, -1, 100.0 + (s % 7)])
        mcts.append(s)
    with open(str(base) + ".csv", "a") as f:
        for r in rows:
            f.write(",".join(map(str, r)) + "\n")
    Path(str(base) + ".log").write_text("\n".join(log) + "\nBEST win%=50\n")
    rc = 1 if any(fail and s in fail for s in range(lo, lo + n)) else 0
    Path(str(base) + ".done").write_text(f"tag={arm}-{lo} rc={rc} start=x end=x\n")
    with open(str(base) + ".trace.jsonl", "w") as f:
        for t in trace:
            f.write(json.dumps(t) + "\n")
    if arm != "off":
        hdr = ["seed"] + [k for k in MCTS_SUM] + ["mctsCpuSec"]
        with open(str(base) + ".mcts.csv", "w") as f:
            f.write(",".join(hdr) + "\n")
            for s in mcts:
                f.write(",".join([str(s)] + ["1"] * len(MCTS_SUM) + ["50.0"]) + "\n")
        with open(str(base) + ".mcts.csv.support.jsonl", "w") as f:
            for s in mcts:
                f.write(json.dumps({"seed": s, "reasons": {"hp_envelope": 1} if arm == "prod" else {}}) + "\n")


def _synth(run: Path, lo: int, count: int, block: int, sha: str, p_prod: float, p_cand: float, rng_seed: int,
           fail=None) -> None:
    rng = np.random.default_rng(rng_seed)
    u = {s: rng.random() for s in range(lo, lo + count)}           # shared latent seed difficulty -> pairing
    noise = {(a_, s): rng.random() for a_ in ARMS for s in range(lo, lo + count)}

    def outcome(arm, s):
        p = {"prod": p_prod, "cand": p_cand, "off": 0.78}[arm]
        won = (0.6 * u[s] + 0.4 * noise[(arm, s)]) < p
        return won, (16 if s % 3 == 0 else 33 if s % 3 == 1 else 45), s % 5 == 0

    for blo in range(lo, lo + count, block):
        for arm in ARMS:
            _write_unit(run, arm, blo, min(block, lo + count - blo), sha,
                        outcome, (fail or {}).get(arm))


def selftest() -> int:
    sha = "a" * 40
    ns = argparse.Namespace
    results = {}
    with tempfile.TemporaryDirectory() as td:
        for name, pp, pc, fail in [
                ("equal", 0.56, 0.56, None),
                ("better", 0.45, 0.80, None),
                ("worse", 0.80, 0.45, None),
                ("stall", 0.56, 0.56, {"cand": {63000003: "native Silver backend: stall: exceeded 1000 decisions"}}),
                ("other", 0.56, 0.56, {"prod": {63000004: "combat runtime research candidate identity"}})]:
            run = Path(td) / name
            run.mkdir()
            _synth(run, 63000000, 128, 8, sha, pp, pc, 7, fail)
            a = ns(run_dir=str(run), seed_lo=63000000, seed_count=128, block=8, git_sha=sha)
            rep = build_report(a)
            results[name] = rep
        assert results["equal"]["verdict"] == "NO_DIFFERENCE_DETECTED", results["equal"]["verdict"]
        assert results["better"]["verdict"] == "CANDIDATE_BETTER", results["better"]["primary_cand_minus_prod"]
        assert results["worse"]["verdict"] == "CANDIDATE_WORSE"
        assert results["stall"]["verdict"] == "NO_DIFFERENCE_DETECTED", results["stall"]["integrityErrors"]
        assert results["stall"]["primary_cand_minus_prod"]["pairs"] == 127
        assert results["stall"]["primary_cand_minus_prod"]["droppedPairs"] == [63000003]
        assert results["other"]["verdict"] == "INVALID"
        sens = results["stall"]["sensitivity_stall_as_loss"]
        assert sens["pairs"] == 128 and sens["discordant"][0] + sens["discordant"][1] >= 28
        # crash: a unit's process dies after 3 of 8 seeds (no failure lines) -> INVALID
        def truncate(run, tag, keep, rc):
            p = run / f"{tag}.csv"
            p.write_text("".join(p.read_text().splitlines(True)[:1 + keep]))
            (run / f"{tag}.done").write_text(f"tag={tag} rc={rc} start=x end=x\n")
        for name, rc, want in [("crash", 139, "INVALID"), ("crash1", 1, "INVALID"), ("crash0", 0, "INVALID"),
                               ("timeout", 124, "NO_DIFFERENCE_DETECTED")]:
            run = Path(td) / name
            run.mkdir()
            _synth(run, 63000000, 128, 8, sha, 0.56, 0.56, 7)
            truncate(run, "cand-63000016", 3, rc)
            rep_ = build_report(ns(run_dir=str(run), seed_lo=63000000, seed_count=128, block=8, git_sha=sha))
            assert rep_["verdict"] == want, (name, rep_["verdict"], rep_["integrityErrors"])
            results[name] = rep_
        t = results["timeout"]
        assert t["census"]["cand"]["timeouts"] == [{"unit": "cand-63000016", "missingSeeds": list(range(63000019, 63000024))}]
        assert t["primary_cand_minus_prod"]["pairs"] == 123
        # a missing .done is INVALID
        (Path(td) / "equal" / "off-63000008.done").unlink()
        assert build_report(ns(run_dir=str(Path(td) / "equal"), seed_lo=63000000, seed_count=128, block=8,
                               git_sha=sha))["verdict"] == "INVALID"
        (Path(td) / "equal" / "off-63000008.done").write_text("tag=off-63000008 rc=0 start=x end=x\n")
        r = results["equal"]
        assert r["integrityErrors"] == [], r["integrityErrors"]
        pa = r["secondary"]["perArm"]
        assert pa["prod"]["escapes"] > 0 and pa["prod"]["escapes"] == pa["prod"]["smokeHeldNonBossFights"]
        assert r["secondary"]["bossDeathCrossCheck"] == {"prod": 0, "cand": 0, "off": 0}
        assert r["secondary"]["bossEntryHp"]["2"]["hp"][0] > 0     # cand loses less HP per fight in the synth
        # McNemar and bootstrap sanity
        assert abs(mcnemar_exact(10, 0) - 2 / 1024) < 1e-12 and mcnemar_exact(5, 5) == 1.0
        assert boot_ci(np.zeros(10)) == [0.0, 0.0, 0.0]
        # determinism: same inputs -> identical report
        a = ns(run_dir=str(Path(td) / "equal"), seed_lo=63000000, seed_count=128, block=8, git_sha=sha)
        assert json.dumps(build_report(a), sort_keys=True) == json.dumps(results["equal"], sort_keys=True)
        # integrity: a candidate log without the research-candidate line is INVALID
        logp = Path(td) / "equal" / "cand-63000000.log"
        logp.write_text(logp.read_text().replace("[ctm-research-candidate]", "[x]"))
        assert build_report(a)["verdict"] == "INVALID"
        # wrong git SHA is INVALID
        b = ns(run_dir=str(Path(td) / "better"), seed_lo=63000000, seed_count=128, block=8, git_sha="b" * 40)
        assert build_report(b)["verdict"] == "INVALID"
    print(json.dumps({k: [v["verdict"], v["primary_cand_minus_prod"]["win"], v["primary_cand_minus_prod"]["discordant"],
                          round(v["primary_cand_minus_prod"]["mcnemarP"], 5)] for k, v in results.items()}, indent=1))
    print("selftest OK")
    return 0


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    sub = p.add_subparsers(dest="cmd", required=True)
    for name in ("check", "analyze"):
        c = sub.add_parser(name)
        c.add_argument("run_dir")
        c.add_argument("--seed-lo", type=int, required=True)
        c.add_argument("--seed-count", type=int, required=True)
        c.add_argument("--git-sha", required=True)
        c.add_argument("--block", type=int, default=8)
        if name == "analyze":
            c.add_argument("--out", required=True, type=Path)
    sub.add_parser("selftest")
    a = p.parse_args()
    if a.cmd == "selftest":
        return selftest()
    if a.cmd == "check":
        return cmd_check(a)
    if a.out.exists():
        raise SystemExit(f"{a.out} exists")
    rep = build_report(a)
    a.out.open("x").write(json.dumps(rep, indent=1, sort_keys=True) + "\n")
    pr = rep["primary_cand_minus_prod"]
    print(json.dumps({"verdict": rep["verdict"], "flags": rep["flags"], "pairs": pr["pairs"],
                      "winRate_cand_prod": pr["winRate"], "win": pr["win"], "discordant": pr["discordant"],
                      "mcnemarP": pr["mcnemarP"], "bossDeaths_cand_prod": pr["bossDeaths"],
                      "integrityErrors": rep["integrityErrors"][:20]}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
LIVE_AB_PY
sha256sum $LAB/live_ab_analyze.py        # expect 510ccf0dbb35c8caeb1203526a9e4aa8f41d29975eeb392d1e2731d9534d8d3c
python3 -I $LAB/live_ab_analyze.py selftest | tail -1      # expect: selftest OK
```

### 7.3 Freeze (before the smoke)

```sh
{ date -u +%FT%TZ; echo "worktree HEAD $(git rev-parse HEAD)  binary build $GITSHA  J=$J"
  sha256sum $LAB/bin/one_combat $LAB/cand/FAST-final.native $LAB/cand/STD1-escape.native $LAB/cand/candidate-v3.json \
    $LAB/arm_env.sh $LAB/run_unit.sh $LAB/launch.sh $LAB/units.txt \
    $LAB/live_ab_analyze.py
  python3 -I -c "import numpy, sys; print('python', sys.version.split()[0], 'numpy', numpy.__version__)"
} | tee $LAB/PREREG-FROZEN.txt
```
Changing any script, unit, constant or environment after this point voids the pre-registration.

### 7.4 Smoke (seed 63009000, all arms, ~3–5 min)

```sh
for a in prod cand off; do bash $LAB/run_unit.sh $WT $LAB $LAB/smoke $a 63009000 1 & done; wait
cat $LAB/smoke/*.done                                     # rc=0 for all three
for a in prod cand off; do
  python3 -I tools/agent/check_benchmark_canary.py --results $LAB/smoke/$a-63009000.csv \
    --meta $LAB/smoke/$a-63009000.csv.meta.json --log $LAB/smoke/$a-63009000.log --expect-backend native_silver \
    --expect-seeds 1 --expect-sims 10000 --expect-seed-lo 63009000 --expect-asc 0 --expect-threads 1 --expect-fair \
    --no-expect-searcher3 --expect-executable-sha $GITSHA --binary $LAB/bin/one_combat \
    --expect-binary-sha256 dddb09f099a3a88994b23178b96e70346ac877c4d4deaf2d786df184972c7169 || echo "CANARY FAIL $a"
done
python3 -I $LAB/live_ab_analyze.py check $LAB/smoke --seed-lo 63009000 --seed-count 1 --block 1 --git-sha $GITSHA \
  | tee $LAB/logs/smoke.check.txt                         # last block must be "integrityErrors": []
grep -h "ctm-research-candidate\|live OOC MCTS ON\|startup failure" $LAB/smoke/*.log
# projected cohort wall time in hours (one seed is noisy; recorded, not a gate):
python3 -I -c "import csv,sys;s={a:float(next(csv.DictReader(open(f'$LAB/smoke/{a}-63009000.csv')))['sec']) for a in ('prod','cand','off')};print(s,'projected_h',round(128*sum(s.values())/$J/3600,2))" \
  | tee -a $LAB/logs/smoke.check.txt
```
Stop and report on any canary failure, a nonempty `integrityErrors`, a startup failure, a missing
`[ctm-research-candidate] candidate_id=pathb-r2` line in the `cand` log, or the line in `prod`. Do not fix and rerun
under this plan. The smoke seed is not pooled.

### 7.5 Launch the cohort (detached)

```sh
setsid nohup bash $LAB/launch.sh $WT $LAB $J > $LAB/logs/launch.log 2>&1 < /dev/null &
```

### 7.6 Monitor and resume

```sh
ls $LAB/run/*.done 2>/dev/null | wc -l          # 48 when finished; then $LAB/run/DONE exists
grep -h "bestbench-seed-failure" $LAB/run/*.log # stalls are expected to be rare; any other message -> report
pgrep -af "bestbench 10000" | wc -l             # about J while running
```
After a reboot or a killed launcher, rerun the 7.5 command unchanged. Finished units are skipped. An interrupted unit
is moved to `run/aborted-<UTC>/` and rerun whole. Do not delete anything under `$LAB`.

### 7.7 Analyze and hand back

```sh
python3 -I $LAB/live_ab_analyze.py analyze $LAB/run --seed-lo 63000000 --seed-count 128 --git-sha $GITSHA \
  --out $LAB/report.json | tee $LAB/logs/report.summary.json
tar czf $WT/build/ctm-live-ab-20261009.tgz -C $WT/build --exclude=ctm-live-ab-20261009/bin \
  --exclude=ctm-live-ab-20261009/cand ctm-live-ab-20261009
sha256sum $WT/build/ctm-live-ab-20261009.tgz
```
Return the tarball (expected tens of MB, mostly traces) and its sha256. Report the summary block: `verdict`,
`flags`, `win`, `discordant`, `mcnemarP` and `bossDeaths`. The cloud thread unpacks it into
`/mnt/project-files/ctm-pathb/live-ab-20261009/`. It rechecks `PREREG-FROZEN.txt` and reruns `analyze` with the
share copy of the script; the bytes must be identical. Then it goes to independent review and records the ledger
entry.

## 8. Hazards

* **H1 Active Lizard with an override.** If `STS_OOC_MCTS_ACTIVE_LIZARD=1` is missing, the candidate silently runs
  without the Lizard correction (`ooc_mcts_adapter.cpp:1699`). `arm_env.sh` sets it, and the analysis requires
  `active_lizard_correction=1` in both banners.
* **H2 Relative paths.** The production CTM, the V4 net and the `v_win`/screen-leaf models load relative to the CWD.
  `run_unit.sh` changes to `$WT`. The candidate paths are absolute.
* **H3 Environment leaks.** Every unit runs under `env -i` with the full list in `arm_env.sh`. The candidate
  variables exist only in `cand`. A leaked candidate manifest would make `prod` print the candidate line; the
  analysis treats that as INVALID.
* **H4 Escapes are wins.** A Smoke Bomb escape ends a real fight as PLAYER_VICTORY (`BattleContext.cpp:2318-2330`).
  The run continues, without rewards. The trace has no escape bit, so escapes are inferred from the Smoke Bomb count.
  This is a diagnostic only.
* **H5 What a verdict means.** The comparison is OOC MCTS with one CTM against OOC MCTS with another. Production
  play has MCTS off. Even `CANDIDATE_BETTER` does not change default play; `cand − off` and a separate confirmation
  decide that.
* **H6 Sample size.** n = 128 resolves only differences of about ±10 pp (section 3). This A/B cannot detect the
  offline HP-NLL gain (mostly a teacher shift, review note 1) unless it moves wins by that much.
* **H7 Time-dependence.** No setting here is time-based: Silver budgets are simulation counts, and MCTS early stop is
  visit-based. So a shared, busy machine changes `sec` but not outcomes. **Inference**, from §384's order-independence
  claim.
* **H8 `bestbench` refuses a CSV that already contains a requested seed.** This is why `run_unit.sh` moves interrupted
  units aside instead of appending.

## 9. Open questions (owner, before 7.3)

1. **The `off` reference arm** (+2.05 CPU-h, about +15 min wall). Keep it, as recommended, or drop it, which removes
   the `off` lines from `units.txt` and makes section 5 item 6 not applicable?
2. **Decision thresholds.** α = 0.05 with CI/McNemar concordance; the non-inferiority sub-flag at −10 pp; the
   PROVISIONAL limit of 6 dropped pairs. Change these only before 7.3.
3. **Pre-registration commit.** Should this file and `live_ab_analyze.py` be committed to
   `claude/new-ctm-stack-8h7edy` (evidence dir `docs/experiments/evidence/ctm_live_ab_418_20261009/`) before the smoke,
   as the offline runbook was (`72ebd7d1`)? Should a short independent pre-run review take place, as for §384?
4. **Machine availability.** Are 10 cores free for about 1.5 h? With fewer, set `J` before 7.3. J does not affect
   results, only wall time.
5. **Follow-up on a positive `cand − off`.** Is an OOC-MCTS-on confirmation the next step, or the production-pin
   swap PR first?
