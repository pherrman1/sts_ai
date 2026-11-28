# 020 - claude (Claude Fable 5.2)
Time: 2026-11-28 09:45 CET
Replies to: 019-claude.md (stratum for the hallway comparison fixed before the run)
Repo state read: unchanged since 019

Hallway fights of the teacher's own 128-sim bench run by entry HP (**Thread**; 13,193 fights, 161 deaths):

| Entry HP (share of max) | Fights | Deaths | Death rate |
|---|---|---|---|
| 0 - 0.3 | 956 | 113 | 11.8 % (acts 1 / 2 / 3: 7.4 / 16.6 / 11.5) |
| 0.3 - 0.5 | 1,858 | 28 | 1.5 % |
| 0.5 - 0.7 | 2,802 | 13 | 0.46 % |
| 0.7 - 0.85 | 3,785 | 5 | 0.13 % |
| 0.85 - 1 | 3,792 | 2 | 0.05 % |

Below half HP: 21 % of the fights, 88 % of the deaths (5.0 % per fight). So hallway deaths are almost entirely
fights entered already badly hurt; 70 % of them start below 30 % HP. This is itself a partial answer to X1's
caveat: whatever 1024 sims save in hallways, the runs that die there at 128 sims arrive with little HP.

Design as now fixed (nothing started; waits for Philipp's go):
- Stratum for the 1024 arm: entry HP below 0.5 in the snapshot run, about 2,814 starts x 4 copies = 11,256
  fight copies, about 2.2 h on the PC GPU. About 560 deaths expected at 128 sims; the 95 % half-width of the
  relative death reduction is about 9 points (clustering by run included).
- 128 arm and Silver on all 13,193 starts x 2 copies.
- Rule as in 019: reduction of a fifth or more with the interval excluding 0 = lost by play inside hallway
  fights; interval excludes a fifth = mostly the arrival state; otherwise undecided. Branch 2 is reachable if the
  true reduction is about 10 % or less.
- In addition to the rule, the same table by entry HP for all three arms on identical states (death rate and HP
  lost), which shows whether Silver or more search survives the low-HP entries the net loses.
