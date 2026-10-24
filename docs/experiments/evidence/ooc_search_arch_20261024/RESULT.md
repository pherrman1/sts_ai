# OOC search architecture A/B/C pilot at A20: result (2026-10-24)

Campaign `ooc-search-arch`, RUN_COMMIT `830d9047`, code `febd4814`, binary `c31fe2b0…`, 64 paired seeds
111302000–111302063 on 8 cloud workers (13:2xZ–15:25Z). `verify.txt`: 64/64 units OK, no duplicates, all 8 workers
DONE; all 192 arm runs rc 0; `analyze.py` 64/64 valid (`result.json`). Pre-launch review PASS
(`/mnt/project-files/reviews/ooc-search-arch-prelaunch-review.md`). Tar hashes in `tars.sha256`.

## Primary: Heart kills (paired)
| | A mcts | B particle | C particle_beam |
|---|---|---|---|
| Heart kills | **13 / 64** (20.3%) | **2** (3.1%) | **3** (4.7%) |
| reached Act 4 | 27 (42.2%) | 8 (12.5%) | 9 (14.1%) |
| kills per Act-4 arrival | 0.48 | 0.25 | 0.33 |
| mean final floor | 43.9 | 37.3 | 38.0 |
| deaths act 1 / 2 / 3 / 4 | 5 / 16 / 16 / 14 | 6 / 25 / 25 / 6 | 4 / 30 / 21 / 6 |

| pair | Heart: only first / only second | diff [95% CI] | exact McNemar p | Act 4: only first / only second | floor diff [95% CI] |
|---|---|---|---|---|---|
| B − A | 1 / 12 | −17.2 pp [−28.1, −7.8] | 0.003 | 1 / 20 (p 2e−5) | −6.5 [−10.5, −2.5] |
| C − A | 2 / 12 | −15.6 pp [−26.6, −4.7] | 0.013 | 4 / 22 (p 5e−4) | −5.9 [−10.1, −1.8] |
| C − B | 2 / 1 | +1.6 pp [−3.1, +7.8] | 1.0 | 4 / 3 (p 1.0) | +0.6 [−2.7, +3.9] |

## Search diagnostics
| | A | B | C |
|---|---|---|---|
| searched roots | 4,199 | 3,566 | 3,716 |
| picks off the prior argmax | 4.2% | 43.8% | 44.1% |
| median selection margin | −0.013 (Q gap; A plays visits) | +0.008 (particle mean) | +0.008 (plan score) |
| OOC planning CPU per root / per game | 7.4 s / 482 s | 1.6 s / 89 s | 9.5 s / 554 s |
| transitions / leaf evaluations per root | 2,499 / 1,296 | 395 / 394 | 2,887 / 2,461 |
| whole-run wall mean (max) | 568 s (1,042) | 128 s (318) | 595 s (1,111) |

Off-prior picks by screen (B; A in brackets): events 45% (2%), rewards 40% (4%), maps 38% (3%), rest 43% (4%),
shops 64% (6%). Root replay (`SMOKE.md`, 53 shared roots): B ≠ A 40%, C ≠ A 42%, C ≠ B 32%.

## Verdict under the frozen decision rule: STOP both new arms
Both new arms are **clearly disastrous**: 11 and 10 fewer Heart kills than A, with fewer Act-4 arrivals and lower
floors (all three CIs exclude 0). C ≈ B (2 vs 1 discordant kills), so a beam over the policy's top-2 ranks adds nothing
over plain particle evaluation, and both lose to MCTS. **Recommendation: KEEP MCTS; STOP B and C** (no 256-seed
extension).

## Interpretation
- **Inference:** the difference is the prior. A plays the prior's argmax at 96% of roots (its played action often has
  the lower Q: median Q margin −0.013); B and C discard the prior at the root and play the leaf's argmax, which differs
  from the prior at ~44% of roots. The rollout3 + value-head leaf is not good enough to overrule student_sel at the
  root: its action gaps are small (median 0.008 against particle standard errors ~0.01; paired z > 2 at 43% of replay
  roots), and the extra deaths come in acts 2–3, consistent with leaf-driven picks that cost HP or deck quality.
  This agrees with the earlier negatives for Q-based root selection (most-visited beats Q-selection, Gumbel SH).
- So B − A answers "do we need PUCT?" mostly as "we need the prior": PUCT at today's settings is a prior-anchored
  search, and direct stochastic evaluation without the prior is much worse. The pilot does not test a prior-anchored
  particle search (e.g. only overruling the prior on a resolved paired gap); that would be a new hypothesis.
- C's plan scores are an in-sample maximum over up to 8 plans on the same particles (optimistic; review note). With
  C ≈ B and both far below A this does not change the verdict.

## Caveats
- 64 seeds; the leaf (SR_crn_r2_s2_ep20 blend w 0.1 + M0) was never qualified online, but all arms share it.
- Equal CPU was not required: B is ~5× cheaper per game than A, C about equal.
