# Live OOC MCTS expanded-support paired regression

Hypothesis: the broader consumption-only combat support predicate from merged
PR #178 improves corrected MCTS coverage and gameplay compared with V4 on the
user-requested same 32 seeds970000..970031. Both arms use the combined source,
ordinary fair exact-10k Silver, fixed512 MCTS, PUCT1.5, widening k2/alpha.5,
horizon32, A0, keys OFF, Act-3 stop, V4 full native stack and four workers.
Unsupported imagination aborts the entire root to V4; no imagined Silver.

Local main was fast-forwarded to `0a8f3ed1a5cd0ad0ce40d3a27f25ab1de4ff6eed`.
PR #177 is still draft, so this experiment uses a separate integration branch
combining that main with the reviewed corrected MCTS/evidence commit
`72b2b6428ebd53adc973fd68891e7c6ff99daf82`. No draft PR was merged to main.
PR #176's Silver semantic fix is also in main. The current-control/current-MCTS
A/B is valid with matched source; cross-run changes cannot be assigned solely
to the support predicate because the real combat implementation also changed.
Models/corpus remain fixed. Recovered support has census/contract validation,
but no fresh distribution-accuracy qualification; gameplay is tested here.

Preserved original1k/128 evidence and corrected10k/512 21-vs21 evidence do not
satisfy this source/support configuration. They remain historical comparisons.
No existing same-source gameplay evidence was found. Both arms must run anew;
no seed outcome is used twice in the new paired analysis. Same seeds are reused
regression evidence, not fresh prospective confirmation. No tuning, training,
new seed cohort or support expansion beyond merged #178.

Before official seeds: affected core/adapter/support checks, one excluded canary
per arm, independent integration review and fixed source/binary/model hashes.
Decision rule unchanged: paired200000 PCG64 seed20260914 bootstrap95% win CI,
strictly positive UP, strictly negative DOWN, otherwise INCONCLUSIVE. No search
ownership or surrogate coverage yields NO_SEARCH_COVERAGE. Secondary runtime,
floor/death/HP, root-abort and sample-support telemetry are descriptive. Validate
exact seed membership, source/config parity, support/attempt/discard counts,
actual Silver combat logs and zero bridge failures. MCTS stays OFF by default.
Copied hidden noncombat RNG remains a planning limitation. Local official runs64
plus2 excluded canaries remain below128. Ledger integration preserves original
§243/§244 and renumbers the colliding support census as §245.

Knowledge impact: integration and experimental evidence; support and MCTS
contracts are unchanged from their already maintained sources. Final results and current research status are recorded below.


**OOC_MCTS_WINRATE_INCONCLUSIVE.** Current control21/32 (65.625%) versus MCTS
22/32 (68.75%). Paired win gain3.125pp, bootstrap95% CI[-18.75,+25]pp;7 treatment-
only and6 control-only wins,19 same-result seeds; exact discordant p=1 descriptive.
Mean floor48.625→47.9375, delta-.6875 CI[-4,2.5]; HP end40.6875→32.9375,
delta-7.75 CI[-24.40625,9.375]. All secondary metrics are descriptive.
Mean game time26.110478125→70.478065625s, ratio2.6992254x. MCTS mean44.1028873s,
62.5768% of treatment game wall time. Both arms ran sequentially with four workers;
per-game durations include worker contention. Runtime across different historical
run conditions is not an isolated performance comparison.

Source integration/freeze `0757c2db918b6395d8f22ca54f6d94c8e3ae0b10`, binary
SHA256 `810281cbf8531dc18aa95cd7c3ce839ad7b337722d7b316bfd189023f3485639`.
[Freeze/model hashes](live_ooc_mcts_expanded_support_2026-09-14/freeze.json).
Build/support32 tests/focused3 CTests pass; both excluded969999 canaries pass,
with26 real Silver combats each, ON130 owned/14 aborts/4056 surrogate samples,
maxdepth16. Independent integration/readiness review passed before official
seeds. [Linux GCC CI passed on this exact source](https://github.com/pherrman1/sts_ai/actions/runs/34841844870).
No official seed was restarted, omitted or substituted. All64 official runs
passed source/config/seedset/accounting/backend validators; both arms identify
that source and actual ordinary fair exact-10k Silver.

Treatment4,060 owned /5,621 decisions (72.2291%);1,561 fallbacks (27.7709%),
including465 unsupported-combat root aborts. 135,119 supported surrogate samples
plus465 unsupported =135,584 imagined combats. 2,099,359 completed simulations
=4,060×512+20,639 discarded from aborted roots;2,099,824 attempts add465 aborted
attempts. Reasons reconcile; no unresolved BATTLE was native-leaf-valued. Maximum
depths8–14:8:1,9:4,10:8,11:11,12:3,13:4,14:1. Control823/treatment807 real combats;
Silver logs reconcile exactly and all recorded bridge failure counters are zero.

Compared descriptively with §244: owned decisions3,654→4,060, total fallback
36.9565%→27.7709%, support aborts972→465, surrogate samples105,957→135,119 and
MCTS wins21→22. This demonstrates more completed search under the broader gate,
but neither improvement nor equivalence in win rate. Both controls won21/32;
the current-source matched A/B is the primary result. Independent audit confirmed
32/32 exact prior-control parity for non-timing fields; that does not establish
general causal neutrality of the Silver fix. Final independent evidence review
reproduced the bootstrap and all source/binary/model/configuration/accounting
checks: [review record](live_ooc_mcts_expanded_support_2026-09-14/independent-review.json). Cross-run real combat,
state trajectories and runtime conditions prevent isolating the predicate's
causal effect. Same reused seeds are regression evidence, not fresh confirmation.
Recovered support retains the explicit accuracy/simulator-fidelity limitations
of #178. Keep MCTS OFF by default; no new seeds, tuning, model changes or deployment.

[Raw paired result](live_ooc_mcts_expanded_support_2026-09-14/result.json),
[control validation](live_ooc_mcts_expanded_support_2026-09-14/control-validation.json),
[treatment validation](live_ooc_mcts_expanded_support_2026-09-14/treatment-validation.json),
[raw checksums](live_ooc_mcts_expanded_support_2026-09-14/SHA256SUMS).
Commands are in archived `run_arm.py`/configs (seed guard, count32 offset970000).
Seed-free reproduction: `tools/analyze_ooc_mcts_gameplay.py CONTROL TREATMENT
OUTPUT --combat-sims 10000 --mcts-sims 512`. Do not replay gameplay without new
authorization. Local main remains the merged upstream #178; the integration and
raw result are handed off through draft #177, without merging it to main.
