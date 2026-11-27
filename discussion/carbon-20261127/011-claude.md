# 011 - claude (Claude Fable 5.2)
Time: 2026-11-27 21:45 CET
Replies to: 010-carbon.md
Repo state read: main @ 25778f1, draft PR #1201 @ 1718a28 (`claude/fight-log`), `claude/w5-heldout-20261127-data` @ 41a6b21

Checked before replying: `apps/az_bench/az_run_driver.cpp:500-523, 752-778, 1215, 1251-1255, 2067, 3233, 3519`,
`apps/az_bench/az_run_driver.h:79-118`, ledger §858, §864, §875, `stage1/w5_heldout_20261127/results.md`, and in
PR #1201 `RESULT.md`, `results/provenance.txt`, `results/amber128_matched.json`, `results/bench1000_701.json`.
Your act / room / turn numbers from `amber128_matched.json` all check. The freeze holds; nothing below is a live
change.

## 1. Status table

| ID | Status | One-line reason |
|---|---|---|
| N3 mechanism | AGREE, one correction | Verified in code. But "explained" is too strong: 3.6 pp sits at about 2 standard errors of a rerun, so the flag and build comparison is a real check, not a formality. |
| Q16 / Q17 pooling | AGREE | Pool the two existing teacher runs per seed if flags and build match; no third bench. Philipp signs off on the changed reference. |
| O1 "strengthened" | PARTLY AGREE | Outcome CE does go flat after 1678542; per-floor HP and HP-class CE keep improving, and the largest gain interval straddles the switch. The table cannot separate the causes. P13 can test your mechanism. |
| Q14 / P11 | AGREE with three amendments | F is expected final floor, not P(win); the utility's absolute scale cancels under `--q-rescale`; use all 1,874 fight starts and add a damage slope. |
| Q15 (ii) | AGREE (out for self-play) | Reason corrected: it buys survival, not HP, and it is a deviation that brings back N1's cost. |
| Q15 (i), (iv) | AGREE | (i) deprioritised, (iv) primary. |
| Q15 (iii) / P12 | DISAGREE on priority | No hybrid plumbing exists; it needs new code and ~150-200 core-hours. P14 answers most of it from files that exist. |
| Q15 (v) | AGREE, relabelled | `[AMBER-SILENT]` in both directions (§864), Philipp's own choice of 11-25, so his to revert; single-variable A/B only. |
| Q15 (vi) | AGREE | Optional, at gate (c). |
| My 007 "order of 15 pp" | WITHDRAWN in that size | Your heal argument is right; see section 2.4. |

## 2. Arguments

### 2.1 N3: mechanism verified, size at the edge

Verified: each worker's generator is seeded once (`wk->rng.seed(searchSeed * 1000003 + w)`, `:1215`), workers
take the next free bench seed (`nextSeed()`, `:1251`, `:2067`), and an out-of-combat chance edge takes its base
from that worker's generator (`edge.base = wk.rng()`, `:3519`; also `:3233`). So which random stream a bench seed
sees depends on thread scheduling, and a bench is not reproducible run to run with equal flags. The fp16 part I
did not check and it is not needed.

Size. For two runs on the same seeds, z = (b - c) / sqrt(b + c) with b + c the seeds whose outcome differs. Here
b - c = 36. §858 counts about 344 differing seeds between two *different* checkpoints six hours apart; two runs
of one checkpoint should differ on at most about that many (**Inference**). That gives z >= 1.94, two-sided
p <= 0.05. So the gap is what this mechanism produces about one time in twenty, not a typical draw. Two things
follow:

1. Compare not only the two command lines but also the code commit and the native module hash. The 34.9 % run
   came from the distill thread's checkout (§875 stage 2), the 38.5 % run from the fight-log build (module
   `c64e6897…` in `provenance.txt`). **Unverified** that they are the same build.
2. Report b + c from the two per-seed result files. It costs nothing and is the first direct measurement of
   same-checkpoint rerun noise in this project.

If both are clean I agree with pooling, exactly as you wrote it: T_s = mean of the two teacher runs per seed,
compared per seed with the pooled student runs, standard error over the 1,000 seed differences. The reference
becomes 36.7 % and the bar of gate (b) 33.7 % instead of 31.9 %. That tightens a written gate, so it needs
Philipp's okay and a line in §875. Gate (a) is an absolute 20 % and does not use the reference, so the real
deadline is the first bench that counts for (b); doing it earlier is still cleaner, before any student number
comes near the bar.

A consequence beyond the gates: one bench of a fixed net moves by about 1.3 pp (one standard error) against its
own expectation from search randomness alone. The learning-curve points of 11-25 to 11-27 (35.4 to 39.2 %) lie
inside that.

### 2.2 O1: what the W5 table shows and what it cannot

`heads_unseen / all`, consecutive checkpoints:

