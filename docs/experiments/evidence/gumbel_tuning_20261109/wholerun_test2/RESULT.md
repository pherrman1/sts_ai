# Gumbel tuning whole-run Test 2: node reuse cap 262,144, G16CAP against §775's G16 + mb4 (result)

Pre-registration: [../wholerun/PREREG.md](../wholerun/PREREG.md) ("Test 2"), launch notes [README.md](README.md).
Analysis: `../wholerun/analyze.py` as frozen with the PREREG (its `test2` part), output `results/result.json`.
Descriptive breakdown: `breakdown.py` (not pre-registered), output `results/breakdown.json`.

## Run

- Run commit 144b02a7 (code 13bb97ec, binary b5090b16, Test 1's), 40 workers × 4 lanes, queue. The first game
  started at 00:35 CET and the last ended at 04:40 CET on 2026-11-10. The 1,024 counted games sum to 142.5 lane-hours
  (PREREG: about 165); the median game took 5.4 min. One game ran over 1 h: G16CAP-111379213, 2 h 11 min (1,370
  Gumbel roots, 19.1 M simulations, died on floor 50; §775's G16 died on floor 24 on that seed).
- Container resets killed running attempts; their claims were released once their heartbeat was over 6 min stale
  (one claim without any heartbeat by its directory age) and the units re-ran from the start: 1,024 units claimed as
  `.a1`, 22 as `.a2`, 6 as `.a3`, 4 as `.a4` (claims snapshot `results/claims.txt`; `claims/` removed after it). The
  35 workers released before the tail ended wrote no DONE file (5 of 40 present).
- `verify_campaign.py`: 1,024 of 1,024 units OK, 0 missing, 0 bad, 0 duplicates, 0 tars for unknown units, all on
  run 144b02a7.
- `analyze.py` (NEW_UNITS = Test 1's 1,056 and this campaign's 1,024 extracted units, REF_UNITS = §775's D, G16, G32
  units, CLAIMS_LIST = both claims snapshots): 0 bad games, 0 env mismatches, 0 combat aborts, 0 dropped seeds.

## Sentinel and control reuse

Test 1's 32 of 32 sentinel G16 games are identical to §775's: **REUSE_VALID**. §775's 1,024 G16 games are the control.

## Primary

| | G16 + mb4 (§775) | G16CAP |
|---|---|---|
| node reuse cap (acts 1-3, Shield and Spear) | 32,768 | 262,144 |
| Heart kill | 41.21% | **38.28%** |
| reach Act 4 (floor ≥ 52) | 49.22% | 47.85% |
| mean final floor | 41.58 | 40.84 |
| CPU per run | 512 s | 501 s (0.98×) |

G16CAP − G16 = **−2.93 pp [−5.66, −0.20]** (95% seed bootstrap, 10,000 resamples), 85 seeds only G16CAP kills, 115
only G16. SPRT gainer (H1 +2 pp, alpha 0.05, beta 0.05, look 64): accepts H0 at 704 seeds (LLR −3.34) →
**NOT_SHOWN**. The nonregression variant reaches CAP at 1,024 (LLR −1.72). All seeds ran (PREREG).
Act-4 reach −1.37 pp [−4.00, +1.37]; final floor −0.74 [−1.61, +0.11].

## Secondary

- Tree reuse (exit line `[silver] whole-run tree reuse:`): G16CAP's cap resets 13 of 497,562 kept-or-reset reroots
  (0.003%), visits lost to them 0.02% of all simulations, visits carried 43.6%. The 32 sentinel G16 games at the
  32,768 cap: 4.50%, 3.90%, 34.3%. The larger cap removes the resets and carries about 9 points more of the
  simulations, at the same CPU.
- Test 1's numbers are unchanged by the added units (C2 − G16 −4.69 pp, C2 − D +4.88, C2 − G32 −4.30; §777).

## Where G16CAP loses (descriptive, not pre-registered)

`breakdown.py`: deaths by section of the final floor, hazard = deaths among runs reaching the section, G16CAP − G16
with a 95% seed bootstrap (4,000 resamples), as Test 1's breakdown.

| section | G16CAP | G16 | G16CAP − G16 (pp) |
|---|---|---|---|
| act 1, floors 1-15 | 102 / 1,024 | 96 / 1,024 | +0.6 [−1.1, +2.1] |
| act-1 boss (16) | 93 / 922 | 89 / 928 | +0.5 [−1.4, +2.3] |
| act 2, floors 17-32 | 136 / 829 | 129 / 839 | +1.0 [−1.4, +3.4] |
| act-2 boss (33) | 71 / 693 | 63 / 710 | +1.4 [−1.0, +3.7] |
| act 3, floors 34-49 | 54 / 622 | 60 / 647 | −0.6 [−3.2, +2.1] |
| act-3 boss 1 (50) | 38 / 568 | 43 / 587 | −0.6 [−2.9, +1.8] |
| act-3 boss 2 (51) | 40 / 530 | 40 / 544 | +0.2 [−2.6, +3.0] |
| act 4 (52-56) | 98 / 490 | 82 / 504 | +3.7 [−0.1, +7.8] |

No section's interval excludes 0. In Act 4 the deaths on floor 56 (the Heart) are 86 of 478 Heart arrivals for G16CAP
and 73 of 495 for G16 (kills per Heart arrival 82.0% vs 85.3%); on the 401 seeds where both reached Act 4, G16CAP
kills the Heart 331 times and G16 344 times. The Heart fight itself already had the 262,144 cap in both arms, so a
difference there comes through the state on arrival (the Shield and Spear fight, played with the larger cap, and
everything before). The whole-run logs hold no HP per fight, so this cannot be split further here.

## Reading (Inference)

- The larger cap works as intended mechanically (no cap resets, more of the tree carried) and does not raise the Heart
  rate: the SPRT accepts H0, and the 95% interval [−5.66, −0.20] holds no gain at all. The point estimate is
  negative and the interval just excludes 0. That was not a pre-registered harm test, and several 95% intervals
  have been read in this test family, so the reading is "no gain, possibly slightly worse", not a shown loss.
- A possible mechanism (hypothesis, not measured): a carried subtree holds the previous search's statistics, visits
  concentrated on the lines that search preferred under its own Gumbel noise and max-backup values. With more carried
  visits, the new root's 16,000 fresh simulations correct less of that.
- For the budget curve's plateau above 16,000 (§779): at 16,000 the 32,768 cap is not a brake, so it does not explain
  why G32 and G64 add nothing in §775. This test does not measure 32,000 or 64,000, where the old cap may reset more
  often (§775's binary had no reuse counters).

## Decision

**NOT_SHOWN**. No default change. G16 + mb4 with the 32,768-node reuse cap stays the teacher candidate; the candidate
does not take the larger cap (PREREG: only Test 2 GO would have changed it).

Seeds: §775's 111378256-111379279 reused (no new seeds). Cost: 142.5 lane-hours.
