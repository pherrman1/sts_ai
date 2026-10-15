# Bounded grouped OOC MCTS parameter search

User authorized sensible grouped parameter search,32 seeds per configuration.
Baseline f8279e4dfc075e83ca6f167f41b7103635c7dd4f, preceding fresh64 gate:
V448/64 versus fixed10000 MCTS42/64,paired CI[-23.4375,+4.6875]pp, inconclusive;
mean elapsed ratio4.50565. New hypothesis: prior/exploration mismatch, excessive
chance breadth, or native leaf/continuation bias can dominate extra iterations.
Alternative: frozen transition/support/hidden RNG limitations dominate regardless
of tuning. This search tests grouped policy choices, without model/support changes.

## Design fixed before outcomes

17 screening configurations at2048 simulations unless budget is the intervention:
reference; uniform priors c1.5; uniform c3; policy T0.5/c0.5; policy T2/c3;
policy c0; widening k1/alpha0.25; k4/alpha0.75; depth8; depth16;
constant0.5 checkpoint leaf; one-combat V4 leaf rollout; three-combat V4 leaf
rollout; one-combat uniform leaf policy; root-mean-Q selection; budget512;
budget10000. Other reference settings: policyT1,c1.5,k2,alpha0.5,depth32,
next-map native v_win checkpoint leaf,V4 continuation,root-most-visits.
Uniform prior preserves all candidates and PUCT exploration. Constant leaf is
an ablation of learned v_win at resolved checkpoints; exact terminal0/1 retained.
No direct native value on unresolved/pending states and no imagined Silver.
Leaf rollout1/3 continues across that many additional surrogate combats, then
resolves noncombat choices to a map checkpoint; global continuation-step bound
1024; unresolved bound exhaustion and unsupported combat abort the complete
root to V4, never native-valuing an unresolved state. Uniform continuation applies only
to unique supported V4 action candidates; other selectors retain existing V4.

Discovery: exactly12000000..12000031 common to all17 configurations and V4. Excluded
canary11999999 once per unique configuration before official use. Prospectively
inventory preserved local/remote qualified gameplay CSVs for discovery/canary
and confirmation12001000..12001031 plus canary12001999. Existing980000 cohorts are prior evidence;
wrong seed regime for this discovery. Both control and reference are collected
under the same newly reviewed executable; no false executable-SHA override.
Frozen real fair exact10000 Silver,A0,keysOFF,Act3 stop; same five model hashes,
full V4 stack,PUCT and widening controls restricted to detached OOC search.
No training/corpus collection, model/schema/support changes or default enabling.

Rank discovery configurations by wins descending,mean final floor descending,
mean elapsed seconds ascending,then stable configID ascending. Family winners:
prior/exploration(reference+5),widening(reference+2),leaf/depth(reference+6),
root selection(reference+1). Composition maps fields exclusively: prior family
prior/temperature/cPuct; widening family k/alpha; leaf/depth family depth/value/
combats/continuationPolicy; root family selection rule. Stable IDs and full
profiles are frozen in search-plan.json before outcomes. Compose their settings and test512/2048/10000 on
same32 seeds, up to3 additional configurations; exact duplicate settings reuse
existing qualifying32 rows rather than rerun. Select highest-ranked evaluated
configuration. Screening intervals are descriptive, selection-biased and not
qualification. Do not adapt these levels, seed count or rule to outcomes.

One selected configuration versus V4 then runs on fresh confirmation12001000..
12001031,32 per arm, without further tuning. Canary12001999 excluded per final arm.
Primary holdout rule: paired200000 PCG64(20260914)95% percentile win-difference
CI strictly above0 UP,strictly below0 DOWN,otherwise INCONCLUSIVE; missing total
owned/surrogate coverage NO_SEARCH_COVERAGE. No confirmation peeking/reselection,
extra seeds or follow-up escalation. Discovery maximum20 configs plus V4;
confirmation2 arms:maximum736 official games, plus excluded canaries.

Designated GCP sts-test24CPUs/24OMPworkers; sequential arms, guarded launcher,
exact source/cache/binary/model binding, run freshness, per-arm full config
receipts. Independent implementation/design review then freeze SHA before
expensive games. Canaries prove activated knobs and unchanged model-load/bridge
contracts. Per-arm exact membership; completed=budget*owned+discarded,
attempts=completed+aborts,discarded<=aborts*(budget-1),reasons reconcile,
imagined=surrogates+actual unsupported combats; continuation-limit aborts have
a separate counter/reason map, rootaborts=unsupported+continuationLimitAborts;zero bridge failures/battleLeaves. Independent
final ranking/composition/holdout bootstrap reproduction. Preserve raw results,
source/model hashes and resource/progress; restore initial stopped VM afterwards.

Knowledge impact: stable opt-in controls in maintained architecture/evaluation
KB; experiment evidence and current research status. New opt-in knobs do not
alter OFF or normal defaultON search behavior; unresolved continuation-bound
failures now fall back per root instead of terminating with a fatal error. Root selection, leaf0.5 and uniform continuation
are algorithm ablations, not fidelity or unbiased-planning qualification.

Prospective freshness preflight rejected original discovery990000..990031 because
a preserved remote smoke record contains990001. No study outcomes were collected
or inspected. Revised ranges above are chosen before outcomes and re-inventoried;
the rejected census remains preserved as a preflight receipt.
