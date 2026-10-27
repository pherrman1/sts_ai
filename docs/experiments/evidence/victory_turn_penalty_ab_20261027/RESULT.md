# #880 Silver victory turn penalty A/B: result (INCONCLUSIVE at 64 pairs, stop)

Run commit `3febdd0` (code `67d2dc1`), binary sha256 `21bc7308…`, student_sel `cf6bf7fb…`; `run_all.sh` on this
thread's 4-CPU cloud container, 4 lanes. Philipp's go 2026-10-27 20:37Z; prelaunch review PASS (code, design and the
3febdd0 delta). Campaign 111386000–031 20:38–22:04Z (64/64 games rc 0) → INCONCLUSIVE → pre-registered extension
111386032–063 22:05–23:47Z (64/64 rc 0). All 64 pairs valid. Raw unit files (one directory per seed):
`/mnt/project-files/victory-turn-penalty-ab/victory_turn_penalty_ab_campaign.tar` (sha256 `cbd34c03…`).
`result-32.json` = first 32 seeds, `result.json` = all 64 (`python3 -I analyze.py OUT units.txt units-extension.txt`).
A = victoryTurnPenalty 0.4 (main), B = 0.

## Outcomes (64 paired seeds)

| | A (0.4) | B (0) | B − A |
|---|---|---|---|
| Heart kills | 17 | 19 | +3.1 pp [−7.8, +14.1]; discordant B-only 7 / A-only 5, McNemar p 0.77 |
| Act-4 arrival | 29 | 26 | −4.7 pp [−17.2, +7.8] |
| kills per Act-4 arrival | 59% | 73% | (descriptive; the Heart fight itself is identical by construction) |
| mean final floor | 41.92 | 39.53 | −2.39 [−5.92, +1.06] |
| losses by final act 1 / 2 / 3 / 4 | 11 / 11 / 13 / 12 | 13 / 13 / 12 / 7 | |
| mean wall per game (s) | 330 | 308 | 0.93x |

First 32 seeds alone: Heart 7 vs 10 (B-only 4 / A-only 1), floor +0.19 [−4.7, +5.1].

## Combat length (all real combats; trace `turns` is 0-based, player turns = +1)

| | A | B |
|---|---|---|
| combats (won) | 1,486 (1,439) | 1,397 (1,352) |
| mean / median / p90 / p95 / max turns | 3.99 / 3 / 7 / 9 / 20 | 4.16 / 3 / 8 / 9 / 33 |
| NORMAL mean (p95, max) | 2.90 (5, 9) | 3.02 (6, 19) |
| ELITE mean (p95, max) | 4.54 (9, 17) | 4.57 (8.7, 20) |
| BOSS mean (p95, max) | 7.34 (11.7, 20) | 8.08 (13, 33) |
| combats ≥ 30 turns | 0 | 1 (Champ, won in 33) |
| turn cap / undecided | 0 | 0 |
| Smoke Bomb escapes | 4 | 4 |

By act × room, B is longer in 9 of 10 act-1–4 NORMAL/ELITE/BOSS cells, by +0.05 to +0.79 turns; bosses carry most of
it (act 1 +0.79, act 2 +0.57, act 3 +0.63, act 4 +1.17).

**Paired first divergence:** 63 of 64 seeds diverge, all first at a combat with the same pre-combat state (1 seed
identical throughout). Turns B − A +0.14 [−0.17, +0.43] (B longer in 28, shorter in 18); HP after +0.49 [−0.95, +1.84];
potions after +0.03 [−0.05, +0.11]; won A 61 / B 60. By room: NORMAL +0.24 [−0.09, +0.58], ELITE +0.16 [−0.40, +0.68].

**Human context (not a criterion):** Baalorlord's 676 Ironclad A20 runs (`expert_turns.json`, .run turns are
1-based) average 4.09 / 4.80 / 7.89 player turns in normal / elite / boss fights; the bot plays 3.90 / 5.54 / 8.34 (A)
and 4.02 / 5.57 / 9.08 (B). The bot is already as quick as the expert in hallway fights and slower in elite and boss
fights, so there is no sign that the 0.4 penalty makes Silver implausibly fast (§701: the bot loses 2–3x more HP than
the expert in elite and boss fights).

## Decision (frozen rule, in order)

- STALL: no (B 0 turn-cap / undecided; ≥ 30-turn combats B 1 vs A 0, rule needs ≥ 3 more).
- WORSE: no (floor CI [−5.92, +1.06] includes 0; Heart A-only − B-only = −2, rule needs ≥ 4).
- LONGER_ONLY: no (mean turns +0.17 < +0.3; the paired first-divergence CI includes 0).
- PROMISING: no (floor point estimate −2.39 < +0.5).
- → **INCONCLUSIVE at 64 pairs: stop.** The 0.4 penalty stays; no default change. SPEED-BIAS flag: not raised.

## Interpretation

Removing the penalty makes Silver's combats slightly longer, almost entirely in boss fights (+0.7 turns on average,
the longest fight 33 vs 20 turns), with no stalling pathology and no measurable gain in HP kept per combat. Whole-run
outcomes point both ways (Heart +3 pp, floor −2.4) and are noise at 64 pairs. **Inference:** the term is small
relative to Silver's HP and potion terms (0.4 per turn vs 1 per HP) and is not what limits the bot; a fight-level
paired harness (`ctmsilvergen`-style redraws) would be the cheaper way to resolve a ±0.2-turn / ±1-HP effect if this
is revisited, e.g. for certified infinite engines (#880 decision rule).
