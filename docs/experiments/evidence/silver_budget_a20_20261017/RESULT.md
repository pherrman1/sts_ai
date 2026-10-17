# A20 Silver budget test: result (2026-10-17)

Run commit d83b4ab9, code e413c1f3, binary a6ad3c56; 8 workers, seeds 111135100-111135611, 512 seeds x 3 arms,
1,536 units, all rc 0, no seed failures; all 512 seeds valid. Tars: `/mnt/project-files/audit-2026-10-17/
silver-budget-a20/runs/wWW.tar.gz` (sha256 in `worker_tars.txt`, each checked in a second container).
Analysis: `python3 tools/analyze_silver_budget_a20.py report <8 extracted out dirs>` -> `report.json`.

## Wins (Heart kills) and Act 4

| Arm | Heart kills | Reached Act 4 | Kills / Act 4 | Mean floor | CPU per run |
| --- | ---: | ---: | ---: | ---: | ---: |
| F flat 10k | 27/512 (5.3%) | 77 (15.0%) | 35% | 32.1 | 53.5 s |
| L learned stop | 30/512 (5.9%) | 75 (14.6%) | 40% | 30.6 | 21.9 s (0.41x) |
| LP learned stop + g6 prior | 27/512 (5.3%) | 97 (18.9%) | 28% | 33.2 | 28.2 s (0.53x) |

Paired differences (Newcombe method 10, 95%):
- **Primary, reached Act 4:**
  - L − F: −0.4 pp [−3.4, +2.6]. NON_INFERIOR (lower bound > −5 pp); exact McNemar p = 0.90.
  - LP − F: +3.9 pp [+0.4, +7.4]. NON_INFERIOR; McNemar p = 0.035.
    The gain was not a pre-registered hypothesis, so it is reported, not claimed.
- **Heart kills (secondary):**
  - L − F: +0.6 pp [−1.7, +2.9]; p = 0.73.
  - LP − F: 0.0 pp [−2.3, +2.3]; p = 1.0.
- **LP vs L (descriptive):** Act 4 +4.3 pp [+1.0, +7.7], p = 0.015; Heart kills −0.6 pp [−2.8, +1.6].

**Reading.** Learned stopping plays as well as flat 10k at A20 on both endpoints, at 0.41x the run CPU.
Adding the gen-6 prior reached Act 4 more often than F, but the extra Act-4 runs did not turn into more
Heart kills: 27 for both LP and F. **Inference:** the prior helps Acts 1-3 combats, while the Act-4 fights
(Shield and Spear, Heart) gain nothing from it. That needs a targeted check before any claim.

## Out-of-combat decision sources (all 512 seeds)
| Arm | student C (heart1) | key rule | Match and Keep |
| --- | ---: | ---: | ---: |
| F | 43,775 | 1,253 | 310 |
| L | 41,883 | 1,140 | 290 |
| LP | 45,251 | 1,329 | 250 |

Student C made about 97% of the OOC decisions. The key rule made most of the rest, and the remainder were Match and
Keep, whose card choices come from the V4 chain (#616 moves them to student C). Nothing went through the
heuristic chain.

Knowledge impact: experiment result; ledger entry pending a § number from the coordinator.
