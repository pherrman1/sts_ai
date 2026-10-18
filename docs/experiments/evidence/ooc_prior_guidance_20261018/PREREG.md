# OOC MCTS prior guidance: Act-1 A20 screen (pre-registered 2026-10-18, before any variant data)

**Question (Philipp, 2026-10-18 11:46Z):** does the student_sel prior over-guide OOC MCTS, so that search only
explores the top pick, and do a looser prior and/or a max-mean-Q final pick play better? Cheapest test: Act 1 only.
Authorization: Philipp 12:01Z "okay do 16 workers actually".

**Diagnostic (existing data, no new runs):** 12,802 non-trivial OOC roots in the decision logs of the A20 winrate
check (224 seeds, binary 9daffbd4, 14 uploaded tars): median top-move prior 0.9925 (>0.99 in 52%), top child median
97.8% of root visits, early-stop visit lock on 100% of roots (~2,050 of 4,096 sims), executed move = prior argmax
90.5%; non-selected children median 2 visits (46% exactly 1). Applying temperature T to those priors (p^(1/T)): Act-1
median top prior 0.996 (T=1), 0.930 (T=2), 0.829 (T=3).

**Stack:** A20 winrate-check stack (`a20_winrate_check_20261018`: student_sel heart1full prior, TARGET_PRIOR=1,
LEAF_SELECTS=heart1, rollout3 + public X2-B, Silver flat exact 10k with g6_E, A20 CTM) at code commit 658d43ee
(main after #659/#660, so STS_ACTIVE_POWER_FEATURES=1 and STS_DEAD_TARGET_DEBUFF_FIX=1 defaults), Act 1 only
(`STS_STOP_AFTER_ACT=1`), fair, one seed per process.

**Arms** (only these values differ; `run_unit.sh`):

| arm | SIMS | TEMPERATURE | ROOT_SELECTION | note |
|---|---|---|---|---|
| C | 4096 | 1 | visits | current default (lock on) |
| T3 | 4096 | 3 | visits | looser prior, lock on |
| Q | 2048 | 1 | q | max mean Q pick; q disables the lock, 2048 ~ C's actual ~2,050 sims |
| T3Q | 2048 | 3 | q | both |

**Seeds:** 111195280-111195343 (64), every arm on every seed (paired). 256 units, 16 workers x 16, 4 parallel.
Smoke: 111195272 (C, in the author's container).

**Primary:** Act-1 score = HP after the Act-1 boss if cleared, else 0 (csv `won`, `hpEnd`). Paired mean difference
vs C, seed bootstrap 95% CI (10,000 resamples, seed 0).
**Secondary (descriptive):** Act-1 deaths, max HP, OOC MCTS CPU per run, sims per root, share of picks = prior argmax.
**Rule per arm vs C:** WORSE if CI upper < 0; SCREEN_PASS if mean >= +3 HP and Act-1 deaths <= C's; else NOT_SHOWN.
SCREEN_PASS only earns a confirmation run that reaches later acts (Philipp's word); no default change from this screen.
**Known limits:** Act-1 HP ignores deck quality that pays off later; T3 runs more sims than C (lock fires later).
