# Gumbel root with the Muesli-style Q cap at A20 map roots: paired A/B result (2026-10-27)

[PREREG](PREREG.md). RUN_COMMIT `b49bbd33` (code main `9a37d780`, v3 binary `7bb54d7e…`), 16 workers × 4,
queue schedule, launched 00:04Z, verified 04:5xZ 10-27 (`verify.txt`: 512 OK, 0 missing, 0 bad, 16/16 DONE).
Seeds 111381000–111381511. `analyze.py` → [result.json](result.json).

**Result: NOT_SHOWN** (pre-registered rule; not NON_INFERIOR because the Heart CI's lower bound is below −5 pp).

| | A (PUCT 4096, map roots) | B (capped Gumbel SH 2048) | B − A |
|---|---|---|---|
| Heart kills | 142 (27.7%) | 129 (25.2%) | −2.5 pp [−6.7, +1.6], McNemar p = 0.27 (53 B-only, 66 A-only) |
| Reached Act 4 | 43.2% | 38.5% | −4.7 pp [−8.9, −0.5], p = 0.035 |
| Mean floor | 42.7 | 41.8 | |
| Wall per game | 906 s | 564 s | 0.62× |
| Played ≠ prior argmax | 6.5% of searched roots | 12.9% | |

All 512 pairs valid; every searched root is a full-budget map root in both arms (8,132 vs 8,042), none aborted.

**Interpretation.** The cap removes §635's collapse (−11.4 pp there, −2.5 pp here, not significant), so the
uncapped σ term was the main cause of that loss. B still overrules student_sel twice as often as PUCT, and the
secondary endpoint points the same way as §635: fewer runs reach Act 4. Inference: the extra overrides, Q-driven
(within ±1 logit) and Gumbel-sampled, are on average worse than the prior on map roots; the leaf still does not
beat student_sel there. B saves 38% of run wall, but at a possible cost in Heart kills that 512 pairs cannot rule
out. No default change. A Gumbel root that plays the prior's argmax (scale 0) with the cap would isolate the
sampling noise from the Q term; that is a new question and Philipp's call.
