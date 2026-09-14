# Full-budget hypothetical OOC root-lock observations

Baseline/current main `5b2a5b51fcbce2ced657281dbb3ac9c6795833c2` includes merged
PRs #183/#184 and #182. Measured/self-inspected implementation:
`b50b1c7a164b8f53016b47f5ff1d3a4b318a3b81`. These measurements describe the observer-only revision; subsequent live-stop
enablement is recorded separately in `ooc_early_stop_enabled_2026-09-15.md`.

## Safety and implementation

PR #182 qualifies a near-full, deliberately restricted V2 artifact. Its final
support is505,935/510,030(99.197106%), excluding initial Smoke Bomb,
pre-smokeBombUsed, and Writhing/Ritual intersection. Brew-generated escape
remains modeled. This is not complete combat support. Independently,
continuation step limits and forbidden imagined native-combat paths can still
throw. Live `searchGuaranteedNonAborting()` therefore stays false. No
support/model/schema/RNG/default change or early-stop enablement was made in
the measured observer-only revision.

`OocMctsConfig::observeRootLock` records the first completed simulation where
PR #183's strict visit-lock predicate holds. The remaining budget assumes all
requested simulations can complete; visit ties that could change final Q choice
are not locked. Mean-Q observation is inapplicable. A sole root locks after one
simulation; a final-simulation lock records zero remaining work. Observation
forces the full requested budget, suppressing both visit stops and qualified
sole-root bypasses. It consumes no additional model/sampling draws. It records
the action, remaining simulations and measured wall suffix until loop completion
or abort. A later support abort still invalidates the whole root.

Live `STS_OOC_MCTS_ROOT_LOCK_TRACE=<fresh.jsonl>` opts in. One record per actually
searched root includes seed/decision/floor/screen, requested/completed/attempted
budget, full-budget completion, first lock/action/remaining/suffix, final action,
abort/reason, provider guarantee and actual saved/stop metrics. Roots declined
before search have no record. Existing completed-run CSV columns are unchanged.
The caller checks a completed locked action equals the full-budget final action.
Only fully completed roots enter conditional opportunity sums; aborted locks
are reported separately and receive no safely enabled savings.

## Evidence inventory and pilot design

Prior #184 timing packets have aggregate seed42 counters and a V1 model;
#182's qualification receipts prove the selected support/native cohort but have
no MCTS allocation history. Active parameter-search local exports belong to
another task and have no qualifying earliest-lock stream. None can replace this
observation. Their known configuration/support evidence is reused. No remote
cohort is needed/launched. The full inventory is preserved in the raw packet.

Smallest descriptive engineering pilot: one common seed42, observation OFF/ON,
same committed Release executable and tracked V2 artifact
`selfplay/models/combat_transition_near_full_except_smoke_v2.native` SHA256
`22c855e0667a58a73835505672b0ae6d03f12e9fb8d64f08893810199246e94e`.
IroncladA0/OOC512/exact10,000Silver, fair combat/copied noncombat RNG,
keysOFF, Act3-or-death, OMP1/CPU0, sequential. Default PUCT1.5/PW2,.5/depth32,
policy priors/temperature1, native resolved leaf values, V4 continuation,
visits root selection. Both guarded commands exit0. No training, tuning,
support expansion, multi-seed quality run or enabled-early-stop timing trial.

## Results

| Full-budget observed measurement | Value |
| --- | ---: |
| Actual searched/completed roots | 155/155 |
| Completed roots with hypothetical locks | 155 |
| First-lock simulation, min/median/max | 1/260/509 |
| First-simulation (sole-root) locks | 34 |
| Completed requested simulations | 79,360 |
| Remaining simulations after first locks | 40,186 (50.64%) |
| Measured sum of completed-root wall suffixes | 5.258686s |
| Observed total OOC MCTS wall time | 13.471238s |
| Conditional suffix / OOC time | 39.04% |
| Conditional suffix / full-run time41.7506s | 12.60% |
| Aborted roots / locked-then-aborted roots | 0/0 |
| Live providers qualifying safe enablement | 0 |
| Actual saved simulations / locked-root stops | 0/0 |

This is potential loop work under a future proven non-aborting contract, not
an achieved runtime reduction. Sole zero-simulation bypass could additionally
avoid its first simulation/setup, which this conservative first-lock estimate
does not include. Individual hypothetical suffix times are measured rather than
assuming equal cost per simulation. One seed and ordered runs do not establish
average savings; timing/configuration effects apply. Zero observed aborts do
not qualify the provider or excluded states.

OFF/ON outcomes, every non-timing OOC counter,26complete Silver telemetry lines
and support-reason JSON match. Both clear Act3 at floor51/hp16/maxHp85.
188OOC decisions include155owned/33fallback,79,360simulations/attempts,
5,735surrogate draws,0support/continuation aborts. Both stop/bypass/saved metrics
remain0. Full-run OFF42.4135s, ON41.7506s; OOC OFF13.520921s, ON13.471238s.
These are observation overhead/context checks, not early-stop timing evidence.
No complete per-action/full-state full-run trace was collected; aggregate
matching is narrower than full trajectory/RNG parity.

## Verification

- Worktree preflight/check passed, pinned dependencies preserved. Local `main`
  fast-forwarded fromc352286 to5b2a5b5; active canonical parameter-search branch
  and its untracked evidence preserved. This task uses a separate app worktree.
- Release one_combat/ooc-mcts-test and complete default Debug target set: build exit0.
- Complete Debug CTest rerun:101/101pass; focused Release rerun:7/7pass.
- Core tests prove exact52/100first strict lock, full-budget visits/Q preservation,
  identical complete sampling draws/particle results, inapplicable mean-Q,
  zero-budget-tail final lock, and lock-at1then-abort-at7 returning no winner/
  no actual saved simulations. Existing unsafe Wheel/fallback RNG regression passes.
- First Debug run: four tests fail importing Torch in analysis-only virtualenv.
  Rerun with existing systemPython3/Torch2.5.1+cu121 fixes all; no dependencies
  altered or GPU used. First Release artifact test lacks probe; build
  combat_transition_runtime_probe and rerun fixes it. Raw failures retained.
- Both full-run receipts/CSV/meta/log/support and155root records retained,
  with source/binary/model hashes and exact guarded commands.
- `git diff --check`, committed-range inspection and final packet reconciliation: pass.

Independent implementation review, exhaustive all-path support proof, repeated/
multi-seed opportunity measurement and early-stopped timing not run. Linux GCC
CI is authoritative on the draft PR; no automatic merge. Knowledge impact:
maintained observer/safety interface and environment variable plus §259 engineering
evidence. No default or scientific deployment qualification change.
[Full raw packet](ooc_root_lock_observation_2026-09-15.json).
