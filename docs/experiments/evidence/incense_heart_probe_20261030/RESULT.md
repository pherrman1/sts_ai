# Incense Burner phase before the Heart: result

Pre-registration: [PREREG.md](PREREG.md) (frozen before launch). Campaign `incense-heart-probe`, RUN_COMMIT feef16cd,
code d5386fcf, binary b6c03fc8; 16 workers × 4 lanes, 2026-10-30 15:5x-16:55Z. `verify_campaign.py`: 630/630 units OK,
no duplicates, 16/16 worker DONE files ([results/verify.txt](results/verify.txt)). Analysis: frozen `analyze.py`
(sha256 3fc21ea0…), output [results/analysis.json](results/analysis.json). 630 states valid in all six arms, 228 source
seeds, 0 bad rows.

## Primary
Heart kill, aligned counters {0, 1, 3, 4} minus wasted {2, 5}: **+12.0 pp [+9.7, +14.5]** → **PHASE_MATTERS**.

## Co-reported
| counter at Heart start | 0 | 1 | 2 | 3 | 4 | 5 |
|---|---|---|---|---|---|---|
| first Intangible on Heart turn | 6 (attack) | 5 (attack) | 4 (Buff) | 3 (attack) | 2 (attack) | 1 (Debilitate) |
| Heart kill | 68.3% [62.4, 73.7] | 71.9% [66.6, 77.0] | 61.7% [55.5, 67.6] | 75.7% [70.6, 80.6] | 80.2% [75.6, 84.4] | 62.2% [55.8, 68.3] |
| kill − state mean (pp) | −1.7 [−3.6, +0.1] | +1.9 [−0.3, +4.2] | −8.3 [−10.7, −6.0] | +5.7 [+3.5, +8.0] | +10.2 [+7.8, +12.6] | −7.8 [−10.0, −5.7] |
| HP left (0 on a loss) | 23.6 | 25.5 | 21.4 | 28.6 | 32.9 | 22.8 |
| turns | 6.81 | 6.99 | 6.48 | 7.39 | 7.50 | 6.50 |

"One more Shield & Spear turn" (kill(c + 1 mod 6) − kill(c)): 0→1 +3.7 [+0.8, +6.8], 1→2 −10.2 [−14.2, −6.4],
2→3 **+14.0 [+10.4, +17.8]**, 3→4 +4.4 [+1.0, +8.0], 4→5 **−17.9 [−21.9, −14.3]**, 5→0 +6.0 [+3.1, +9.2].
HP left, aligned − wasted: +5.6 [+4.4, +6.8]. 61% of states have the same outcome in all six arms, so the effect sits
in the contested 39%. The earlier the first covered attack, the better (counter 4 covers turn 2, the first Blood Shots
or Echo).

CPU: 228,391 s (63 CPU-h), 60 s per Heart fight.

## Disclosures and caveats
- One state appears twice (index 501 and 544, `fork-111384715-2`, the run-1 duplicate tar found in #913's review);
  the two copies use different battle seeds. Dropping index 544: 629 states, +12.0 pp [+9.7, +14.5], unchanged.
- Heart search here is learned stop (≤ 10k per root, one-action roots unsearched), not production's flat 40k Act-4
  strong budget. The effect is mechanical (Intangible on a 45 or 2×15 hit) and should carry over, but its exact size
  under production search is not measured.
- Card misc and bottled cards are not carried by act4replay (same in every arm).
- The arms force the counter; they do not price what it costs to stall a Shield & Spear turn (HP, potion use). The
  S&S end-state term that would use this must trade that cost against the "one more turn" values above.

## Decision
Per the pre-registered rule: next is a priced Shield & Spear end-state term for the Incense counter (default off,
issue #914), with its own whole-run gate. Building and running it is Philipp's call.
