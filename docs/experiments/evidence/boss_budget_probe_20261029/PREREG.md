# Boss-budget probe on Baalorlord's boss states (pre-registration)

Status: FROZEN 2026-10-29 before launch (pre-launch review PASS with fixes: decision regions made disjoint, SMOKE.md, 10 h timeout, cost line). Philipp asked for it on 2026-10-29 07:50Z
("Let's go on 16 workers") after §716 ranked it as fix 1. Code, binary and inputs are in `campaign.manifest`.

## Question

§716 (exploratory, 32 act-2 bosses × 2 copies): flat 40k Silver lost −3.25 [−6.81, +0.27] HP per fight against
today's A20 production (learned stop, ≤ 10k per root), at 7.4× the CPU. Act-2 elites did not gain from 10× or 100×
budget. On all of §711's act-1-3 boss states, does a larger flat budget lower HP lost? And how much of that does
half the budget (20k) keep?

## Design

- States: the 250 of §711's 329 Baalorlord runs that reached a boss inside the exact-replay prefix (499 boss fights:
  250 act-1, 128 act-2, 121 act-3; `units.txt`, ordered by §711 boss CPU, longest first). External run seeds of
  §694; no 111xxxxxx block (seed guard: `expertfights` is guarded at argument 2 as in §711).
- Mode: `one_combat expertfights` exactly as in §711 (`run_unit.sh` differs from §711's only in the `E=` line and the unit timeout, 10 h instead of 7 h), plus
  the §716 research arms: `STS_EXPERT_FIGHTS_ARMS=flat20000,flat40000`, `STS_EXPERT_FIGHTS_ARM_ROOMS=1B,2B,3B`,
  `STS_EXPERT_FIGHTS_ARM_REPLICATES=2`. In every boss fight, copies 0 and 1 are played by production and by each
  arm, on the same copy seeds (copy 0 = the game's battle seed). Other fights and copies are played only until
  the first win, so the main line is §711's.
- Arms: `flat<N>` searches every root with exactly N simulations (one-action roots included). It has no learned stop
  and keeps the boss prior playouts, root and tree priors and the reuse cap. Production is today's A20 default (learned
  stop up to 10k per root, boss prior playouts).

## Endpoints and analysis (fixed; `analyze.py`)

HP lost per copy = entry HP − exit HP, with exit 0 on a loss. The floor-51 exit is inverted for the Act-4
transition heal as in §711, on every side. Side value = mean over its 2 copies. Drops as in §711. 95% CIs:
run-clustered bootstrap (10,000 resamples, seed 20261029).

- **Primary:** mean over all act-1-3 boss fights of (flat40000 − production) HP lost.
- **Decision rule (applied by hand to `primary.flat40000_minus_prod_ci` = [lo, hi]; margin 1 HP per boss fight;
  the three regions do not overlap):**
  - hi < 0 and lo ≤ −1 → **BUDGET_HELPS**: boss budget is a lever worth pricing. Next is a CPU-matched whole-run
    A/B design (Philipp's go).
  - lo > −1 → **NO_USEFUL_GAIN**: any gain is below 1 HP per boss fight (that covers hi < 0, "helps below
    margin", which is reported as such). Boss budget is not a lever worth 7×+ CPU. Stop.
  - otherwise (lo ≤ −1 and hi ≥ 0) → **INCONCLUSIVE**.
- **Co-reported:** death per fight (arm − production, CI), potions per fight, CPU ratio arm/production, flat20000 −
  production with the same CI, by act and by encounter (n ≥ 20), production − expert.
- No default change on this result. Any default change needs a whole-run A/B. The CPU-match rule for that A/B (B
  mean wall ≤ 1.10× A) means a budget increase must be paid for elsewhere, so the 20k arm and the CPU ratio are
  part of the answer.

## Caveats fixed in advance

- 2 copies per side (§716 used 2). The paired difference uses common random numbers on battle streams. Search RNG
  differs by arm only through the search itself.
- The expert's states are those he reached by his own play, and potions are the bot's own (§711).
- The arms change budget only. Prior playouts stay on in bosses in all three sides.
- §716's boss estimate is part of this sample (32 of the 128 act-2 bosses, same copy seeds), so the act-2 row is not
  independent of it. The primary pools all acts.

## Cost

Production boss CPU in §711 is 3.3 h per copy. In the smokes, flat40000 is 9.1× and flat20000 4.3× production
(`SMOKE.md`). With 2 copies of each side that is ≈ 95-100 CPU-h in total, ≈ 2 h on 16 workers × 4 lanes, plus the
tail. The longest unit (1655315178: Hexaghost, Automaton, Awakened One) needs ≈ 5.4 h of CPU, about 6.5-7.5 h on
slow containers. The unit timeout is 10 h (rc 124).
