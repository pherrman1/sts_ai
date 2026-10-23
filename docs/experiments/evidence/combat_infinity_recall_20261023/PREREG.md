# Phase 2 realistic recall qualification

Baseline: merged #839, 45eb23a7ed88869f3ea54d22d70f37e3cf93b22e. Both inherited review corrections verified before starting. Fresh app-managed worktree infinity-realistic-recall, branch research/infinity-realistic-recall.

Accepted user handoff: retain depth 24, nodes 2000, candidates 16, replay periods 128, actions per candidate 1024, total replay actions 4096. No model/artifact/training/loss/reward/default/Silver/OOC changes. No natural roots or new seed cohort. Deterministic constructed concrete states, RNG initializers 1..6 inherited from #839. One process CPU observation per fixture/arm; no throughput or population recall claim.

Arms, in order: (0) unchanged merged detector with added fixture harness; (A) qualify singleton shuffle RNG using active zones, retain exhaust exact; (A+B) only energy excluded from control bucket, require nondecreasing energy for candidate and every replay period. Preserve patches and source/binary hashes for each arm. Never increase caps.

Positive A: two Dropkicks, Vulnerable 2, energy 1, 200-HP Cultist; seven static exhaust cards: Strike x2, Defend x2, Bash, Anger, True Grit. No active powers or hooks. Negative: remove Vulnerable. Also retain exact exhaust payload/physical ID/size sensitivity.

Candidate B: two Dropkicks plus Sundial, starting energy 7, card #0 base/turn cost 0, card #1 costForTurn 1; test with and without the same static exhaust. Full mechanical period: prefix four plays then six plays, same Sundial counter. Matched negative changes only card #0 persistent cost (base and turn) to 3; verify energy declines and legal play ends before lethal. This avoids extending the RNG quotient to new card identities. Pommel+/Shrug is unsuitable for an energy-only comparison without additional setup because Shrug also increases block. No block abstraction is authorized.

Retain legacy Time Warp/Awakened guards; add simulator-initialized Time Eater and A20 Heart (800 HP, Beat of Death 2, Invincible 200), including full simulator trace through damage cap/player death. Keep exact player HP, block, powers and monster counters.

Decision PASS only if exhausted Dropkick and a neutral/positive realistic engine certify, all matched near misses/encounter guards do not falsely certify, and positives remain comfortably inside original limits. Otherwise stop without broadening abstraction/search. A PASS permits a separately requested public-root pilot only, never implementation here.

Fixture-construction correction before oracle changes: the first mechanics probe failed because turn-only cost changes reset in piles. See development-turn-cost-result.txt. The final persistent-cost contrast tests the intended economics. The cost-3 negative is a controlled near miss; no natural-occurrence claim.
