# Observed cost-tail addendum

This narrows the resource interpretation in [the timeout disposition review](TIMEOUT_DISPOSITION_REVIEW.md); its `EXECUTION_BLOCKED` verdict and all original caps remain unchanged.

Integrity's completed [source217 diagnosis](../audit/TIMEOUT_610084217_REVIEW.md) is bound by machine receipt SHA256 `f524b1e387abbfa43a565836247e1f55d3f090d388e97b6e2e866263704e3f05`. This strategy review read that metadata report, not the raw branch outcomes or profile rows.

The 100 complete persisted branch records consumed **1,747.39344 game-thread CPU seconds**, averaging **17.4739344 seconds per recorded continuation**. This is about **2.43 times** the proposal's historical BOSS average of 7.1862847 seconds, and about **97.08%** of the 1,800.0335-second invocation wall duration. These are the intact records from this interrupted source, not an estimate of every unrecorded or unfinished branch.

The selected source state was Act 1 floor 17, BOSS_RELIC decision35. The saved profiles show substantial forward work: 38,235 intact roots and 179,029,250 newly completed simulations, with no recorded fatal root error, descent abort, unresolved endpoint or conservation failure. The latest flushed profile precedes receipt finish by about 0.090 seconds. Together, the evidence supports an **observed compute-cost tail**, rather than an observed prolonged stall or engine fault. It does not certify the interrupted root, unflushed records or eventual validity of unfinished branches. The 42 cycle fallbacks and 14 engine-stop search endpoints retain their existing diagnostic meaning.

The resource estimate therefore missed this source's observed expensive continuation tail. It was based on an aggregate average and explicitly excluded tail overhead; neither that average nor the total P6 projection guaranteed that every source would satisfy a separate 30-minute wall cap. The diagnosis cannot isolate the contributions of source horizon, deck/policy behavior, option differences or concurrency. It also cannot reconstruct complete source/branch CPU from the residual wall time.

No action-quality conclusion follows. This is not evidence of K16 harm, improvement or equivalence. There is no post hoc cap relaxation, retry, replacement, incomplete primary or reuse of the closed RemoveLow result. The remaining fixed queue and final failure accounting stay governed by the original protocol.