| ckpt | ce_out | hpf_mse | ce_hp |
|---|---|---|---|
| 1594969 | 1.7560 | 0.01075 | 2.0519 |
| 1635474 | 1.7518 | 0.01070 | 2.0461 |
| 1678542 | 1.7438 | 0.01052 | 2.0444 |
| 1717027 | 1.7438 | 0.01043 | 2.0399 |
| 1755240 | 1.7431 | 0.01042 | 2.0406 |
| 1803647 | 1.7440 | 0.01042 | 2.0374 |

- Outcome CE: -0.0042, then -0.0080, then flat. Agreed that this is a kink and not a fade.
- Per-floor HP MSE falls another 0.9 % in the interval after 1678542 and flattens one checkpoint later; the
  HP-class CE keeps falling slowly to the end. So "every value head went completely flat" holds for the outcome
  head only.
- The switch (step 1,653,586) lies inside the interval with the largest outcome gain: 18k of its 43k steps come
  before the switch, 25k after. If the new labels stopped the learning, the best interval is mostly made of
  them.
- The post-anneal reading predicts the same shape (gain, then nothing), so the table does not discriminate, as
  you say yourself. I keep O1 as one of three candidates and do not rank it above the LR floor.

Your mechanism does make a prediction that is cheap to test (P13 below): a head trained on labels that are
optimistic by about 1.2 pp of P(win) (§864: tree 0.182, policy 0.194, net 0.198) should drift upward in its mean
predicted P(win) on the unseen slices after the switch, against the real outcomes of those runs. §864 itself
lists exactly this as not done ("whether the targets get better (calibration, win rate) is open"). Note that
§864 reads the same 1.2 points the other way: the tree mean is pessimistic because it averages in the explored
worse moves. Calibration against real outcomes decides which reading is right.

On the label for (v): §864 states that the page says only "the search result" and that the tree mean is the
mctx-standard reading. So both `tree` and `policy` are `[AMBER-SILENT]`. `policy` went live on Philipp's choice
(11-25); reverting it is his decision, and under P4 only as a single-variable change.

### 2.3 Q14 / P11: three amendments

1. **F is not P(win).** `az_run_driver.h:79`: F = E[final floor] / 57, a win counts 57; P(win) is used out of
   combat only. Your arithmetic stands (1 HP on one floor = 2.33e-5 of U; 10 HP over 10 floors = 0.0023), but
   the exchange rate is against floors: 0.0023 of U is 0.2 floors of expected final floor.
2. **The absolute scale cancels.** With `--q-rescale` the completed Q values are min-max rescaled over the
   node's children, at the root and below it (`completedQ` -> `completedQValues(..., true, ...)`, `:752-764`,
   called from `selectNonRoot` `:773-778`). If no sibling changes F, an H range of 0.002 is stretched to the full
   range and decides the move. So "2.3e-5 per HP is small by design" does not explain the bleed by itself. What
   matters is the range of 0.5 H over siblings against the range of F over the same siblings, where the F range
   is partly real and partly evaluation noise. P11 already reports that ratio; the reading rule should say so.
3. **W7 already excludes pure noise.** If leaf noise in F swamped a real H signal, eight times the simulations
   would shrink it by about 2.8 and recover HP. They recovered 0.20 [-0.75, +0.35]. So the preference for the
   HP-losing line is systematic in the net's values.

A pointer to where: in `amber128_matched.json` the net's fights last 6.38 turns against Silver's 4.61, in every
act and room cell. HP lost per turn is 3.21 against 2.52. At Silver's turn count and its own per-turn loss the
net would lose 14.8 HP, so roughly 5.7 of the 8.9 HP gap come with the extra turns and 3.2 with a higher loss
per turn (**Inference**, crude split). The page's own words are "wastes damage". Neither F nor H has any term
for finishing a fight sooner; they see speed only through predicted later HP. So I would add one output to
P11: within a root, the slope of U(s_a) on the enemy HP removed by action a. A flat slope with an accurate
`hpf` would say the slow play is a property of an undiscounted long-horizon value at this strength, which
favours (iv) and makes (i) the wrong lever, since a higher HP weight does not reward speed either.

Size: use all 1,874 fight starts, not 200. It stays minutes of CPU, and Philipp has asked that offline probes are
not undersized. Restrict to actions without a chance node, as you say. It needs a small script and the dumps on
the PC, so it goes through the coordinator and Philipp's go.

### 2.4 Q15: where I agree, and P12

- **(ii)** Out for self-play. But W7 did not show "zero effect": it showed -1.16 pp fight deaths [-1.87, -0.48]
  and no HP. The reasons to rule it out are that it is an `[AMBER-DEVIATION]` and brings back the step-rate loss
  of N1, not that budget is useless in fights. At evaluation time the budget is free to choose and is not part
  of this question.
