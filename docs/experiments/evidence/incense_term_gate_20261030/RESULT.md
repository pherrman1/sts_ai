# Incense Burner term at Shield & Spear: gate result

Pre-registration: [PREREG.md](PREREG.md) (frozen before launch; prelaunch review PASS). Campaign `incense-term-gate`,
RUN_COMMIT 221867e3, code bfd45383, binary 0ef572a5; 16 workers × 4 lanes, 2026-10-30 19:1x-21:0xZ.
`verify_campaign.py`: 592/592 units OK, no duplicates, 16/16 worker DONE files ([results/verify.txt](results/verify.txt)).
Analysis: frozen `analyze.py` (sha256 9288fbfd…), output [results/analysis.json](results/analysis.json). All 592 units
rc=0, 592 states valid (8 runs each), 185 source seeds, 0 bad rows.

## Primary
Heart kill (S&S won and Heart won), term on − off: **+5.9 pp [+4.1, +7.8]** → **PASS**.

## Co-reported
| | off | on | on − off |
|---|---|---|---|
| Heart kill | 57.3% [51.3, 63.2] | 63.1% [57.3, 69.0] | +5.9 pp [+4.1, +7.8] |
| S&S death | 4.3% | 4.8% | +0.5 pp [−0.1, +1.2] |
| Heart kill given an S&S win | 58.3% | 64.6% | |
| reach the Heart on an aligned counter {0, 1, 3, 4} | 63.4% | 93.5% | +30.1 pp [+27.9, +32.3] |
| S&S HP left (0 on a loss) | | | −1.3 HP [−2.1, −0.6] |
| S&S turns (0-based) | 4.76 | 5.27 | |
| CPU per S&S + Heart run | 52.9 s | 54.6 s | |

Counter at the Heart (S&S wins, 4 replicates): off 359 / 402 / 442 / 403 / 338 / 323 for 0..5; on 61 / 715 / 15 /
320 / 1,119 / 24. With the term Silver mostly ends S&S on 4 (Intangible on the Heart's first attack) or 1.

On − off Heart kill by the counter at S&S entry (pp, point estimates): 0: +7.3 (n 89), 1: +5.9 (162), 2: +4.1 (98),
3: +6.6 (80), 4: +4.5 (72), 5: +6.9 (91). The gain does not depend on where the counter starts.

First copy of each of the 513 distinct states: +5.9 pp [+4.0, +8.0]; S&S death +0.7 pp [+0.0, +1.5]; aligned 63.5% →
93.6%; S&S HP −1.3 [−2.1, −0.5].

## Caveats
- Research Heart search (learned stop ≤ 10k, Act 4 strong off), not production's flat 40k; S&S rewards skipped in both
  arms; card misc and bottles not carried.
- The price comes from §723 on largely the same games, so it is not out of sample; scale 1.33 HP/pp was not tuned.
- The S&S death cost is small but probably real (+0.5 to +0.7 pp, CI touching 0).

## Decision
PASS per the pre-registered rule. The term goes to Philipp as a default candidate. A production-budget check (Act 4
strong) before switching the default is his call.
