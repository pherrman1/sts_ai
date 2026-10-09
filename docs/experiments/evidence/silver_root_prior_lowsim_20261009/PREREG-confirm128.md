# Low-sim prior: 128-pair confirmation (pre-registration)

Frozen 2026-10-09 ~10:22 UTC before any confirmation seed ran. Philipp's "yes"
2026-10-09 10:21 UTC to the offered 128-seed confirmation after the 32-seed
screen (PREREG.md here: prior256 19/32, plain256 13/32, plain2k 19/32).

- Same binary (c3547dc4…, commit 51937c6a), same prior (573305c4…, w400),
  same settings (A0, fair, keys skipped, `STS_SILVER_EXACT_ROOT_BUDGETS=1`).
- Seeds: 61001000..61001127 (128, fresh, disjoint from the screen).
- Arms: A plain 256, B prior w400 + 256, C plain 2,000.
- Statistics: paired win-rate difference with 95% bootstrap CI over seeds
  (10,000 resamples, fixed RNG seed 0).
- Primary: B − A. Secondary: B − C (equivalence question), CPU s/run.
- Labels:
  - CONFIRMED: B − A CI excludes 0 above, and B − C point estimate ≥ −5pp.
  - PRIOR_HELPS_ONLY_VS_256: B − A CI excludes 0 above, B − C < −5pp.
  - NOT_CONFIRMED: B − A CI includes 0 or is below.
- Nothing ships before the CTM full retrain; a confirmation only supports a
  default-off fast mode proposal.
