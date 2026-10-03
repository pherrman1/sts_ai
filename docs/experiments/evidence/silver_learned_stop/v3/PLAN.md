# Learned Silver stopping v3: frozen live promotion plan

Status: frozen before any v3 seed ran. Code `8c7da1d0`; the plan commits that
follow it change no code. The independent pre-run review
(`/mnt/project-files/reviews/pr403-v3-prerun-review.md`) required three plan
fixes, applied here: the Bonferroni bound, a full-precision analysis script,
and corrected v1/v2 attribution. Its recommendations are also applied: the arm
order rotates per shard, and `bossmax30k` is labelled as likely informative
only.

## Why

Learned stopping passed its replay gate twice: v1 (`gbt-b91dcfea64e1`,
ledger §370) and v2 (`gbt-770201c31f7b`, §372). The live floor difference
against #199 leaned negative in both 128-seed live runs:
- v1 (43M): −1.15;
- v2 (45M): −0.96, 95% CI [−2.1, +0.0].

Pooling both runs (256 pairs, two different models) gives −1.05,
CI [−1.88, −0.23]. Learned stopping won more often (196 vs 188) but died
earlier in lost runs.

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
- Each part runs 4 shards of 64 seeds, one CPU each. Each shard runs all four
  arms; shard k starts the arm list at position k, so within a part every arm
  runs once in every position. Per-seed results do not depend on the order.
- Every command goes through `tools/seed_guard.sh`, and the script checks the
  binary hash before any shard starts.
- Budget: about 91–96 CPU-seconds per seed over all four arms, estimated from
  the §372 live and replay timings. That is about 26–28 CPU-hours in total, or
  about 1.75 hours wall time per container.
- A shard that exits nonzero is kept and not retried. The analysis then uses
  the seeds present in all four arms and says so.

## Analysis

The verdict comes from `analyze.py run3` in this directory, at full precision.
- It pools each arm's 16 shard CSVs and pairs by seed.
- For each variant V in {`learned`, `bossfallback`, `bossmax30k`} it calls
  `paired_analysis.bootstrap_ci` with 10,000 replicates and a fresh generator
  with seed 20260807.
- If a shard is missing, the analysis runs on the intersection of the seeds
  present in all four arms and marks the report as partial. The descriptive
  `paired_analysis.py` reports then need `--allow-partial`.

**Primary metric:** the mean paired floor difference ΔF(V) = floor(V) −
floor(control), with a **Bonferroni-corrected 98.33% bootstrap CI**
(1 − 0.05/3, for three variants against one control).

**Qualification:** V qualifies when both of the following hold.
- The lower bound of that 98.33% CI is above **−0.75 floors**.
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

**`bossmax30k` is likely informative only.** The review estimates about 27–29
seconds per run for it, against 26.7 for the control, so it probably fails the
time criterion by construction. It answers Philipp's question through the
`bossmax30k` − `learned` comparison: floors, wins and boss deaths. If that
comparison shows a gain (Inference: ΔF above 0 with a 95% CI excluding 0), a
cheaper version of the boss cap becomes the next candidate. Otherwise the
10k cap stays.

**Power (Inference):**
- The per-pair SD of ΔF was 7.2 floors in §370 (v1) and 6.2 in §372 (v2).
  At 1,024 pairs the 98.33% CI half-width is about 0.5 floors.
- A variant with a true ΔF of 0 qualifies with about 88% probability.
- A variant with a true ΔF of −1 qualifies with under 1% probability.
- The pick among qualifiers is a point-estimate choice, not a significance
  claim.

## What follows

A `PROMOTE_<V>` verdict is a recommendation. The default flip is a separate
ADR and PR, and Philipp decides. Nothing in this change alters a default.
