# Gumbel tuning whole-run Test 3: no tree reuse, G16NR against §775's G16 + mb4 (pre-registration)

**Authorization.** Philipp, 2026-11-10 15:22 CET: "Ja let's go", answering the proposal of 08:42 CET to run §775's
G16 + mb4 without tree reuse (`STS_SILVER_NODE_REUSE_CAP=1024`) on §775's 1,024 seeds against §775's G16, about 145
lane-hours, no code change, no new seeds. Workers: 40 as in Test 2 (asked at 15:22 CET). Prelaunch review before the
launch.

## Question

Test 2 (§780) kept more of the tree (reuse cap 262,144 instead of 32,768) and found G16CAP − G16 −2.93 pp
[−5.66, −0.20] Heart. Do the visits a root inherits from the previous search help or hurt the Gumbel root at 16,000
simulations? If inherited visits hurt, a root without them should be at least as good as G16, and the three caps
should order no reuse ≥ 32,768 ≥ 262,144.

## Design

- Seeds: §775's 111378256-111379279 in ascending order, one unit `SEED G16NR` per seed (`units.txt`). Smoke on the
  smoke seeds 111379282 and 111379283 (not analysed).
- Arm G16NR = §775's G16 + mb4 (`run_unit.sh`, a copy of Test 1's with this arm added) plus
  `STS_SILVER_NODE_REUSE_CAP=1024`, the smallest value the option accepts. At a reroot (`NativeSilverBackend.cpp`,
  `prepareSearcher`) a pool of at least the cap is compacted to the subtree reachable from the new root; if that
  still holds at least 1,024 nodes, the root starts a fresh tree (a cap reset). Subtrees under 1,024 nodes stay. The
  Heart keeps its cap of max(cap, 262,144) as in G16 and G16CAP. Every root runs its flat 16,000 fresh simulations
  in every arm, so the arms differ only in what a root inherits.
- Control: §775's 1,024 G16 games (binary 0eabb014), valid through Test 1's 32 of 32 identical sentinel games on
  this binary (REUSE_VALID, §777). Third point: Test 2's 1,024 G16CAP games (same binary, same seeds).
- Binary b5090b16 (code 13bb97ec, Tests 1 and 2's) from the share's binary cache; net-0420 out of combat; timeout 8 h
  per game; `run_unit.sh` checks the arm's log lines (`research node reuse cap 1024`, `reuse_cap=1024`).
- Smoke (local, 2026-11-10 15:26-15:44 CET, binary b5090b16, not part of the data), G16NR and G16 on the smoke seeds:
  - 111379282: both rc 0, both died on floor 16. G16NR kept 18 of 134 kept-or-reset reroots and carried 1.3% of its
    simulations (G16: 128 of 131, 38.0%).
  - 111379283: both rc 0, both killed the Heart. G16NR kept 216 of 679 reroots (the Heart's and subtrees under 1,024
    nodes) and carried 5.1% of its simulations (G16: 681 of 704, 33.8%). CPU 990 s for 14.9 M simulations
    (G16: 908 s for 14.0 M), 1.02× G16's CPU per simulation.
  - Both G16NR logs show `[silver] research node reuse cap 1024` and `reuse_cap=1024`; `run_unit.sh` accepted all four
    games; `analyze.py --self-test` passes.

## Primary (analyze.py, frozen with this file)

d = Heart kill G16NR − G16 per seed (§775's game). A seed counts if both games finished rc 0 with all log checks and
an env matching the arm (a combat abort is a counted loss); universe = seeds whose G16NR unit was claimed; dropped
seeds are listed, never imputed; more than 20 dropped = **INCOMPLETE**; sentinel not REUSE_VALID =
**CONTROL_INVALID**. 95% seed bootstrap (10,000 resamples, seed 20261109), two-sided:
**NO_REUSE_BETTER** if lo > 0, **NO_REUSE_WORSE** if hi < 0, else **NO_DIFFERENCE_SHOWN**.

No SPRT: no option or default is gated; the test asks for the direction of the reuse effect, and every seed runs.

## Secondary (95%, not gates)

- G16NR − G16CAP (both on b5090b16), G16CAP − G16 (§780 again), G16NR − D.
- Act-4 reach and final floor of each contrast; per arm Heart kill, act-4 reach, mean final floor, CPU per run,
  games over 1 h.
- Tree reuse counters: kept reroots as a share of kept-or-reset reroots, inherited visits as a share of all
  simulations (G16's sentinel games: 34.3%; G16CAP 43.6%). If G16NR carries more than 10% of its simulations, the
  reading says "reduced reuse", not "no reuse".

## Reading (pre-registered)

- NO_REUSE_BETTER: inherited visits hurt the Gumbel root at 16k. The next step locates why (leaf value calibrated by
  depth against max-backup optimism, separate pre-registration with Philipp's go); a teacher candidate takes no reuse.
- NO_REUSE_WORSE: reuse helps at 16k; Test 2's −2.93 pp is then not "more reuse hurts" but noise or specific to the
  large cap.
- NO_DIFFERENCE_SHOWN: no evidence that reuse matters at 16k either way. With G16NR − G16CAP lo > 0 the three points
  are consistent with harm from large reuse only; otherwise Test 2's result stays unexplained (most likely noise).

Power (inference): as Test 2, about ±2.8 pp at 1,024 pairs (§780: 200 discordant seeds).

## Cost

G16's 512 s per run × 1,024 = 146 lane-hours; the smoke's two G16NR games took 1.12× their G16 games' CPU (more
roots on the first seed), so about 150-170 lane-hours, about 1.5-2 h on 40 workers × 4 lanes. Share: about 4,100
new files (tars, claims) on a share holding about 41,300 files at 15:25 CET.

## Decision

No default change in any case.