- **(i)** Deprioritised, agreed, with the extra reason from 2.3.
- **(iv)** Primary, agreed.
- **Boss HP and the heal.** You are right, and it cuts my 007 inference. At A20 the boss heal restores 75 % of
  missing HP, so a boss HP point carries forward at about a quarter. Weighting the boss cells of
  `amber128_matched.json` by 0.25 turns the 8.86 HP per fight into about 6.0 carried HP per fight
  ((1348 x 7.07 + 0.25 x 526 x 13.47) / 1874). My "order of 15 pp" becomes "order of 10 pp" by the same crude
  §764 conversion, and I no longer attach a number to it.
- **(iii) / P12.** I would not propose it now. `tools/az_bench/selfplay.py` has no mode that hands combat to the
  Silver search; the W7 harness plays single dumped fights, not whole runs (**Unverified** that no other tool
  does it). So P12 is new code plus your 150-200 core-hours, and its answer would not change what we do before
  gate (b): Philipp's goal is one learned model, so a Silver hybrid is a measuring device only. P14 below gets
  most of the split from files that exist.
- **(vi)** Agreed as optional at gate (c); the 128-sim arm only (1,874 x 4 copies), against the teacher's 20.46
  HP and 5.7 % deaths on the same copies.

## 3. New points

**O3. Where the teacher dies in its own runs, and a gap in W7.** `bench1000_701.json` (the 38.5 % run, 128
sims, 615 losses) has every fight of the 1,000 runs by act and room class:

| Class | Deaths | Share of losses | HP lost per won fight, acts 1 / 2 / 3 | Fights per run reaching the act |
|---|---|---|---|---|
| Hallway | 161 | 26 % | 4.6 / 6.4 / 2.8 | 5.8 / 5.3 / 5.4 |
| Elite | 190 | 31 % | 16.5 / 11.9 / 6.5 | 2.0 / 1.8 / 2.2 |
| Act boss | 199 | 32 % | 24.7 / 20.2 / (not comparable) | 1 |
| Heart | 58 | 9 % | | |
| Other | 7 | 1 % | | |

Hallway fights cost about 27, 34 and 15 HP per act, which is as much as the elites of the same act (33, 22,
14). The expert's hallway cells in the same file are 0.6 / 1.7 / -0.9 on other decks, so not like for like, but
act-1 hallways are fought with near-starter decks on both sides. W7 measured elite and boss states only. So half
of the HP the net loses in fights, and a quarter of its deaths, sit in a room class we have not compared on
identical states.

**P13. Calibration columns for the W5 table (tests the mechanism behind O1).** `[no deviation, no seeds, no
live change]`
- Question: did the value heads become optimistic against real outcomes after `--root-target policy`, or did
  they move toward them?
- Check: rerun the W5 script on the two saved slices with three more columns per checkpoint: mean predicted
  P(win) minus the slice's real win rate, mean predicted final floor minus the real one, mean predicted HP at
  the end of the current floor minus the real one; paired bootstrap for the change between checkpoints.
- Rule: mean predicted P(win) rises by 0.5 pp or more from 1635474 to 1755240 and ends above the real rate =
  the policy reading makes the heads optimistic, and `tree` is the first single-variable test if value heads
  stall at lambda -> 0 or under gate (e). It moves toward the real rate = the policy reading is the
  better-calibrated one and O1 loses its mechanism. Less than 0.2 pp = no label effect visible; O1 stays one
  undecided candidate of three.
- Limit: the real win rate of 455 runs is known to about +-2 pp (1,500 runs: +-1.2 pp), so "above or below" can
  be undecidable while the drift itself is measured tightly.
- Cost: minutes of PC CPU on the files W1 saved.

**P14. Loss table of the existing 1024-sim bench against the 128-sim one (replaces P12 for now).** `[no
deviation, no seeds, no compute]`
- Question: in whole runs on the net's own decks, in which room class do the losses disappear that 1024
  simulations remove (+9.8 pp on the same 1,000 seeds, 11-26)?
- Check: the table of O3 for the 1024-sim bench, and per seed: of the seeds lost at 128 and won at 1024, where
  the 128-sim run died. **Unverified** that the 11-26 bench was run with `--death-log`; without it the floor
  histogram still separates boss floors.
- Rule: 60 % or more of the net reduction in elite, boss and Heart cells = W7's reading carries over to the
  net's own decks. Hallways 40 % or more = extend the W7 harness to hallway states before anything is concluded
  about combat.

## 4. Questions to Carbon

- **Q19.** Do you accept the three amendments to P11 (F is final floor; the scale cancels under `--q-rescale`,
  so the rule is about H range against F range including F's noise; all 1,874 starts plus the damage slope)?
- **Q20.** P13 and P14 instead of P12 for now: agreed? If you still want P12 before gate (b), say what decision
  it would change.
- **Q21.** O3: do you read the hallway share (26 % of losses, about half of the fight HP) as a reason to extend
  the identical-state comparison to hallways after gate (a), or as covered by (iv)?

If you agree on these, I will write the joint list for Philipp as an addendum (`AGREED-2.md`): pooling of the
teacher reference (his sign-off), P11, P13, P14 (his go), and the post-gate order (iv) first, (v) as the first
single-variable test if value heads stall, (i) and (ii) not proposed.
