# Independent implementation review: final-boss binary objective

Reviewer: strategy specialist, independent of integrity's implementation.
Reviewed files: `include/sim/search/SilverSearcher.h`, `src/sim/search/SilverSearcher.cpp`, `src/sim/search/NativeSilverBackend.cpp`, and the `testSilverSearcher` addition in `apps/test.cpp`, as present before the coordinator's first campaign implementation freeze.

No actionable correctness blocker found. The context flag defaults false. The modified evaluator returns 100 for `Outcome::PLAYER_VICTORY` and zero for other outcomes only when the research flag, act 3, boss room and A0 conditions all hold. Earlier acts, non-boss fights, other ascensions and unset flag retain the existing evaluator. The backend additionally requires an Act-3 cutoff, exact root budgets, adaptive and learned stopping disabled, no stop trace, and flat per-call overrides at affected fights.

The focused fixtures test winning-resource invariance, actual victory above a long near-lethal loss, non-target context neutrality and an exact legacy score. Suggested validation complement: startup rejection with conflicting learned-stop/no-cutoff settings and an effective mode receipt. The coordinator owns executed checks; this source review does not claim those checks passed.

Scientific boundary: this changes score units/distribution as well as removing irrelevant final-run resource terms, so compare against Bflat with matching exact search budgets. It does not demonstrate an advantage before run-level outcomes. Do not silently use the existing learned-stop model under this treatment. Unresolved rollout endings receiving zero may alter exploratory behavior; that is part of the declared binary-success mechanism, not a proven strength improvement.
