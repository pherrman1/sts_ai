# Act-4 combat strength with the tree-reuse node cap raised (PREREG, 2026-10-24)

**Question (Philipp, 2026-10-24 11:06Z):** "Do we use stopping here? Should we maybe try without and increase the search
space node limit?" The first campaign (`../act4_combat_strength_20261024`) plays flat budgets without any stop, but
Silver drops the reused tree at a reroot once the pool has 32,768 nodes (`kReuseCap`). The node-cap check
(`/mnt/project-files/silver-node-cap/README.md`) found that at 40k ~30% of reroots lose their tree (reuse 39-43% vs
75-77% at 10k); in production (learned stop) 1 of ~2,200. So the first campaign's 40k is closer to ~2.3x than 4x the
10k search per decision.

**Change.** Research option `STS_SILVER_NODE_REUSE_CAP` (integer 1,024-16,777,216; unset = 32,768, production
unchanged; every production/generator mode already refuses a cap other than 32,768). A banner
`[silver] research node reuse cap N` confirms it.

**Design.** The first campaign's 128 + 128 states, arms (P, PP, N), copies and battle/planner seeds
(S&S 111395000-111396023, Heart 111398100-111399123), now only at flat 40,000 simulations with cap 262,144. No new
seeds: every new cell is paired per (state, copy) with the first campaign's 10k and capped-40k cells. 768 units,
8 fights each, queue schedule.

**Smoke (seeds 111396996-997, 2 Heart states, P arm, 40k, OMP 2):** reroots that keep a tree 51 of 96 (cap 32,768)
vs 98 of 118 (cap 262,144); mean inherited visits 5,985 vs 31,803; max tree 88k vs 314k nodes; CPU per fight x1.6.

**Analysis (`analyze_cap.py`, with the first campaign's `analyze.py` bootstrap and ERROR handling).** Cap cells are
`Pc`, `PPc`, `Nc`.
- Primary, Heart: win `PPc@40k - PP@10k` (budget only, production Heart config).
- Primary, S&S: HP lost `P@10k - Pc@40k` (budget only, production elite config).
- Decision rule as the first campaign: `COMBAT_HEADROOM` if Heart CI lower > 0 and mean >= +3 pp, or S&S CI lower > 0
  and mean >= 3 HP; `SATURATED` if Heart CI upper < +3 pp and S&S CI upper < 3 HP; else `INCONCLUSIVE`.
- Secondary: each capped 40k cell vs its 10k cell and vs the uncapped 40k cell; CPU per fight.

**Cost.** About 150 CPU-hours (Heart PP at ~300 s per fight dominates), ~1.5 h on 32 workers.
