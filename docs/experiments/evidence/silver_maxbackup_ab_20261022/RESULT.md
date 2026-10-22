# Result: max backup + block-first vs production Silver, A20 fight level (2026-10-22)

**Primary label (fix10000 − base10000, all fights): score NOT_SHOWN, HP lost NOT_SHOWN.
Secondary label (fix10000 − matched; matched arm = base12000, per-fight CPU ratio 1.009): score NOT_SHOWN,
HP lost WORSE.** The candidate does not carry its first-fight gain into whole runs. The point estimates go the
wrong way everywhere except elites, and they are worst on bosses.

64 sources (111149400–463), 723 valid replayed fights (274 normal, 295 elite, 128 boss, 26 other, 11 Act 4),
R = 2. Seed bootstrap, 95% CI. One invalid arm row was excluded.

| contrast (all fights) | score | win | HP lost |
|---|---|---|---|
| fix10000 − base10000 | −2.08 [−4.90, +0.64] | −0.005 [−0.015, +0.005] | +0.28 [−0.28, +0.86] |
| fix10000 − base12000 (matched) | −1.94 [−4.16, +0.34] | −0.003 [−0.011, +0.006] | **+0.50 [+0.04, +0.99]** |
| fix10000 − base15000 | −1.93 [−4.36, +0.48] | −0.003 [−0.012, +0.005] | +0.36 [−0.06, +0.79] |
| base12000 − base10000 | −0.13 [−1.86, +1.58] | −0.002 | −0.22 [−0.58, +0.13] |
| base15000 − base10000 | −0.15 [−2.37, +1.98] | −0.001 | −0.08 [−0.48, +0.32] |

Bosses (128 fights):
- fix − base10000: score −8.1 [−21.5, +4.7], HP +1.37 [−0.77, +3.80].
- fix − base12000: score −9.4 [−19.8, +1.1], HP **+2.16 [+0.01, +4.40]**.
- fix − base15000: score **−11.4 [−22.9, −0.2]**, HP **+2.67 [+0.79, +4.60]**.

Elites, fix − base12000: score +0.03 [−1.95, +2.29], win +0.007 [+0.002, +0.014]. Normals: score −0.72
[−1.95, +0.21]. All subsets are descriptive.

CPU:
- fix10000 / base10000 is 1.216 per fight [1.19, 1.24] and 1.157 per simulation.
- fix10000 / base12000 is 1.009 per fight, so base12000 is the matched arm. fix10000 / base15000 is 0.793.
- Mean playout length: 17.1 actions vs 15.7.

**Reading.**
1. On starter-deck first fights the candidate halved exact regret. Across whole runs it is at best neutral and
   costs HP on bosses.
2. **Inference** (no exact solve exists for these fights): the block-first rule and the optimistic max backup
   favour long, defensive lines. In boss fights that scale (damage race, Guardian/Slime Boss/Act 2-3 bosses)
   that is the wrong bias, and the exact benchmarks never measured it.
3. No detectable gain from extra simulations for production Silver at 10k: 12k and 15k are within ±0.2 points
   (CIs about ±2).

**Decision.** The flags stay default off. This ends the max backup + block-first candidate as specified. Any
follow-up would need a fight-type gate or a boss-level exact benchmark first.

Run: RUN_COMMIT 661602c8, code main c4dcb43c, binary 5d840679 (v3), 32 workers (W14 never started), queue
schedule. Units 445 and 446 were taken over after two containers stopped. `verify_campaign.py`: OK 64 / 64,
no duplicates. Tars: `/mnt/project-files/silver-maxbackup-ab/units/` (sha256 in `tars.sha256`). Analysis:
`python3 analyze.py result.json <extracted>/out/units/*`.
