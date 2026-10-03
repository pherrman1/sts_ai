# Learned Silver stopping v3: frozen live promotion plan

Status: frozen before any v3 seed ran. Code `8c7da1d0`; the plan commit follows
it and changes no code.

## Why

v2 passed its replay gate twice (ledger §370, §372). Pooling both 128-seed live
runs (256 pairs) shows two things:
- more wins for learned stopping (196 vs 188);
- earlier deaths in lost runs, with a floor difference of −1.05,
  CI [−1.88, −0.23].

The v2 replay also had its only negative room estimate in boss fights:
−0.0074, CI [−0.0246, +0.0101].

A default flip should first rule out a strength cost of about one floor.
128 pairs cannot resolve that. Philipp also asked whether hard decisions,
especially in boss fights, should get more than the 10k cap.

## Arms

All arms use the same binary (`one_combat-8c7da1d0`, sha256
`c43c9d1bab5d05e4c2d7823a330fc061217da702481cc982c83e02a1464cfd11`) and
`../live_env.sh`.

| Arm | Settings |
|---|---|
| `control` | production #199 (`STS_SILVER_ADAPTIVE=1`) |
| `learned` | v2 unchanged (`STS_SILVER_ADAPTIVE=0 STS_SILVER_LEARNED_STOP=1`) |
| `bossfallback` | v2, but boss rooms use #199 (`STS_SILVER_LEARNED_STOP_BOSS_FALLBACK=1`) |
| `bossmax30k` | v2; a boss root that reaches 10k without stopping continues in 10k steps up to 30k, until its leader is strictly locked against 30k (`STS_SILVER_LEARNED_STOP_BOSS_MAX=30000`) |

Model `gbt-770201c31f7b`, threshold 0.0323, unchanged from §372.

Smoke checks (seed `46009000`, not pooled):
- All four arms ran and their sidecars record the settings.
- Under `bossmax30k`, roots went past 10k only on boss floors (16 and 33):
  16 roots reached 30k and 1 stopped at 20k.
- `BOSS_MAX=5000` and `BOSS_FALLBACK` without learned stopping are rejected
  (ctest).

## Run

- `bestbench`, Ironclad A0, fair play, paired seeds `46000000..46001023`
  (1,024 seeds, unused before).
- `launch_part.sh M`, M = 0..3, splits the seeds into four disjoint parts of
  256, one part per 4-CPU cloud container.
- Each part runs 4 shards of 64 seeds, one CPU each. Each shard runs the four
  arms in order.
- Every command goes through `tools/seed_guard.sh`, and the script checks the
  binary hash before any shard starts.
- Budget: about 91 CPU-seconds per seed over all four arms, measured in the
  §372 live runs. That is about 26 CPU-hours in total, or about 1.7 hours
  wall time per container.
- A shard that exits nonzero is kept and not retried. The analysis then uses
  the seeds present in all four arms and says so.

## Analysis

For each variant V in {`learned`, `bossfallback`, `bossmax30k`}:
- Pool each arm's 16 shard CSVs.
- Run `paired_analysis.py control.csv V.csv`: strict seed pairing, a
  10,000-replicate bootstrap with fixed seed 20260807.

**Primary metric:** the mean paired floor difference ΔF(V) = floor(V) −
floor(control), with its 95% bootstrap CI.

**Qualification:** V qualifies when both of the following hold.
- The CI lower bound of ΔF(V) is above **−0.75 floors**.
- Its mean seconds per run are below the control's.

**Verdict:**
- `PROMOTE_<V>`: at least one variant qualifies. V is the qualifying variant
  with the highest mean ΔF; on a tie, the one with fewer seconds per run.
- `KEEP_OPT_IN`: no variant qualifies.

**Reported, not part of the verdict:**
- wins and the win-difference CI;
- ending HP;
- seconds per run;
- deaths by encounter class, boss deaths in particular;
- `bossmax30k` against `learned` and `bossfallback` against `learned`.

**Power (Inference):**
- The per-pair SD of ΔF was 6.2–7.2 floors in §370 and §372. At 1,024 pairs
  the CI half-width is about 0.4 floors.
- A variant with a true ΔF of 0 qualifies with about 95% probability.
- A variant with a true ΔF of −1 qualifies with under 1% probability.
- Three variants are each tested at 95%. The pick among qualifiers is a
  point-estimate choice, not a significance claim.

## What follows

A `PROMOTE_<V>` verdict is a recommendation. The default flip is a separate
ADR and PR, and Philipp decides. Nothing in this change alters a default.
