# P300 clairvoyance 2x2: result

Run commit `cd34ba1f`, code `4e3783bf` (ADR-0062), binary `2750c38d…` (x86-64-v3); 2 cloud workers x 4 lanes,
2026-10-26 22:51Z to 2026-10-27 04:1xZ. `verify_campaign.py`: 384/384 units OK, 0 missing, 0 bad, DONE.json 2/2.
4,528 fights per cell (18,112 in all), 0 invalid, 0 `[known-rng]` messages, 0 invalid-action dumps.
CPU: Fnat 14.1, Ffull 15.1, Knat 2.6, Kfull 3.0 core-h (34.8 in all). Numbers: `analysis.json` (`analyze.py`, deck
bootstrap 2,000, seed 20261026). All effects in pp; 95% CIs in brackets.

## Primary: D = top-5 adds minus bottom-5 adds, per cell

| Cell | Base win | D | Top-5 mean | Bottom-5 mean |
|---|---|---|---|---|
| Fnat (fair, natural HP) | 51.6% | **+6.0** [+3.8, +8.3] | +7.1 | +1.1 |
| Ffull (fair, full HP) | 61.7% | **+5.2** [+2.9, +7.6] | +8.3 | +3.1 |
| Knat (known RNG, natural HP) | 73.4% | **+4.1** [+2.3, +6.0] | +6.0 | +2.0 |
| Kfull (known RNG, full HP, P300's regime) | 85.7% | **+2.7** [+1.2, +4.4] | +1.4 | −1.2 |

Main effects on D: clairvoyance C = −2.2 [−4.4, 0.0]; full HP H = −1.1 [−2.2, +0.1]; C x H = −0.6 [−3.5, +2.1];
D(Kfull) − D(Fnat) = −3.3 [−6.0, −0.6].

**Pre-registered readings that fire:** R1c (D(Kfull) < 3 but D(Knat) ≥ 3: the Kfull ceiling compresses the effect, not a
non-replication) and **R4** (D(Fnat) ≥ 4: Stage A's random key sampling missed a real top-vs-bottom gap; a fixed-key
fair table is worth building). R1, R2 and R3 do not fire.

## Secondary (single variants)

Single-variant effects share the base variant's sampling error (about 2.5 pp per cell, common to every effect in the
cell), so mean add, single keys and rm:Strike sit about 3 pp higher in Fnat than in §684 (base 51.6% here vs 54.7%
there, other seeds). D cancels it.

| Variant | Fnat | Ffull | Knat | Kfull |
|---|---|---|---|---|
| Corruption | +10.9 | +12.8 | +8.6 | +4.7 |
| Feel No Pain | +8.1 | +9.9 | +8.1 | +2.6 |
| Barricade | +6.8 | +7.3 | +4.4 | −0.5 |
| Impervious | +4.9 | +5.7 | +4.9 | +0.5 |
| Demon Form | +4.7 | +6.0 | +4.2 | −0.3 |
| Immolate | +2.6 | +5.5 | +0.8 | −1.0 |
| Rampage | +2.1 | +3.9 | +1.8 | −1.8 |
| Anger | +1.0 | +0.5 | +2.9 | −1.0 |
| Wild Strike | +1.0 | +1.6 | +3.4 | −0.8 |
| Whirlwind | −1.3 | +4.2 | +1.0 | −1.6 |
| mean add | +4.1 | +5.7 | +4.0 | +0.1 |
| rm:Strike (76 decks) | +4.9 | +2.3 | +1.0 | −0.7 |

Single-key CIs are about ±4.5 pp (see `analysis.json`).

## Reading

- **P300's ordering is real in fair play.** In our engine, on our decks, with fair Silver at natural HP, P300's top 5
  beat its bottom 5 by 6 pp. Corruption and Feel No Pain lead; Whirlwind is last. §684's "Impervious 0.0 / top-5
  pooled +0.3" came from about 20 random decks per key and a different base draw, not from a missing effect.
- **Clairvoyance does not inflate these values; it shrinks them.** D falls from fair to known RNG at both HP levels
  (C = −2.2). The steepest drop is the Kfull ceiling: at 86% base win, all adds move toward 0. Full HP alone changes D
  little (H = −1.1).
- **P300's magnitudes (+10 to +14 per top card) do not transfer as absolute numbers.** Their mean add +3.7 sits on a
  68% base in their regime; in ours the per-card effects depend on base win, and the ranking is what carries over.
- **Inference:** a fixed-key fair Heart table (R4) would have usable signal for the strongest power/defence keys. Its
  size and whether it beats student_sel's card picks are open; that is a separate decision.

Seeds: 111304600–111304983 (shared by every cell and variant, and by the calibration of 2026-10-26).
