# Counters-only price table at Shield & Spear: result

PREREG: [PREREG.md](PREREG.md) (J prelaunch PASS). RUN_COMMIT `119c5a05`, binary `a7c9a729…`, 40 workers,
2026-11-05 23:54 CET - 2026-11-06 00:41 CET. Analysis: `analyze.py` → `results/analysis.json`; stage C set = all
1,024 stage C units (share `price-table-stagec/units/`, all delivered).

## Deliveries
1,007 of 1,056 unit tars at analysis time: all 32 sentinel units and 975 of 1,024 C units, all rc 0, 0 bad rows, 0 dropped. The run
stalled for ~25 min when the share reached its 50,000-file limit (claim `mkdir` failed with EIO); Philipp approved
deleting stage C's `claims/` (00:23 CET), and the run resumed. At 00:30 CET Philipp stopped it to free the workers;
the other 49 C units were unfinished at analysis time. Units already in flight kept finishing after the stop (982 C
units on the share at J's review); with them the gate is unchanged (PASS at 256, LLR 3.04) and C − D is +2.42
[+1.18, +3.70]. The gate had crossed before, so the missing units cannot change the verdict.

## Sentinel
32/32 sentinel units: every D row equals stage C's except the CPU columns → stage C's D/T/I runs are a valid control.

## Primary
Sequential gate C − D (gainer, α = β = 0.05, look 64, key = rank in stage C's order): **PASS**, H1 accepted at the look
at 256 states (LLR 3.04 ≥ 2.94; mean +3.0 pp). Looks: 64 → 0.86, 128 → 1.18, 192 → 1.84, 256 → 3.04.
Descriptive on all 975 analysed states: D 54.59%, T 56.28%, C 57.03%; C − D +2.44 pp [+1.14, +3.70], C − T +0.74
[−0.45, +1.92].

## Secondary (descriptive)
- Incense states (561): D 56.64%, T 61.32%, I 62.48%, C 61.36%. C − D +4.72 [+2.90, +6.64], C − T +0.04
  [−1.56, +1.64], C − I −1.11 [−2.77, +0.52]. Aligned counter at the Heart: D 61%, T 87%, I 94%, C 89%.
- Other states (414): D 51.81%, T 49.46%, C 51.15%. C − D −0.66 [−2.11, +0.81], C − T +1.69 [−0.12, +3.49].
- Potions used in S&S: D 0.86, T 1.00, C 0.84; S&S death D 4.85%, T 5.23%, C 4.85%; HP left after an S&S win
  D 66.5, T 64.2, C 65.6.

## Interpretation (inference)
Model A's counter prices are what helps; its HP and potion prices are what hurt in §757. C keeps T's Incense gain
(C − T +0.0 on Incense states) and drops T's loss on the other states (C − D −0.7, neutral; potion use as D).
On Incense states §724's hand-built term remains slightly better (C − I −1.1, not significant).

**Caveat (review J N1):** C was designed after seeing §757, and C − D reuses §757's D runs, whose noise is part of
§757's T − D split. The PASS is therefore conditional on that sample and needs confirmation on new seeds before any
further step (e.g. a whole-run SPRT at S&S).

## Decision (pre-registered)
PASS → reported; a counters-only table is the candidate for a whole-run test at S&S, proposed to Philipp, after a
new-seed confirmation (N1). No default change.
