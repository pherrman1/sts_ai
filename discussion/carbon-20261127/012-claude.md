# 012 - claude (Claude Fable 5.2)
Time: 2026-11-27 21:50 CET
Replies to: 011-claude.md (corrections only; a planned edit did not make it into the pushed file)
Repo state read: main @ 25778f1

Four corrections to 011. Nothing else changes; the status table and Q19-Q21 stand.

1. **O3 and Q21: hallways are about 40 % of the fight HP, not half.** From the O3 table, HP lost in won fights
   per full run: hallways 27 + 34 + 15 = 76, elites 33 + 22 + 14 = 69, act-1 and act-2 bosses 25 + 20 = 45
   (act 3 not comparable). 76 of about 190 is 40 %. The share of losses (26 %) is unchanged.
2. **2.1, last paragraph:** "one bench of a fixed net moves by about 1.3 pp against its own expectation" holds
   only if the two teacher runs differ on about 344 seeds. It is an **Inference** until b + c is counted.
3. **Line reference:** the definition F = E[final floor] / 57 is at `apps/az_bench/az_run_driver.h:83` (also in
   the file header, line 17), not `:79`.
4. **2.2:** the HP-class CE does not fall monotonically after 1678542 (2.0444, 2.0399, 2.0406, 2.0377, 2.0374);
   "drifts down slowly" is the accurate wording. The point (not flat, unlike the outcome CE) stands.
