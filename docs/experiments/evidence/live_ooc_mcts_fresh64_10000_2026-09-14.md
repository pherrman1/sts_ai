# Fresh 64-seed live OOC MCTS versus V4 gate

## Frozen design before outcomes

User authorized a fresh 64-seed paired MCTS-versus-V4 gate with 10,000 MCTS
simulations. Hypothesis: the fixed-10000 MCTS policy improves Act-3 win rate over
V4 with mechanically and compositionally qualified expanded combat support.
More search could also encounter more unsupported imagined states and cause more
whole-root V4 fallbacks; diagnostic accuracy does not guarantee better gameplay.
The primary contrast is this new MCTS policy versus matched V4, not a causal
budget comparison against the historical reused-seed 512/2048 cohorts.

Baseline and exact remote runtime source:
`54f2820f426c45540b02eb075cf73102b00de8f0`, with passed Linux GCC CI and the
preceding independently reviewed expanded-composition qualification.
No C++ runtime paths differ from reviewed integration `0757c2db...`.
Remote older executable inventories do not satisfy corrected runtime provenance;
a new exact-source worktree/cache/build is required. The analysis implementation
SHA and exact binary/model hashes are frozen separately before official games.

Both arms use ordinary fair exact-10k Silver combat, A0, keys OFF, Act-3 stop,
full frozen V4 strategic/native floor/win/policy stack. Treatment uses fixed
10,000 OOC MCTS simulations, PUCT1.5, widening k2/alpha.5, depth32, checkpoint
leaves and the same frozen native combat transition model. Unsupported imagination
aborts the complete root to V4. No imagined Silver or unresolved battle leaf.
Copied hidden noncombat RNG remains a planning limitation.

Official seeds are exactly **980000..980063**, paired in both arms. Excluded
canary **979999** is run once per arm before official seeds. Local and remote
preserved gameplay CSV inventories must prove no seed collision. Prior970000..
970031 evidence is reused regression evidence and does not satisfy this fresh
cohort or fixed10000 treatment, so both fresh arms must collect new outcomes.
No old control rows are pooled. No tuning, model/support changes, extra official
seeds, repeated official seeds, data collection, budget sweep or default changes.

Designated GCP research host `sts-test`,24 CPUs; both arms use24 OMP workers,
execute sequentially within one experiment window, and record actual resource
use and progress. All gameplay commands use the repository launcher and seed
run guard in GCP research mode. Official128 games plus2 excluded canaries exceed
the local128 ceiling, so no local game seeds are driven.

Primary rule is unchanged: paired200,000-resample NumPy PCG64 seed20260914
percentile95% CI for MCTS-minus-V4 win rate. Strictly positive lower bound yields
`OOC_MCTS_WINRATE_UP`; strictly negative upper bound yields
`OOC_MCTS_WINRATE_DOWN`; otherwise `OOC_MCTS_WINRATE_INCONCLUSIVE`.
No aggregate ownership or combat-surrogate coverage yields
`OOC_MCTS_NO_SEARCH_COVERAGE`. Exact discordant binomial p is descriptive.
Secondary floor/death/HP/runtime, support aborts/fallback, samples and depth
telemetry are descriptive. No follow-up escalation based on outcomes.

Before official games: independent design/implementation review; focused analyzer
and runtime tests; source/build/model hashes and CMake source binding; both fresh
excluded canaries and independent readiness validation. Freeze reviewed analysis
SHA before the expensive run. Require complete exact seed membership, matching
source/config/backend, zero bridge failures and battleLeaves, support reason
counts, completed=10000*owned+discarded, attempts=completed+aborts,
discarded<=9999*aborts and imaginedCombats=surrogateSamples+unsupportedCombats.
Final raw outcomes and bootstrap/accounting receive independent reproduction.

Knowledge impact: experimental evidence/current research status; stable analyzer
cohort parameters are routed to the evaluation protocol. #174/#178/#179 and the
historical gameplay packets remain preserved. Results are appended after the
frozen run; a positive engineering gate does not automatically enable MCTS.

## Readiness receipts

The new exact54f GCP Release build passed `ooc_mcts` and
`combat_transition_runtime_loader` (2/2,0.06s). Remote census inspected659
preserved gameplay CSV records with no overlap or errors; local census likewise
found no overlap. `exact-sha-preflight` passed source, clean tracked checkout,
CMake source binding and six file hashes. Binary SHA256 is
`810281cbf8531dc18aa95cd7c3ce839ad7b337722d7b316bfd189023f3485639`.
The frozen manifests contain every model path/hash.

The native manifest has no cwd field. The scoped `launch_arm.py` renders the
manifest through the unchanged repository `remote_run`, retaining active-job
and output-freshness checks, with GNU `env --chdir` to the exact checkout and
absolute executable/result paths. The designated GCP guard checks host/root and
all seed argv before env changes the actual process cwd. This is necessary for
native relative floor/policy model loads. GIT_DIR/GIT_WORK_TREE identify the
linked checkout; no fake PWD is used. Independent guard-only64 passed and129
was rejected locally, without executing games. Frozen rendered receipts record
actual argv and cwd. No launcher or runtime source changes.

