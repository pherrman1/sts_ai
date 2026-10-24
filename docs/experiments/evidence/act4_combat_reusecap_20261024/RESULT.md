# Act-4 combat strength at a raised node cap: 40k wins the Heart +2.4 pp over production 10k; Shield and Spear unchanged (2026-10-24)

**Question** ([PREREG](PREREG.md)). Does Silver at 40k simulations do better in Act 4 when its reused tree is kept
(node reuse cap 262,144 instead of 32,768, `STS_SILVER_NODE_REUSE_CAP`)? Same 128 + 128 states, copies and seeds as
[`../act4_combat_strength_20261024`](../act4_combat_strength_20261024/RESULT.md); only the 40k cells, named Pc, PPc, Nc.

**Run.** Run commit `c19e1213` (code `269cf66d`, binary `415cb152…`), 32 cloud workers × 4 lanes, queue schedule,
2026-10-24 from 11:45Z. `tools/cloud/verify_campaign.py`: 764 of 768 units OK, 0 bad, one run commit; two units
were delivered twice with identical CSVs. The last four units (Heart PP states 4, 36, 68, 100) stayed on one slow
worker for over 4 h; they were rerun in this thread's container from the same run commit and binary (`415cb152…`,
`.env` `STS_EXECUTABLE_GIT_SHA=c19e1213`), 16:02Z–17:20Z, rc 0. All 768 units rc 0, no fight threw; the first
campaign's one error (Heart state 15 copy 4) is dropped from every cell. Results: [`analysis.json`](analysis.json).

| cell (40k, cap 262,144) | Heart wins | Heart HP lost | Heart CPU s/fight | S&S wins | S&S HP lost | S&S CPU s/fight |
|---|---|---|---|---|---|---|
| Pc | 60.6% | 53.5 | 42 | 94.4% | 28.8 | 26 |
| PPc | 63.2% | 51.7 | 243 | 95.1% | 25.4 | 148 |
| Nc | 57.6% | 55.8 | 41 | 92.8% | 30.7 | 26 |

For comparison (first campaign, cap 32,768): Heart P/PP/N 57.5/60.9/57.4% at 10k and 58.7/61.9/56.1% at 40k;
S&S HP lost P/PP/N 29.9/25.4/30.6 at 10k.

**Primary** (95% bootstrap over the 128 states):
- Heart win `PPc@40k − PP@10k` **+2.4 pp [+0.6, +4.2]**: CI above 0, mean below +3 pp.
- S&S HP lost `P@10k − Pc@40k` **+1.1 HP [+0.1, +2.0]**: below 3 HP.
- Rule: **INCONCLUSIVE** (neither COMBAT_HEADROOM nor SATURATED).

**Secondary.**
- Heart, capped 40k vs 10k: Pc − P +3.1 pp [+1.2, +5.1]; Nc − N +0.2 pp [−2.1, +2.7].
- Heart, raised vs default cap at 40k: PPc − PP +1.4 pp [−0.6, +3.5]; Pc − P +2.0 pp [−0.3, +4.2]; Nc − N
  +1.5 pp [−0.9, +3.9]. All three point the same way; none excludes 0.
- S&S: the raised cap changes nothing (PP10 − PPc40 +0.0 HP [−0.8, +0.9]; P40 − Pc40 −0.1). Prior playouts at 10k
  remain the only S&S gain (first campaign: +4.5 HP).
- CPU: the raised cap adds 5-14% per fight at 40k.

**Interpretation.** With its tree kept, 40k Silver with prior playouts wins the Heart about 2.4 pp more often than
production's 10k; the gain is real at 95% but
below the pre-registered +3 pp line. More budget does not help S&S; prior playouts do.

**Decision (Philipp, 2026-10-24 17:00Z):** "Die extra Kosten sind es mir für beide Combats wert": whole-run Act 4
defaults to S&S at flat 10k with prior playouts and the Heart at flat 40k with the cap raised (ADR-0060,
`STS_SILVER_ACT4_STRONG=0` restores the learned stop).
