# Stage C result: §746 model A as Silver's Shield & Spear win leaf through the price table

Pre-registration: [../PREREG-stageC.md](../PREREG-stageC.md) (frozen, J prelaunch PASS). Campaign: this directory,
RUN_COMMIT `47a5289c`, binary `4ace2751…`, 40 workers (Philipp 2026-11-05 20:05 CET), run ≈ 20:50-22:58 CET.
Analysis: `analyze.py` → `results/analysis.json`.

## Deliveries and deviation
1,021 of 1,024 units on the share (unit tars sha256-of-sha256 list `191d5078…`), all rc 0, 0 bad rows, 0 invalid
runs. Units 170, 439 and 447 were on their second attempt after container restarts when Philipp said at 22:58 CET
"lass einfach die 3 einheiten ignorieren und jz auswertung machn"; they are counted as dropped (whole unit, every
arm, P4) and never analysed. This is the only deviation from the PREREG. Units 170 and 439 finished afterwards
(23:00 / 23:03 CET; d = 0 in both gates); with them T − D stays +1.59 pp [−0.05, +3.22]. Unit 447 was still running:
T − D would turn PASS only if that one state's T − D were ≥ +0.75 (true for 10 of the 1,023 finished states). 1,021 states from 534 source seeds
(589 Incense states / 185 seeds, 432 others / 352 seeds).

## Primary (co-primary gates, gainer, α = 0.025 each)
| | Heart kill | − D | 95% CI | 97.5% CI | gate |
|---|---|---|---|---|---|
| D | 55.04% | | | | |
| T | 56.64% | +1.59 pp | [+0.15, +3.02] | [−0.05, +3.23] | CAP (LLR 2.54 < 3.66) → **INCONCLUSIVE** |
| TA | 56.29% | +1.25 pp | [−0.24, +2.71] | [−0.45, +2.92] | CAP (LLR 1.05) → **INCONCLUSIVE** |

Neither gate crossed a bound by the cap (1,021 units); the 97.5% fixed-sample CI includes 0 for both.
First copy of each distinct state (936): T − D +1.26 [−0.16, +2.66], TA − D +0.80 [−0.67, +2.27].

## Secondary and co-reported (descriptive)
- **Incense states (589):** D 57.13%, T 61.67%, TA 61.76%, I 63.03%, TI 61.97%. vs D: T +4.54 [+2.51, +6.56],
  I +5.90 [+4.15, +7.73]. vs I: T −1.36 [−2.99, +0.27], TA −1.27 [−2.86, +0.33], TI −1.06 [−2.58, +0.47].
  Aligned counter (0/1/3/4) at the Heart: D 61.8%, T 87.0%, TA 87.3%, I 93.7%, TI 92.9%. T moves the counter to
  3/4 (S&S wins ending on 3: 655, on 4: 806 of 2,251), I mostly to 1/4 (692 / 1,130).
- **Other states (432):** D 52.20%, T 49.77% (−2.43 [−4.20, −0.70]), TA 48.84% (−3.36 [−5.27, −1.49]).
  S&S death D 5.32%, T 6.08%, TA 6.37%; potions used in S&S 0.80 / 0.92 / 0.93; HP left after an S&S win
  66.7 / 65.4 / 65.0.
- **All states:** S&S death 4.75 / 5.14 / 5.31%; Heart kill given an S&S win 56.2 / 58.1 / 57.8%; HP left after an
  S&S win 66.5 / 64.2 / 64.1; potions used 0.86 / 1.01 / 1.01; S&S turns 4.57 / 4.87 / 4.86; CPU per run
  42.8 / 41.5 / 40.2 s.
- **Anchor:** at the floor TA = T in all 706 such states (0 differing runs, determinism check). Where it is not at
  the floor (315 states) TA − T −1.11 [−3.19, +0.92].
- No table fell back to the default leaf (no flat HP curve).

## Interpretation (inference)
The table is not a better S&S leaf than the default overall. Two effects nearly cancel: model A's counter prices
recover most of §724's Incense gain (+4.5 of +5.9 pp, aligned counter 87% vs 94%), but on states without a counter
to price the table plays worse (−2.4 pp): Silver spends more potions and HP in S&S and dies there more often, which
is §746's calibration finding (model A prices HP and potion changes wrongly at the margin) showing up in play.
Anchoring the win bonus to the model does not help. Model A is good enough for the Incense phase and not for HP and
potions; better prices need the paired fight-end labels of the leaf plan (thread A), not a finer table format.

## Decision (pre-registered)
INCONCLUSIVE → reported; the table flag stays research-only; stage 2's labels decide the next model. §724's term
stays the better Incense treatment (TI − I −1.06 pp: the table adds nothing on top of it). Not pre-registered and not
run: a counters-only table (counter prices from the table, HP / potions from the default leaf) would test the
"Incense yes, HP/potions no" reading directly; needs Philipp's go.
