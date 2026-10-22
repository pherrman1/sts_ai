# Gumbel-root A20 A/B: result (2026-10-22)

**Verdict: WORSE.** B (Gumbel sequential halving, M = 16, at full-budget roots with 2048 sims) killed the Heart in
48 of 511 paired A20 seeds against A's 106 (PUCT, 4096): 9.4% vs 20.7%. The difference is −11.4 pp [−14.8, −7.9],
exact McNemar p = 2.6e-10 (B-only 15, A-only 73).

| | A (PUCT 4096) | B (Gumbel SH 2048) | B − A |
|---|---|---|---|
| Heart kills | 106 (20.7%) | 48 (9.4%) | −11.4 pp [−14.8, −7.9], p 2.6e-10 |
| Reached Act 4 | 201 (39.3%) | 137 (26.8%) | −12.5 pp [−17.2, −7.9], p 2.6e-7 |
| Final act 1 / 2 / 3 / 4 | 50 / 121 / 139 / 201 | 40 / 161 / 173 / 137 | |
| Mean final floor | 43.5 | 41.0 | |
| Mean wall per run | 708 s | 425 s | 0.60× |
| Searched roots where the played action ≠ prior argmax | 6.5% (2,182 / 33,560) | 17.3% (5,439 / 31,477) | |

**Units.** 511 of 512 seeds are valid (`verify_campaign.py`: 511 OK, 0 BAD, 0 duplicates, all on run `3baca749`).
Unit 111153366 used up its 4 queue attempts: the containers of a1–a3 died, and a4 never sent a heartbeat. It is
reported as missing, not replaced (PREREG). The lead reran it with the frozen binary (`lead-rerun-111153366.txt`):
A killed the Heart and B died in Act 4. With it, the totals are 107/512 vs 48/512 and the verdict is unchanged. Workers W15–W25 delivered no units (containers lost early); the queue covered their share.

**Interpretation.** Offline (§619), SH agreed better with a uniform-allocation reference built on the same leaf
evaluator. In play it overrides the prior on far more roots, and those overrides lose: deaths shift from Act 4 to
Acts 2–3. The leaf Q (rollout3 + X2-B) is not reliable enough to beat student_sel's prior once root selection follows
Q. This is the third time Q-based root selection has lost in play (§414, §560). B's lower wall is mostly shorter runs,
not cheaper search.

**Consequence.** `STS_OOC_MCTS_GUMBEL_ROOT` stays default off. Offline agreement with leaf Q is not a usable gate for
root-selection changes. Any Gumbel-style root would need a value signal that beats the prior, or must keep the prior
dominant (for example a much smaller c_scale), and either needs its own play A/B.

Notes:
- `analyze.py` labelled "B ahead with p < 0.05 above 1.10× wall" as WIN_AT_HIGHER_CPU, a case the PREREG calls
  NOT_SHOWN (reviewer C). The label is aligned in this commit. It does not apply here.
- The worker brief's "uploads exactly wWW.tar and DONE" wording predates queue mode, which also writes `claims/` and
  `units/` (reviewer C nit). The brief stays as the workers received it.

Data: `/mnt/project-files/az-gumbel-root-ab/units/` ([tars.sha256](tars.sha256)), [result.json](result.json).
