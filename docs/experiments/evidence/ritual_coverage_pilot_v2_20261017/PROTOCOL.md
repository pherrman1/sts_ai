# Controlled A0 Ritual coverage pilot v2 (scaled sources) — preregistration

Status: **approved by Philipp 2026-10-17T10:56Z ("lets scale sources"); not
executed.** Follows §505, where the v1 packet
([protocol](../ritual_coverage_pilot_20261017/PROTOCOL.md),
[result](../ritual_coverage_pilot_20261017/REPORT.md)) was
`PILOT_COVERAGE_INCONCLUSIVE`: 144/144 valid units but only 25/494 Writhing
targets (5%) with positive Dagger growth and every VALIDATION `cellPositive`
cell short.

## Single change from v1

**Sources only.** v1's question, twelve cells, intervention, producer, teacher,
per-unit budgets, coverage thresholds, ordinary-child exclusions, stop rules,
classification and "no retry / extension / fitting / TEST access / promotion"
all carry over unchanged from the v1 protocol. Launcher:
`tools/ctm_ritual_coverage_pilot.py --packet v2`.

- Sources are the first **40 TRAIN** and first **20 VALIDATION** members of
  52000000..52000399 in the same split manifest
  (SHA-256 `a32ff220b0a6e4b8fa7350ed0f29cba267ea46cef1b140c60f0cdbb181ba8e85`),
  **excluding all twelve v1 sources**, chosen before any v2 outcome:
  - TRAIN: 52000010, 52000012–52000014, 52000016–52000018, 52000022–52000031,
    52000033, 52000035–52000043, 52000045–52000052, 52000054–52000056,
    52000058, 52000059.
  - VALIDATION: 52000032, 52000034, 52000057, 52000074, 52000100, 52000104,
    52000123, 52000129, 52000159, 52000175, 52000181, 52000183, 52000199,
    52000200, 52000203, 52000217, 52000226, 52000235, 52000237, 52000255.
- **720 units** (60 sources × 12 cells), source-major then v1 cell order. The
  first source's twelve cells remain the mechanics checkpoint.
- Eight single-thread workers, 60 s/unit, 90 min packet ceiling, 8 GB address
  space per worker, no GPU (v1 needed 223 s for 144 units).

## Decision rule and interpretation

Classification is computed on v2 alone (v1 sources are not pooled), using the
v1 thresholds counted in distinct source groups. `PILOT_COVERAGE_ADEQUATE_FOR_REVIEW_ONLY`
licenses only designing a reviewed Ritual-only fit; it qualifies nothing.
`PILOT_COVERAGE_INCONCLUSIVE` with ~5% positives again means source scaling
alone is insufficient and a Dagger-kill-raising design is needed. Any invalid
unit gives `PILOT_INCOMPLETE_OR_INVALID`.
