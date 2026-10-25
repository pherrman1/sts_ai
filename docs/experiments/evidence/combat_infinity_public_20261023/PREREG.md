# Public-root infinity annotation pilot

Accepted continuation of the phase-2 handoff. Separate fresh app-managed worktree infinity-public-root-pilot, baseline reviewed/frozen phase-2 commit 59d7c463f733c9fb23ccef194d9d3d5c1dd9a3ff, dependent draft PR #843 unmerged. No phase-2 worktree edits.

Hypothesis: a small research-only adapter can label public information sets by sampling K=4 concrete worlds using Silver CardPile.drawTop semantics, without private draw order/RNG. This pilot tests adapter correctness and preserved-root coverage, not natural prevalence or label calibration.

Fixed scope/budget: first four archived public roots (hash-bound inventory, no outcome filtering), K=4 per eligible root, existing oracle bounds unchanged (depth24, nodes2000, candidates16, periods128, actions1024, total4096 per world). No new whole-combat/run seed cohort; no model, AZ/training/loss/reward/default/Silver/OOC modifications. Four constructed public controls (exhaust Dropkick, energy-positive, broken Dropkick, phase guard), each K=4, plus four-seed sampler contract checks with known top/bottom and three unknown cards. Each CLI run has a 30-second wall bound.

Sampling: canonical public wire hydration, discard source isolatedSearchSeed and observation generation from sampling identity, derive per-world seeds from SHA256(domain:canonical-public-sha:k), seed all six streams via seedSearchRng, drain a copied information-set CardPile via existing drawTop using shuffleRng, reverse to bottom-first concrete representation. Keep the post-drain shuffle RNG for future simulator operations. This reuses the public-conditioned distribution, not the exact historical trajectory or an assertion of pathwise RNG coupling across lazy/eager interleaving.

Sidecar certified_fraction = certified worlds / 4. candidate_fraction = worlds with any damaging candidate, including certified / 4. minimum_reach_depth = minimum among damaging candidates, null if absent. Preserve all per-world oracle witnesses/caps/replay diagnostics and sampled seed/order. Unsupported or missing-provenance roots get null fractions, never a negative label or a reduced denominator.

Before launch inventory already shows retained roots lack no-Prismatic-Shard evidence outside combat's two relic bitsets. Do not manufacture the assertion, weaken the gate or recollect a cohort. Report unsupported coverage explicitly; constructed controls may pass while natural-root annotation remains blocked by missing provenance.

Checks: known-top/bottom and physical multiset preservation, exact full-draw parity with Silver lazy kernel for K=4 seeds, ignored source RNG/unknown-list permutation/private side-channel invariance, root immutability, rejection of concrete/private order and hidden intents, missing/false no-Shard yields null labels, and positive/negative sidecar aggregation. Independent review before scientific interpretation; no merge or scale-up.
