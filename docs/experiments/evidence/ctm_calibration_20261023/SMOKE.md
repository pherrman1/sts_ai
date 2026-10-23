# Smoke of the CTM-calibration A/B (before the freeze)

**Purpose:** run [`run_unit.sh`](run_unit.sh) end to end on spare seeds before the freeze: both arms finish, the
banners and the calibration table are right, and [`analyze.py`](analyze.py) reads the output. Ten seeds say nothing
reliable about the primary.

## Setup
- Binary `one_combat` sha256 `2e65eff7b3cd552c2403e8bd8fa50befb5da8cedddd2663391c080fa36d85a47`, built from
  `ea859598` (the flag). `12e69805` changes only docs; `run_unit.sh` is the same in both. OOC prior
  `student_sel.bin` `cf6bf7fb…`.
- Seeds 111394990–111394993 started 2026-10-23 18:33Z at `ea859598`; 111394994–111394999 started 19:17Z at
  `12e69805`. Four units ran at once on this 4-core container.
- Raw output (the `run_unit.sh` output dirs): `/mnt/project-files/ctm-calibration/ctm_calibration_smoke_20261023.tar.gz`
  (sha256 `3107328695c63349f7fa52dd9454758e3e6a3e2e08e36ab3e5fb8074ced0c774`).

## Checks
- All 20 games ended with rc 0 and a complete, integrity-passed footer.
- In every game's log and stderr: the learned OOC stop, the Act-4 survival model, the heart1 prior, the fast-root cap
  1024 and the M0 leaf calibration at ascension 20. The calibration banner
  (`[ctm-calibration] table=models/candidates/ctm_calibration_pathb_a20_v1.json sha256=359619f7… groups=34
  scope=pathb-a20`) is in all 10 C games and in no A game ([`smoke_table.py`](smoke_table.py)).
- `analyze.py` reads the output: 10 of 10 seeds valid, C − A −10 pp [−30, 0], NOT_SHOWN
  ([`smoke_analysis.json`](smoke_analysis.json)).

## Games

| seed | order | A | rc | wall s | C | rc | wall s | first different decision |
|---|---|---|---|---|---|---|---|---|
| 111394990 | A, C | died act 3, floor 38 | 0 | 719 | died act 2, floor 30 | 0 | 578 | 59 |
| 111394991 | C, A | Heart kill | 0 | 948 | died act 2, floor 24 | 0 | 388 | 1 |
| 111394992 | A, C | died act 2, floor 29 | 0 | 290 | died act 2, floor 29 | 0 | 241 | 54 |
| 111394993 | C, A | died act 4, floor 56 | 0 | 1264 | died act 2, floor 22 | 0 | 378 | 26 |
| 111394994 | A, C | Heart kill | 0 | 1056 | Heart kill | 0 | 826 | 127 |
| 111394995 | C, A | died act 1, floor 16 | 0 | 282 | died act 1, floor 16 | 0 | 289 | none |
| 111394996 | A, C | Heart kill | 0 | 1204 | Heart kill | 0 | 1021 | 130 |
| 111394997 | C, A | died act 4, floor 55 | 0 | 934 | died act 3, floor 51 | 0 | 1149 | 122 |
| 111394998 | A, C | died act 2, floor 33 | 0 | 550 | died act 2, floor 33 | 0 | 492 | none |
| 111394999 | C, A | died act 4, floor 56 | 0 | 890 | died act 4, floor 56 | 0 | 879 | 47 |

## Reading
- Heart kills: A 3 of 10, C 2 of 10. Only 111394991 differs (A's kill; exact McNemar p = 1). Reached Act 4: A 6,
  C 3. Deaths in Act 2: A 2, C 5. Mean final floor: A 45.1, C 37.3.
- In each of the four seeds whose games ended differently (111394990, 991, 993, 997), A got further. In 995 and 998
  the arms made the same decisions throughout; in 992, 994, 996 and 999 they parted but ended alike.
- The games part at near-ties. At the first decision where the arms differ, the two picks' root Q values are within
  0.016 of each other in both searches in six seeds, and 0.03–0.04 apart in one search in 993 (an Act-1 campfire at
  58 HP: A rested, C upgraded a card) and 994 (an Act-3 card reward) ([`smoke_divergence.py`](smoke_divergence.py)).
  C's root values run higher, as fewer imagined deaths make them (994: the card C took is worth 0.38 to C's search and
  0.30 to A's).
- Descriptive only: C entered Act-2 fights with less HP (mean 64.6 against 67.9), and its three extra Act-2 deaths
  were hallway or event fights entered at 22–26 HP (990, 991, 993). In Act 3 the learned stop ended 57% of C's fast
  roots against 47% of A's (74 and 107 roots). The A/B's secondary endpoints measure both.
- Walls do not compare: C's games ended earlier, and four games shared four cores (mean wall C / A 0.77).
- Effect on the plan: the design stands. Because of this lean, PREREG's point guess went from +1 pp to 0, and the
  recommended run became two stages with a stop rule after 512 seeds.

## Commands
```
python3 -I smoke_table.py OUT OUT2                   # games table, banner check
python3 -I smoke_divergence.py OUT/1113949?? OUT2/1113949??
python3 -I analyze.py ALL smoke_analysis.json        # ALL: the seed dirs of OUT and OUT2 copied into one dir
```
