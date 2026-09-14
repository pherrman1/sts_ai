# Corrected live OOC MCTS paired Silver regression benchmark

The user authorized four corrections after the original §243 negative gate:
resolve pending leaf contents before native win evaluation, fail unsupported
imagined combat back to V4 for the entire OOC decision, align both real-combat
arms to the corpus ordinary exact-10k
Silver policy, and deepen deterministic transitions with a fixed 512-simulation
MCTS budget. See the maintained [OOC contract](../../knowledge-base/architecture/out-of-combat.md).
Knowledge impact: updated live continuation, combat-policy prerequisites and
search/coverage telemetry contracts; unchanged models, support envelope and
OFF default. This bundles four corrections and cannot attribute effects to one.

Hypothesis: the corrected opt-in OOC policy improves Act-3 wins over the existing
V4 OOC stack when both arms use ordinary exact-10k Silver. Control is MCTS OFF;
treatment is corrected MCTS ON at 512, PUCT 1.5, stochastic widening k=2 and
alpha=0.5, depth32. Both use the same frozen executable and model hashes,
A0, four OpenMP workers, keys OFF and Act-3 stop. Only detached imagination uses
the combat surrogate; unsupported imagined combat abandons the entire root
and uses V4.
No native/Silver combat executes in imagination; partial root action statistics
are discarded and attempted/completed work plus support reasons are recorded.
The original combat-transition artifact and tracked V4/floor/win/combat-policy
models remain frozen; no regeneration, training or support expansion.

Evidence inventory: preserved §243 raw paired32 outputs have the correct seeds
and artifacts but real combat 1k, MCTS128 and the old leaf/unsupported contracts.
They cannot answer this corrected configuration. The user explicitly requires
**the same seeds 970000..970031**, so this is a paired regression comparison,
not fresh confirmation. Excluded 969992..969999 are implementation smoke/parity
seeds. No additional decision-bearing seeds or sweep are authorized.

The decision rule remains the paired seed bootstrap 95% CI on treatment-minus-
control won: strictly positive → OOC_MCTS_WINRATE_UP; strictly negative → DOWN;
otherwise INCONCLUSIVE. If the treatment has no completed MCTS-owned decision
or no surrogate imagination, report OOC_MCTS_NO_SEARCH_COVERAGE and retain paired
outcomes as descriptive only. This coverage failure rule is frozen before seeds.
Use 200,000 paired resamples, NumPy PCG64 seed20260914,
linear percentile quantiles. Discordant exact two-sided binomial p and secondary
floor/HP/fights/death/runtime metrics are descriptive. Support reasons must sum
to unsupported imagined combats; supported plus unsupported must equal all
imagined combats. Ownership/simulations, effective actual backend and real combat
counts must reconcile. Depth includes searched primitive edges, excluding leaf
projection policy steps. This remains an engineering policy A/B under copied
hidden native RNG; no unbiased stochastic-planning or deployment qualification.

Implementation baseline: `916a3d35ff33bd3992de38f1540049838cb55d80`.
The initial implementation ec76e49 used detached10k Silver for unsupported
imagination. The user rejected that cost and selected whole-decision V4 fallback
before any revised decision-bearing seed launched. Its excluded969992 full-game
canary was stopped incomplete after minutes of CPU; this is not a smoke pass.
The briefly started designated24vCPU VM had no benchmark launched and was returned
to its initially stopped state. The final run remains local with four workers.

**OOC_MCTS_WINRATE_INCONCLUSIVE.** Both arms won 21/32 (65.625%); paired win
change 0pp, bootstrap 95% CI [-21.875,+21.875]pp. Six treatment-only wins and six
control-only wins; 20 same-result seeds. Exact discordant p=1 descriptive.
Mean floor 48.625 → 49.0625 (delta .4375, CI [-2.34375,3.1875]); mean HP end
40.6875 → 28.71875 (delta -11.96875, CI [-29.09375,5.21875]). These are secondary.
Mean per-game elapsed time 38.2206875 → 61.072265625 seconds, ratio 1.5978851x;
MCTS accounts for 57.8583% of treatment game wall time. Arms ran sequentially,
each with four workers; per-game timings include contention among those workers.

Final reviewed/frozen source `f9af4ad6055b98603fd732d59869b5b39cc8beec`, binary
SHA256 `0ad6c27b7a9a8faa131bb526ace5f875cb4463842df50aba5baec0f67f621f73`.
[Freeze and smoke/source binding](live_ooc_mcts_corrected_2026-09-14/freeze.json).
The deliberate all-zero prefreeze smoke metadata is preserved: final build
completed before smokes, tested source was committed unchanged as the frozen SHA,
and the same binary was used for both official arms with the proper SHA stamp.
Independent implementation review passed, focused CTests 3/3, qualified startup
11/11, OFF exact non-timing parity 8/8 against preserved `916a3d35` at 10k Silver,
and ON smoke 8/8. [Authoritative Linux GCC CI passed](https://github.com/pherrman1/sts_ai/actions/runs/34830645555)
before any official seed. No official seeds were restarted or omitted. An analysis
attempt before the last game completed correctly failed exact-32 membership;
only the completed outputs passed validation and entered this result. Final independent
evidence review reproduced the bootstrap/result exactly and passed all provenance,
configuration and accounting checks; [review record](live_ooc_mcts_corrected_2026-09-14/independent-review.json).

Final treatment: 3,654 owned decisions / 5,796 OOC decisions; 2,142 fallbacks
(36.9565%), including 972 unsupported-combat root aborts. 105,957 supported
surrogate samples plus 972 unsupported = 106,929 imagined combats. All support
reasons reconcile. 41,912 completed simulations from aborted roots were discarded;
1,912,760 completed simulations = 3,654×512 + 41,912; 1,913,732 attempts include
972 aborted attempts. No unresolved BATTLE was native-leaf-valued. Search maximum
depth distribution: 6:2, 7:3, 8:1, 9:5, 10:7, 11:8, 12:3, 13:3. Deterministic
reuse plus the fixed increased budget removed the observed depth-3 ceiling.
Supported-sample coverage is sufficient for the frozen primary rule; the small
unsupported fraction of imagined samples does not mean few root decisions abort.

Control 823 / treatment 811 actual combats, all ordinary exact-10k Silver;
Silver logs match the completed-run counters and all conversion, semantic,
transaction and knowledge failure counters are zero. Models/hashes are unchanged.
[Raw analysis](live_ooc_mcts_corrected_2026-09-14/result.json),
[control validation](live_ooc_mcts_corrected_2026-09-14/control-validation.json),
[treatment validation](live_ooc_mcts_corrected_2026-09-14/treatment-validation.json),
[raw files and checksums](live_ooc_mcts_corrected_2026-09-14/SHA256SUMS).
Reproduction: invoke archived `run_arm.py` through its seed guard, control then
treatment with count32/offset970000; analyze with `tools/analyze_ooc_mcts_gameplay.py
CONTROL TREATMENT OUTPUT --combat-sims 10000 --mcts-sims 512`. Do not replay these
seeds without authorization; reproduction instructions are provenance.

The corrected policy no longer shows the original large negative point estimate,
but this A/B does not demonstrate an improvement or equivalence. Keep MCTS OFF
by default and return this frozen evidence for review. Same seeds and four bundled
corrections prevent fresh-confirmation or single-mechanism causal claims. No
additional runs, tuning or deployment were performed.
