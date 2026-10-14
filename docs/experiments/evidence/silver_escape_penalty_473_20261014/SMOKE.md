# §473 planning smoke (seeds 74070750–74070767)

Planning container, 2026-10-14 16:36–16:55Z, binary sha256 `bafcdf80…` built from
[CODE_COMMIT](CODE_COMMIT), through `run_unit.sh`, both arms, one seed per unit.

| unit set | rc | outcome |
|---|---|---|
| 74070750 (A0), 74070751 (A20), both arms | 4 × 0 | identical rows and traces |
| 74070752–74070767 (A0), both arms | 32 × 0 | 14 seeds identical; 74070756 and 74070759 diverge (traces differ; end HP 48→12 and 36→34, both still won) |

- The `.env` pairs differ only in `STS_SILVER_ESCAPE_PENALTY` (`0,0` vs `12,35`) and output paths, and set
  neither `STS_OOC_SKIP_OPTIONAL_RECALL` nor `STS_MULTISELECT_CANONICAL`.
- The first smoke attempt at 47ef0dee exited rc=2 at startup: `one_combat` rejected the option (missing from its
  accepted `STS_SILVER_*` list). Fixed in e221fcac, which is the code commit.
- 2 of 18 seeds diverge, so the option reaches play, and most runs never hold a Smoke Bomb in a fight
  (low power, as the prereg says).

Raw: `/mnt/project-files/silver-escape-473/smoke-473.tar` (sha256 `e11abd7d43ff7d9f0d7270d83211e644a38d094727d99651b2525171fc069034`).
