# M0 as the A20 default plays the A/B's arm M; `=0` plays arm A (2026-10-23)

**Question.** [ADR-0057](../../../../decisions/0057-ooc-leaf-calibration-a20-default.md) makes the calibrated leaf M0
the A20 default: with `STS_OOC_MCTS_LEAF_CALIBRATION` unset, the rollout3 X2-B leaf takes
`-2.5384,-2.9227,-3.6523,-3.6334:1.0535`. Does the default play exactly what the value-level A/B measured as arm M
(`../value_level_ab_20261023/`), and does `=0` play exactly arm A?

**Design.**
- Two A/B seeds on which arms A and M play differently: 111340189 (arm M 207 records, arm A 177) and 111340744
  (171 and 187).
- [`run_check.sh`](run_check.sh) plays one game with an A/B arm's environment from its unit tar (`<arm>-<seed>.env`).
  It drops the heart1 path, the git sha and the calibration from that environment and adds the setting under test.
  The game is `heartoutcomegen 1 SEED OUT policy` under `tools/seed_guard.sh`, as in the A/B.
- Three settings per seed:
  - `def`: arm A's environment, calibration unset (the new default). Expected: arm M.
  - `off`: arm A's environment with `STS_OOC_MCTS_LEAF_CALIBRATION=0`. Expected: arm A.
  - `exp`: arm M's environment, explicit calibration. Expected: arm M.
- [`compare.py`](compare.py) compares every record after the header and every CTM row with the A/B's records. The
  header holds file paths and the git sha, so it differs.

**Result.** PASS ([`compare.txt`](compare.txt)).
- Binary: x86-64-v3 release `one_combat` built at `93a78e19`, sha256 `bac252f8e7b10616…`. Later commits on this
  branch change only the live advisor and docs, not this binary's sources. heart1 file `student_sel.bin`
  (`cf6bf7fb…`), as in the A/B.
- Every compared record and CTM row is identical:

  | seed | `def` vs arm M | `exp` vs arm M | `off` vs arm A |
  |---|---|---|---|
  | 111340189 | 207 records, 17 CTM rows | 207, 17 | 177, 13 |
  | 111340744 | 171, 15 | 171, 15 | 187, 15 |

- `def` and arm A differ from the first records on, so the check can tell the two arms apart.
- Banners: `def` prints `leaf_calibration=-2.5384…,-2.9227…,-3.6523…,-3.6334:1.0535… leaf_calibration_min_ascension=20`
  (17 significant digits), `exp` the same calibration without the scope, and `off` no calibration.
- All six games ended rc 0 in 208–308 s. Neither seed reaches Act 3 in either arm: arm M dies on floors 30 and 23,
  arm A on floors 23 and 28.
- The same check passed on the binary built before the win-model guard (`01049bab…`,
  [`compare_pre_guard.txt`](compare_pre_guard.txt)).

**Conclusion.** The default reproduces the A/B's arm M byte for byte, and `=0` reproduces arm A. The A/B's result for
M0 is the result for the default.
