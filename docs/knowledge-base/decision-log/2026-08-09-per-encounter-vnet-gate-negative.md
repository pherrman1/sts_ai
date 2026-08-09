# Per-encounter vnet specialization gate: NEGATIVE

**Date:** 2026-08-09

**Decision:** Close the per-boss XGBoost fine-tuning line. The gate is
negative — direction wrong, not statistically significant but consistent
with §126 (boss-conditioning flat/negative).

**Rationale:**

Per-boss fine-tuned models (Arm 1 of §150) were benchmarked at 64 paired seeds
(S3 fair, 1k sims) against the identical pooled base model. The per-encounter
dispatch added 50 boss-specialized XGBoost trees per boss on top of a shared
2000-tree pooled model.

- Run-level: −6.2pp win rate (95% CI [−15.6pp, +1.6pp], n.s.)
- Floor −0.8, HP end −4.2
- Discordance: 6 pooled-only wins vs 2 per-boss-only (8/64 pairs)

Per-boss detail shows a HP-preservation-over-win-probability trade: COLLECTOR
(−8.6pp win, +14.5 exit HP) and TIME_EATER (−12.5pp win, +12.4 exit HP). The
fine-tuned model is valuing endHp over winning — a direct consequence of the
endHp label target without sufficient win-bonus weighting.

**Inference:** The pooled XGBoost already extracts per-encounter signal through
its encounter feature (index 1). Per-boss trees trained on a constant encounter
value do not learn interactions the pooled model missed — they learn a biased
HP-preservation objective that hurts win rate. This is consistent with §126
(boss-only conditioning of the pooled vnet was flat) and with the earlier
entity-aware multi-head rejection (§57).

**Alternatives considered:** Per-boss fine-tuning with a different label target
(e.g., P(win)-weighted endHp) could theoretically fix the HP-preservation bias,
but the −6.2pp starting point and the large CI mean the lever would need to be
substantial to reach significance. The §126 result suggests any per-encounter
specialization faces an uphill battle against the pooled model's existing
encounter awareness.

**Evidence:**
- EXPERIMENTS.md §150 (updated with gate results)
- Gate CSVs: `.ai/cycles/2026-08-09-11-53-34/{baseline,treatment}_sdiag.csv.fights.csv`
- Run-level paired: `.ai/cycles/2026-08-09-11-53-34/{baseline,treatment}_runs.csv`
- §126 (boss-conditioning flat)
- §57 (entity-aware multi-head rejected)

**Status:** Closed. Per-boss XGBoost fine-tuning is not worth pursuing.
Meta-learner (Arm 2) is deferred — high label noise + negative XGBoost arm
make it unlikely to succeed without a better label target.
