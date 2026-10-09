# Prior budget sweep vs plain 10k, 128 seeds (pre-registration)

Frozen 2026-10-09 ~10:40 UTC before any new arm ran. Philipp 10:38 UTC: "can
you try a few different simulations with the prior and compare it against 10k
sim with 128 seeds?"

- Same binary (c3547dc4…, 51937c6a), prior (573305c4…, w400), settings as
  PREREG-confirm128.md (A0, fair, keys skipped, flat exact budgets).
- Seeds: same 61001000..61001127 as the confirmation, so arms are paired with
  the existing plain 256 / prior 256 / plain 2k arms (reused, not rerun).
- New arms: prior + 512, 1,000, 2,000, 4,000 sims; plain 10,000 (reference).
- Reported per prior arm: win rate, paired difference vs plain 10k and vs plain
  2k with 95% bootstrap CI (10,000 resamples, seed 0), CPU s/run, mean floor.
- Descriptive sweep, no pass label. A prior arm "matches 10k" only if its CI vs
  10k includes 0 AND the point estimate is >= -3pp; n=128 cannot show
  equivalence to closer than roughly +-8pp, so any such match needs a larger
  confirmation before it is claimed. Nothing ships before the CTM full retrain.
- Note: §399 found prior + 2k = plain 2k on seeds 56003000-031.
