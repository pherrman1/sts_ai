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
