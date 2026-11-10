# Gumbel tuning whole-run Test 3: no tree reuse, G16NR against §775's G16 + mb4 (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen with the PREREG in the run commit 33252bf0
(before any unit had run), output `results/result.json`. Descriptive breakdown: `breakdown.py` (not pre-registered),
output `results/breakdown.json`. Prelaunch review: K, PASS (with a delta review of 33252bf0).

## Run

- Run commit 33252bf0 (code 13bb97ec, binary b5090b16 from the share's binary cache, Tests 1 and 2's), 40 workers × 4
  lanes, queue. The first game started at 17:01 CET and the last ended at 18:21 CET on 2026-11-10. The 1,024 games sum
  to 143.8 lane-hours (PREREG: about 150-170); the median game took 5.3 min, the longest 47 min
  (G16NR-111378660, a Heart kill; §775's G16 took 21 min there). No game came near the 8 h timeout.
- Every unit ran once: 1,024 claims, all `.a1`, none released (claims snapshot `results/claims.txt`; `claims/` removed
  after it). 40/40 worker DONE files.
- `verify_campaign.py`: 1,024 of 1,024 units OK, 0 missing, 0 bad, 0 duplicates, 0 tars for unknown units, all on run
  33252bf0.
- `analyze.py` (NEW_ROOT = Tests 1, 2 and 3's extracted units, REF_ROOT = §775's D and G16 units, CLAIMS_LIST =
  this campaign's snapshot): 0 bad games, 0 env mismatches, 0 combat aborts, 0 dropped seeds.

## Sentinel and control reuse

Test 1's 32 of 32 sentinel G16 games are identical to §775's: **REUSE_VALID**. §775's 1,024 G16 games are the control.

## Primary

| | G16 + mb4 (§775) | G16NR |
|---|---|---|
| node reuse cap (acts 1-3, Shield and Spear) | 32,768 | 1,024 |
| Heart kill | 41.21% | **38.48%** |
| reach Act 4 (floor ≥ 52) | 49.22% | 46.29% |
| mean final floor | 41.58 | 40.46 |
| CPU per run | 512 s | 505 s (0.99×) |

G16NR − G16 = **−2.73 pp [−5.47, +0.10]** (95% seed bootstrap, 10,000 resamples, seed 20261109), 94 seeds only G16NR
kills, 122 only G16 → **NO_DIFFERENCE_SHOWN**. Act-4 reach −2.93 pp [−5.86, 0.00]; final floor −1.12 [−2.09, −0.14].

## Secondary (95%, not gates)

| contrast | Heart (pp) | Act-4 reach (pp) | only first / only second | CPU ratio |
|---|---|---|---|---|
| G16NR − G16CAP | +0.20 [−2.44, +2.83] | −1.56 [−4.39, +1.17] | 97 / 95 | 1.01× |
| G16CAP − G16 (§780 again) | −2.93 [−5.66, −0.20] | −1.37 [−4.00, +1.37] | 85 / 115 | 0.98× |
| G16NR − D | +6.84 [+3.91, +9.77] | +5.18 [+2.15, +8.20] | 155 / 85 | 2.00× |

Tree reuse (exit line `[silver] whole-run tree reuse:`), per arm over all its games:

| arm | node reuse cap | kept reroots / kept or reset | visits carried, share of all simulations | visits lost to cap resets |
|---|---|---|---|---|
| G16NR | 1,024 | 24.6% (114,512 of 465,541) | **6.1%** | 19.0% |
| G16 (Test 1's 32 sentinel games) | 32,768 | 95.5% | 34.3% | 3.9% |
| G16CAP | 262,144 | 100.0% | 43.6% | 0.02% |

G16NR carries 6.1% of its simulations, under the PREREG's 10%, so the reading is "no reuse", not "reduced reuse". The
kept reroots are subtrees under 1,024 nodes and the Heart (cap 262,144 in every arm). Every root in every arm runs its
16,000 fresh simulations, so a cap reset costs the head start, not CPU: CPU per run is the same in all three arms.

## Where the arms lose (descriptive, not pre-registered)

`breakdown.py`: deaths by section of the final floor, hazard = deaths among runs reaching the section, arm − G16 with
a 95% seed bootstrap (4,000 resamples), as Test 2's breakdown.

| section | G16NR | G16CAP | G16 | G16NR − G16 (pp) | G16CAP − G16 (pp) |
|---|---|---|---|---|---|
| act 1, floors 1-15 | 101 / 1,024 | 102 / 1,024 | 96 / 1,024 | +0.5 [−1.2, +2.1] | +0.6 [−1.1, +2.1] |
| act-1 boss (16) | 99 / 923 | 93 / 922 | 89 / 928 | +1.1 [−0.7, +3.2] | +0.5 [−1.4, +2.3] |
| act 2, floors 17-32 | 140 / 824 | 136 / 829 | 129 / 839 | +1.6 [−1.1, +4.3] | +1.0 [−1.4, +3.4] |
| act-2 boss (33) | 75 / 684 | 71 / 693 | 63 / 710 | +2.1 [−0.5, +4.6] | +1.4 [−1.0, +3.7] |
| act 3, floors 34-49 | 56 / 609 | 54 / 622 | 60 / 647 | −0.1 [−2.9, +2.8] | −0.6 [−3.2, +2.1] |
| act-3 boss 1 (50) | 38 / 553 | 38 / 568 | 43 / 587 | −0.5 [−2.9, +2.0] | −0.6 [−2.9, +1.8] |
| act-3 boss 2 (51) | 41 / 515 | 40 / 530 | 40 / 544 | +0.6 [−2.1, +3.5] | +0.2 [−2.6, +3.0] |
| act 4 (52-56) | 80 / 474 | 98 / 490 | 82 / 504 | +0.6 [−3.3, +4.6] | +3.7 [−0.1, +7.8] |

No section's interval excludes 0. G16NR's extra deaths sit in acts 1-2 (each section +0.5 to +2.1), G16CAP's mostly
in Act 4. Joint Heart kills per seed (G16, G16CAP, G16NR): all three kill on 258 seeds, none on 462; only G16 kills on
73, only G16CAP on 46, only G16NR on 55; all but G16 on 39, all but G16CAP on 49, all but G16NR on 42.

## Reading (Inference)

- No reuse does not beat reuse: the pre-registered NO_REUSE_BETTER needs lo > 0, and G16NR's point estimate is
  −2.73 pp. So there is no evidence that inherited visits hurt the Gumbel root at 16,000 simulations, and Test 3 does
  not support the idea that inherited deep, max-backed values mislead the new root (the leaf-calibration question).
  Inherited visits do not clearly help either: the interval reaches +0.10.
- The two ends of the reuse range play alike: G16NR (6% of simulations carried) and G16CAP (44%) are +0.20 pp apart
  [−2.44, +2.83]. By the PREREG's reading (G16NR − G16CAP lo ≤ 0), Test 2's −2.93 pp is not explained as harm from
  large reuse.
- Both are about 2.8 pp below the same 1,024 G16 games, which makes the Heart rate non-monotone in the reuse: 38.5% at
  6% carried, 41.2% at 34%, 38.3% at 44%. Two readings fit, and this test cannot tell them apart:
  - The 32,768 default is a real optimum: a moderate head start helps, and the larger cap keeps more of the old graph
    (below the cap a reroot does not compact, so nodes outside the new subtree stay findable). No measurement here
    shows that mechanism.
  - The shared control sits above its own expectation. G16 replays deterministically, so all contrasts against these
    1,024 games share one draw of G16's outcomes: c2 (§777, −4.69), G16CAP (§780, −2.93), G16STOP (§783, −2.34 at
    0.70× the simulations) and G16NR (−2.73) all came out below it. Each interval is valid on its own, but the four
    are not independent evidence. G16 + mb4 was also the best arm of §775. Against that, §775's G16 at 32,000
    simulations (G32) reached 40.82% on these seeds, and G16 on #1025's 1,024 fresh seeds (111430000-111431023,
    traced runs) killed the Heart in 41.60% (other seeds, so not a paired comparison).
- Separating the two needs a control that is not these 1,024 games: one cap arm on #1025's seeds against #1025's G16
  games, after a sentinel (about 145 lane-hours, no new seeds), would show whether the −2.8 pp holds with another draw.
  That needs Philipp's go.

## Decision

**NO_DIFFERENCE_SHOWN**. No default change (PREREG: none in any case). G16 + mb4 with the 32,768-node reuse cap stays
the teacher candidate; no reuse is not taken. The node reuse cap stays a non-lever at 16,000 simulations: neither 1,024
nor 262,144 improves on 32,768.

Seeds: §775's 111378256-111379279 reused (no new seeds). Cost: 143.8 lane-hours.
