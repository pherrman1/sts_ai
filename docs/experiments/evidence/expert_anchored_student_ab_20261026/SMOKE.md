# Pre-launch smokes, seeds 111385990-111385991 (2026-10-27 00:40Z)

Binary `linux-gcc-release-x86-64-v3` at code commit `f526cef9` (main), sha256
`5d9ac01529b73fa9284d70f001d71695aee1c54e075e2163fb32b18c8ef4ff62`. Inputs: student_sel.bin `cf6bf7fb…`,
expert.bin `14506144…`. Four lanes in parallel on one 4-CPU cloud container, through `run_unit.sh` with
`ARMS_OVERRIDE`.

| check | result |
|---|---|
| A 111385990, B 111385990, B 111385990 again, A 111385991 | all rc 0, every banner check in `run_unit.sh` passes, footer `complete` + `integrityPassed` |
| heart1 loaded | A logs `[heart1] loaded …/student_sel.bin`, B `…/expert.bin`; header `model_artifacts` role `ooc_heart1` carries the right sha256 |
| header A vs B | identical except the CTM row path and the ooc_heart1 artifact |
| determinism | the two B runs of 111385990 give identical game records (sha256 of rows 2.. `1e8b3bdc…`) |
| search | MAP arm config banner `searchScreensA20Default=map_full_budget`; 13 searched roots per game, all on map screens; Act 4 strong banner present; every other screen `heart1_screen` or a rule |
| A vs B on 111385990 | first divergence at an act-1 shop (`heart1_screen`); both die on floor 13 (act 1) |
| analyze.py | runs on the pair (verdict NOT_SHOWN on 1 seed, wall B/A 1.08); `--futility` runs (CONTINUE) on a copy renamed into the futility block |
| wall | 111385990 (floor 13): A 75 s, B 81 s; 111385991 (A, floor 33): 342 s |

Unit time for a game that reaches the Heart is longer (§683: 647 s for a full MAP game before Act-4 strong); expect
20-50 min per unit (two games; reviewer: up to 40-50 min when both reach the Heart).
