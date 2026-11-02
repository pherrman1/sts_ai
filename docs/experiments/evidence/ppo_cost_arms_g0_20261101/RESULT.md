# PPO cost arms and G0: result, 2026-11-02 (§744)

Pre-registration: [PREREG.md](PREREG.md) (frozen in 45a46940 after review K PASS; K2/K3 dropped and K15 added before
any campaign game, see the amendment there). Analysis: `analyze.py` as frozen, on the 13,312 games (`games.csv`,
`result.json`).

**Verdict: cost arm K15 (200 hallway sims + no learned Silver prior) is admitted and cheapest → PPO self-play combat.
G0: HEART1 (heart1 alone is not worse than student_sel alone) → the PPO net starts from heart1's weights.**

## Data
- 3,072 units (1,024 K seeds 111382000-111383023 USED replays, 2,048 G0 seeds 111372000-111374047 new), 24 cloud
  workers, `verify_campaign.py`: 3,072 OK, 0 missing, 0 bad, 9 duplicate tars (lease re-claims), one run commit
  45a46940. Every game rc 0. Binary d39c2b98 (X1's), student_sel cf6bf7fb, heart1.bin 1e92f2a6.
- Determinism: FB reproduces X1's F1000 on all 1,024 seeds (same Heart outcome and floor).

## Cost arms: Heart kills F − R paired over 1,024 seeds (95% seed bootstrap)

| Arm | R | F | D = F − R | Verdict | CPU vs B | Mean CPU/game R / F | DiD vs X1 1000 |
|---|---|---|---|---|---|---|---|
| K1 200 hallway sims | 11.5% | 14.8% | +3.32 [+1.07, +5.57] | VALID | 0.76 | 15.6 / 18.2 s | −1.17 [−4.20, +1.76] |
| K4 no boss prior playouts | 10.4% | 14.9% | +4.49 [+2.44, +6.64] | VALID | 0.30 | 6.1 / 7.0 s | 0.00 [−2.54, +2.54] |
| K5 no learned prior | 9.3% | 12.1% | +2.83 [+0.68, +4.88] | INCONCLUSIVE (point < +3.03) | 0.26 | 5.2 / 6.1 s | −1.66 [−4.69, +1.27] |
| K15 = K1 + K5 | 7.4% | 10.9% | +3.52 [+1.66, +5.37] | VALID | 0.16 | 3.2 / 4.1 s | −0.98 [−3.71, +1.76] |
| B (X1 F1000, FB) | 12.3% | 16.8% | +4.49 (X1) | | 1 | — / 22.2 s | |

Admitted: K1, K4, K15; chosen as pre-registered (cheapest admitted): **K15**, ~6× cheaper than B per game.

## G0: heart1 alone vs student_sel alone (F keys, base combat, 2,048 paired new seeds)
- Heart kills student_sel 16.3%, heart1 16.1%, D −0.24 pp [−2.00, +1.51] → **HEART1** (CI upper bound not < 0).
- Act 3 cleared −0.78 pp [−2.93, +1.32]; mean floor −0.18. CPU per game 22.2 / 23.5 s.

## Reading
- Boss prior playouts are most of B's cost: dropping them alone (K4) cuts CPU to 30% and keeps the key effect intact
  (DiD 0.00). The learned prior and the 200-sim hallway fights cost a further half.
- Levels drop with cheaper combat (F: 16.8% B → 14.9% K4 → 10.9% K15). For PPO this means fewer Heart kills to learn
  from per game, but ~6× more games per core: per core-hour K15 yields ~3.5× the Heart kills of B. The admission test
  covers one OOC effect (mostly the act-1 Sapphire key), not card or path choices whose value depends on fight skill.
- K5 alone is INCONCLUSIVE while K15 (K5 + K1) is VALID: both have overlapping CIs; the rule is applied as frozen.
- G0: heart1, trained on mixed ascensions in another engine, plays A20 here as well as our distilled student; the
  d256 net needs no distillation step.

## Decision (as pre-registered)
PPO recipe screen (`ppo_recipe_screen_20261101`) runs with combat K15 and start net heart1. Every adopted PPO result
is still confirmed at production combat before it becomes a default.

## Cost
13,312 games; ≈ 37 core-h (cloud). Seeds: 111372000-111374047 now USED (G0); smokes 111386992-993 USED.
