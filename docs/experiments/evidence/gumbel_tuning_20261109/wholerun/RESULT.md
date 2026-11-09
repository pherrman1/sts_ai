# Gumbel tuning, confirmation in whole runs: c2 against §775's G16 + mb4 (result)

Pre-registration: [PREREG.md](PREREG.md). Analysis: `analyze.py` as frozen, output `results/result.json`. Stage 2's
pick c2 ([../RESULT.md](../RESULT.md)) against §775's teacher G16 + mb4 on §775's 1,024 seeds.

## Run

- Run commit b93ecc07 (code 13bb97ec, binary b5090b16), 40 workers × 4 lanes, queue with the 32 sentinel units first
  in the unit list (the queue's claim order, not a separate static phase). The first unit started at 21:34 CET, the
  last ended at 22:57 CET on 2026-11-09. Unit wall time sums to 145 lane-h (projected 160); the median unit took 4.9
  min, the longest 42 min (C2-111378648).
- `verify_campaign.py`: 1,056 of 1,056 units OK, 0 extra tars, 40/40 worker DONE files. Every unit was claimed once
  (claims snapshot `claims.txt` on the share; `claims/` removed after it).
- `analyze.py`: 0 bad games, 0 env mismatches, 0 combat aborts, 0 dropped seeds.

## Sentinel and control reuse

32 of 32 sentinel G16 games are identical to §775's (rc, abort flag, .log without timing, heart1_ppo decision counts,
Gumbel roots and simulations): **REUSE_VALID**. §775's 1,024 G16 games are the control.

## Primary

| | G16 + mb4 (§775) | C2 |
|---|---|---|
| Heart kill | 41.21% | **36.52%** |
| reach Act 4 (floor ≥ 52) | 49.22% | 44.82% |
| mean final floor | 41.58 | 39.88 |
| CPU per run | 512 s | 495 s (0.97×) |

C2 − G16 = **−4.69 pp [−7.71, −1.66]** (95% seed bootstrap, 10,000 resamples), 102 seeds only C2 kills, 150 only
G16. SPRT gainer (H1 +2 pp, alpha 0.05, beta 0.05, look 64): accepts H0 at 640 seeds (LLR −3.22) → **NOT_SHOWN**.
The nonregression variant reaches CAP at 1,024 (LLR −2.48). All seeds ran (PREREG). The 95% interval excludes 0: c2 is
worse than G16 + mb4 in whole runs, not just not better.

## Secondary

- C2 − D (§775's A20 default combat) +4.88 pp [+1.95, +7.71] at 1.96× D's CPU; C2 − G32 −4.30 pp [−7.32, −1.37].
- Act-4 reach C2 − G16 −4.39 pp [−7.42, −1.37]; final floor −1.70 [−2.74, −0.67].
- No game over 1 h (longest 42 min).
- `results/result.json` has no `ref:G64` in `per_arm` because the REF_ROOT used here held only §775's D, G16 and G32
  units (the G64 units were not extracted); `analyze.py` reads G64 too when its units are there (40.43%, as §775).
- Tree reuse (this binary): C2 cap resets on 4.92% of kept-or-reset reroots (24,227 of 492,103), visits lost to cap
  resets 4.50% of all simulations, visits carried 35.0%. The 32 sentinel G16 games: 4.50%, 3.90%, 34.3%. Both are
  far above PREREG's 1% skip line, so Test 2 stays recommended.

## Where c2 loses (descriptive, not pre-registered)

Computed by `breakdown.py` (output `results/breakdown.json`) from this campaign's and §775's games and from the unit tars of
tuning stages 1 and 2.

The whole-run logs hold a run's final floor, outcome and CPU, not HP per fight. Deaths by section (a run's death floor;
non-boss sections mix hallway, elite and event fights), hazard = deaths among runs reaching the section, C2 − G16 with
95% seed bootstrap (4,000 resamples):

| section | C2 | G16 | C2 − G16 (pp) |
|---|---|---|---|
| act 1, floors 1-15 | 114 / 1,024 | 96 / 1,024 | +1.8 [−0.1, +3.5] |
| act-1 boss (16) | 95 / 910 | 89 / 928 | +0.8 [−1.0, +2.7] |
| act 2, floors 17-32 | 151 / 815 | 129 / 839 | +3.2 [+0.2, +5.9] |
| act-2 boss (33) | 71 / 664 | 63 / 710 | +1.8 [−0.8, +4.4] |
| act 3, floors 34-49 | 53 / 593 | 60 / 647 | −0.3 [−3.0, +2.4] |
| act-3 boss 1 (50) | 39 / 540 | 43 / 587 | −0.1 [−2.6, +2.4] |
| act-3 boss 2 (51) | 42 / 501 | 40 / 544 | +1.0 [−1.8, +4.0] |
| act 4 (52-56) | 85 / 459 | 82 / 504 | +2.2 [−1.9, +6.3] |

On the 252 seeds with different outcomes the loser died in acts 1-2 outside the bosses on 61 seeds where only G16
killed and on 32 where only C2 killed.

On stage 2's 602 paired elite and boss fights (production runs, not net-0420's) c2 loses less HP than ctl in every act
(act-1 elite −0.12 [−0.74, +0.51] to act-3 boss −2.25 [−4.17, −0.31]) and drinks more potions (point estimate positive in every act and room; act-3 bosses include 0):
+0.068 potions per fight [+0.049, +0.086] (ctl 0.597), act-1 boss +0.165 [+0.107, +0.223]. At 3.7 HP per potion
(§766) that is about 0.25 HP per fight, at Silver's leaf price of 11 HP about 0.75 HP. Stage 1's main effects per act
and room put J (end-turn widening) at −0.15 HP in act 1 and −1.4 to −2.2 HP in acts 2-3.

Reading (Inference): c2 was tuned on acts 1-3 elite and boss fights only. In whole runs it plays every hallway fight
and Act 4 with the same constants. Its excess deaths are resolved only in act 2 outside the bosses, where hallway
fights dominate; act 1 outside the boss points the same way (interval includes 0), and act 3, where the tuning gain was
largest, shows none. A hallway fight test (selffights, arm rooms `1M,2M,3M`, ctl vs c2, stage
2's 56 seeds, about 20 lane-h) would measure it; Philipp chose it on 2026-11-09 at 23:30 CET (own
pre-registration). The potion cost covers part of the HP gain
but not 4.7 pp. Like §770 against §775, HP per elite or boss fight did not predict the whole-run result, here not even
its sign.

## Decision

**NOT_SHOWN** (C2 worse, CI excludes 0). No default change. G16 + mb4 stays the teacher candidate. c2 is not used.
Test 2 (node reuse cap) runs as **G16CAP − G16** (PREREG: G16CAP if Test 1 is not GO), with its units and launch after
Philipp's choice of order.

Seeds: §775's 111378256-111379279 reused (no new seeds). Cost: 145 lane-hours.
