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
contracts are unchanged from their already maintained sources. Final results
and current research status will be recorded after the frozen paired run.
