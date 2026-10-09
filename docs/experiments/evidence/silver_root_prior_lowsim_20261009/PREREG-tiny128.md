# Prior vs plain at 128 / 64 / 32 sims, 128 seeds (pre-registration)

Frozen 2026-10-09 ~11:54 UTC before these arms ran. Philipp 11:53 UTC: "can
you even try prior and plain 128 sims and 64 sims and 32 sims?"

- Same binary (c3547dc4…), prior (573305c4…, w400), settings and seeds
  (61001000..61001127) as PREREG-sweep128.md; paired with the existing arms.
- New arms: plain and prior at 128, 64, 32 sims.
- Descriptive: win rate, prior − plain at each budget and each arm vs plain
  10k with 95% paired bootstrap CI (10,000 resamples, seed 0), CPU s/run.
- Note: w400 was tuned offline at 256 sims; it is not re-tuned for these
  budgets.
