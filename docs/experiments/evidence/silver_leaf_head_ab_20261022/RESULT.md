# Result: learned leaf head capped at win-now vs production Silver, A20 fight level (2026-10-23)

**Primary label (head10000 − base10000, all fights): score NOT_SHOWN, HP lost NOT_SHOWN. Secondary label
(head10000 − matched; matched arm = base12000, per-fight CPU ratio 0.938): score NOT_SHOWN, HP lost NOT_SHOWN.
Step-3 gate: FAIL** (the matched score contrast's CI lower bound is −2.78, the bar −1; boss score and HP lost are not
WORSE). No whole-run A/B is proposed for this candidate. The head gains a little on normal fights and loses on elites
and in Acts 3-4.

256 sources (111350000–255), 2,895 valid replayed fights (1,021 normal, 1,209 elite, 553 boss, 112 other; 74 in
Act 4), R = 2. Seed bootstrap, 95% CI. 17 fights were excluded for escapes, as pre-registered.

| contrast (all fights) | score | win | HP lost |
|---|---|---|---|
| head10000 − base10000 | −0.90 [−2.31, +0.52] | −0.004 [−0.009, +0.001] | −0.16 [−0.48, +0.17] |
| head10000 − base12000 (matched) | −1.31 [−2.78, +0.14] | **−0.005 [−0.010, −0.001]** | −0.07 [−0.37, +0.25] |
| head10000 − base15000 | −1.39 [−2.90, +0.10] | **−0.006 [−0.011, −0.001]** | −0.17 [−0.46, +0.12] |
| base12000 − base10000 | +0.41 [−0.51, +1.34] | +0.001 [−0.002, +0.005] | −0.09 [−0.30, +0.11] |
| base15000 − base10000 | +0.49 [−0.61, +1.60] | +0.002 [−0.002, +0.006] | +0.01 [−0.20, +0.22] |

By room and act, head10000 − base12000 (descriptive):

| fights | score | win | HP lost |
|---|---|---|---|
| normal and other (1,133) | +0.36 [−0.47, +1.14] | +0.000 [−0.003, +0.003] | **−0.38 [−0.63, −0.11]** |
| elite (1,209) | **−2.43 [−4.87, −0.04]** | **−0.009 [−0.016, −0.001]** | −0.05 [−0.54, +0.44] |
| boss (553) | −2.28 [−8.20, +3.91] | −0.009 [−0.029, +0.011] | +0.53 [−0.67, +1.71] |
| Act 1 (1,352) | +0.52 [−0.95, +2.00] | +0.001 [−0.004, +0.007] | −0.28 [−0.59, +0.03] |
| Act 2 (893) | −1.31 [−4.30, +1.46] | −0.008 [−0.018, +0.002] | −0.14 [−0.68, +0.40] |
| Act 3 (576) | **−4.30 [−8.46, −0.44]** | −0.010 [−0.023, +0.002] | +0.75 [−0.24, +1.69] |
| Act 4 (74) | −11.3 [−33.9, +12.8] | −0.061 [−0.133, +0.014] | −1.67 [−5.37, +2.06] |

Fight win rate per arm (replicates of the counted fights, `describe.txt`), head10000 against production at 10k, 12k
and 15k: all 92.7% vs 93.1, 93.2, 93.2%; normal 98.4 vs 98.2, 98.4, 98.3; elite 94.0 vs 94.8, 94.8, 95.1; boss
78.0 vs 78.8, 78.9, 78.8; Act 4 67.6 vs 73.0, 73.6, 73.6 (74 fights); the Heart 40.0 vs 45.7, 47.1, 48.6 (35 fights).

CPU:
- head10000 / base10000 is 1.127 per fight [1.106, 1.149] and 1.092 per simulation.
- head10000 / base12000 is 0.938 per fight, so base12000 is the matched arm; head10000 / base15000 is 0.748.
- Decisions per fight 52.4 vs 50.8 (boss 90.9 vs 88.3, Act 3 70.3 vs 67.8). Mean playout length 16.7 vs 16.3 actions.

Stalls: 12 fights in which head10000 took more than twice production's decisions (6 normal, 2 elite, 4 boss), none
like the uncapped head's. In four, production died in both redraws and the head lived longer (it won Shield and
Spear 21/33 and Awakened One 22/2 and one Reptomancer redraw, and lost Donu and Deca too). Six are short hallway
fights (10-18 decisions for production) that the head played twice as long, four of them for more HP (three Jaw
Worms, e.g. 64/64 against 61/61, and a Large Slime) and two for less (Shelled Parasite 45/32 against 45/45, Snake
Plant 73/78 against 84/84). Two are boss fights both arms won: Slime Boss 28/34 against 26/26, Collector 51/37
against 72/49.

**Reading.**
1. The head helps where the first-fight test measured it: in normal fights it loses 0.38 HP less than production at
   matched CPU. It loses in elites (score −2.4, 0.9 percentage points more elite losses) and late in the run (Act 3
   score −4.3; Act 4 wins 67.6% against 73.6%, 74 fights).
2. The same pattern as §638 (max backup + block-first) and as the win-now blend's smoke
   (`../silver_leaf_winnow_blend_20261023`): gains in short fights, losses in long fights that scale. **Inference**,
   not tested here: the head's cap binds at about 60% of first-fight leaves, so much of its value is win-now, which
   ignores the damage still to come; the uncapped head stalls instead (PREREG background).
3. Production gains nothing measurable from 12k or 15k simulations at 10k (+0.4 and +0.5 points per fight, CIs
   about ±1).

**Decision.** The gate failed: no whole-run A/B for this candidate, and `STS_SILVER_LEAF_HEAD` stays default off.
The exact first-fight benchmark does not predict long fights; a further leaf candidate needs a long-fight check
(elites, bosses, Acts 3-4) before any fight-level A/B.

Run: pre-launch review PASS (03:04Z). RUN_COMMIT 420026c2, code 75afdee0, binary 83de6c12 (v3), 8 workers, queue
schedule, wall 05:39-12:08Z. Worker 8 hit the session limit at launch and joined at 07:34Z. The manifest said
`workers 32`, so three quarters of the units waited the 15-minute claim settle before running. `verify_campaign.py`:
units OK 256, MISSING 0, BAD 0, duplicates 0, one run commit. Tars: `/mnt/project-files/silver-leaf-head-ab/campaign/units/`
(sha256 in `tars.sha256`). Analysis: `python3 analyze.py result.json <extracted>`; descriptive extras
`python3 describe.py <extracted>` (`describe.txt`).