Independent analyzer/prereg review passed; historical32 result is reproduced
exactly and64 membership/accounting corruption tests passed (2tests). Focused
CTest passed1/1; repository health passed with no warnings. Source CI provenance
remains the prior Linux GCC success; the new analyzer/helper change receives
its own draft-PR CI after outcome recording.

Both excluded979999 canaries completed once. Native benchmark canary checks and
strict root/support validators pass: control32real combats,41.2202s; treatment
47owned decisions,105support aborts,7143surrogate samples,30real combats,
maxdepth12,92.6452s. Every bridge failure and battleLeaves is zero. Successful
strategic/floor/win/policy load messages appear in both logs; treatment startup
confirms native combat model and sims10000. These outcomes are excluded from
official analysis. Reviewed analyzer/launch SHA is
`13508a4507daebc1fe081151973050a51d8aef9d`.
Independent excluded-canary readiness passed with raw configuration, model-load,
source/hash, accounting, zero failures and positive treatment coverage checks.
Official V4 launched first (remote PID5517); MCTS is queued to follow only after
its completion. Official outcome files remain separate from canaries.

## Completed official result

**`OOC_MCTS_WINRATE_INCONCLUSIVE`**. Both arms completed exactly64 fresh paired
seeds980000..980063 once, excluding both979999 canaries. V448/64 (75%) versus
MCTS42/64 (65.625%): MCTS-minus-V4−9.375pp; paired95% bootstrap CI
**[−23.4375,+4.6875]pp**. Eight treatment-only wins and14 control-only wins;
42same-result pairs. Descriptive exact two-sided discordant binomial p
0.28627872467041016. Primary rule/200000 PCG64(20260914) resamples are unchanged.
The negative point estimate does not meet the DOWN gate because its interval
includes zero; there is no demonstrated improvement at this fixed10000 setting.

| Descriptive outcome | V4 | MCTS10000 | Paired difference95% CI |
|---|---:|---:|---:|
| Mean floor |48.765625|46.921875|−1.84375 [−4.390625,+0.53125]|
| Mean ending HP |41.109375|40.296875|−0.8125 [−12.15625,+10.109375]|
| Mean elapsed game seconds |101.381390625|456.7887890625|+355.4073984375 [305.96287140625,407.27075296875]|
| Real Silver combats |1633|1564|descriptive counts|

Mean elapsed game time ratio4.5056473; whole-arm wall328.8s versus1648.9s.
These are descriptive sequential24-worker cohort timings, not a causal budget
comparison against previous differently configured/reused-seed runs. MCTS
instrumented wall averaged407.3788s,89.1832% of treatment game elapsed time.
Observed full-batch CPU use≈24cores and peak observed RSS≈6GB; utilization
naturally tapered with the final games. Arms did not overlap.

Treatment10898 OOC decisions:7240 MCTS-owned and3658 V4 fallbacks (33.5658%).
1551 fallbacks were support-triggered whole-root aborts. Completed simulations
73686339=7240×10000+1286339 discarded; attempts73687890=completed+1551.
Imagined combats1447062=1445511 surrogate samples+1551 unsupported calls.
Maxdepth6..23; all battleLeaves zero. Both full-arm native benchmark checks and
strict source/config/seed/trace/support validators pass; all four Silver bridge
failure counters are zero and log-line counts exactly match real combats.
Postflight again passes exact source/cache/binary/five-model hashes.

Support-abort reasons (sum1551): gold-mutating encounter366, potion250,
pre-stolen gold155, Writhing Mass200, Entropic Brew30, gold-mutating relic227,
card264, Smoke Bomb25, Ritual Dagger34. Frozen exclusions remain exclusions;
no support broadening, tuning, training, follow-up seeds or default enablement.
Native MCTS default OFF and existing512 setting are preserved.

Independent final raw-outcome/interval/accounting reproduction **PASS** is recorded
in `final-independent-review.json`: all six means/CIs reproduce exactly, with
zero reviewer gameplay. Analyzer/launch reviewed SHA
13508a4507daebc1fe081151973050a51d8aef9d remains frozen; results only append
evidence. Source CI passed at54f; new analyzer/readiness CI Linux GCC passed
run34860408603 (3m9s). Final evidence head receives its own CI.

ELI5: On these64 new games the larger-search policy won six fewer games than
V4 and took considerably longer. The uncertainty interval crosses zero, so this
gate is inconclusive and provides no basis to enable MCTS. This is real-game
engineering policy evidence with copied hidden noncombat RNG, not an unbiased
planning-value or deployment qualification. The offline composition prerequisite
passed separately in #179; its qualification is not a gameplay win claim.

Raw outcomes/configs/meta/trace/support, gzip logs, execution receipts, resource
snapshots, hashes, analysis and review receipts are preserved in the adjacent
packet. `README.md` gives the seed-free reproduction command. Original working
artifacts remain ignored under build/ooc-mcts-fresh64-10000; remote raw results
and source cache remain preserved. Knowledge impact: experiment evidence/current
research status plus explicit analyzer cohort parameters in benchmark protocol.
