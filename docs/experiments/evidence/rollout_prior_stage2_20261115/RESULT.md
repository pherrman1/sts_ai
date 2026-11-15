# Rollout prior on G16 targets, stage 2: result (2026-11-15)

**Verdict: WORSE (both candidates).** As the playout policy, V and its boss fine-tune X-B pick worse root moves than
g7f_E at equal simulations. V@4k is +0.289 max-backed Q (99 % CI [+0.214, +0.379]) and XB@4k +0.300 [+0.232, +0.375].
V at 16k is +0.339 [+0.261, +0.431] worse than g7f_E at 16k. On the P1 curve, V at 16,000 sims (loss 1.111) sits
between g7f_E at 2,000 (1.156) and 4,000 (0.991). Every group, every encounter and fold 4 point the same way. Stage 1's
root-regret gain does not carry over to playout states. Under the PREREG's decision rule the line stays parked;
Philipp's separate whole-run gate (stage 3, V in all four prior roles) is running.

[PREREG](PREREG-stage2.md) · run commit 2c2d064e (code f9601609, binary 5a659bd8, x86-64-v3) · share
`/mnt/project-files/rollout-prior-stage2` · 32 cloud workers × 4 lanes, 2026-11-15 21:36-22:58 CET · numbers:
[results/result.json](results/result.json) (sha256 b2663c2a…), [results/analyze.out](results/analyze.out) ·
`analyze.py <new> <§797 units> results/result.json --s798 <§798 units> --boot 10000`.

## Early stop (deviation)

Philipp ended the run at 22:57 CET ("can we already stop the stage 2 run? its pretty clear its worse and i dont wanna
wait for the tail"), with 253 of 256 units done. One more (seed 111980058, rc 0) finished at 22:58 CET and is
included. The 2 units still running (seeds 111980140, 111980159; long games) were stopped and count as dropped runs.
2 is below the PREREG's 20-drop bound, so the status stays OK. Short games finish first, so stopping early leaves out
2 of the longest games. The estimate did not move as runs came in (V@4k +0.31 on 105 runs, +0.29 on 216, +0.289 on
254).

## Checks

- Status **OK**: 254 runs (rc 0), 0 sentinel mismatches against §797 (roots and `chosen`), 0 student-manifest
  mismatches (names and sha256 of rp_V.txt / rp_X-B.txt), 2 dropped runs. 235 runs have at least one boss / Act-4
  root (42,138 rows); the other 19 died before a boss, as in §797 and §798.
- Calibration **OK**: the p1:1000 − p1:16000 gap is 0.547, with 95 % CI [0.504, 0.592].
- asplayed:4000 against §798's asplayed:4000 (same arm index and salt): 42,220 of 42,220 picks are identical. The
  control contrast asplayed:4000 − p1:4000 is +0.003 [−0.028, +0.035] (NOT_SHOWN), as it should be.
- Row drops: an arm's pick that the played tree never visited drops the row. That happened 41 times for asplayed,
  12 for V@4k, 5 for X-B, 4 for V@16k and 2-7 for p1 (see `drops`).

## Results (all rows, loss = best max-backed Q in the played G16 tree − Q of the arm's pick)

| arm | playout policy | sims | loss | CPU per root (s) |
|---|---|---|---|---|
| asplayed:4000 | g7f_E | 4,000 | 0.994 | 0.52 |
| st:4000 | V | 4,000 | 1.283 | 0.59 |
| ste:4000 | X-B | 4,000 | 1.294 | 0.60 |
| st:16000 | V | 16,000 | 1.111 | 2.35 |
| p1:1000 … p1:16000 (§797) | g7f_E | 1k / 2k / 4k / 8k / 16k | 1.319 / 1.156 / 0.991 / 0.860 / 0.772 | 0.13 … 2.07 |

Student CPU is overstated: the student arms run through `nativeSilverPolicyPriorWith` without g7f_E's argmax hook and
pick cache. The labels compare at equal simulations.

| contrast (99 % CI, run-clustered) | all | Act 1-2 bosses | Act 3 bosses | Act-4 elite | Heart | fold 4 |
|---|---|---|---|---|---|---|
| V@4k | +0.289 [+0.214, +0.379] | +0.160 | +0.379 | +0.334 | +0.344 | +0.263 |
| XB@4k | +0.300 [+0.232, +0.375] | +0.189 | +0.379 | +0.309 | +0.363 | +0.286 |
| V@16k | +0.339 [+0.261, +0.431] | +0.207 | +0.427 | +0.374 | +0.410 | +0.413 |
| label | WORSE, WORSE, WORSE | WORSE | WORSE | WORSE | WORSE | WORSE |

All group and fold-4 CIs are above 0 (see result.json). Per encounter, V@4k is worse in every boss. The gap is largest
for Awakened One (+0.46), Automaton (+0.38), the Heart (+0.34), Donu & Deca (+0.34), Shield & Spear (+0.33) and
Time Eater (+0.33). It is smallest for Hexaghost (+0.02), Slime Boss (+0.06) and Champ (+0.07). X-B's boss fine-tune
does not help.

## Interpretation (Inference)

- **Distribution shift.** V saw only the roots that G16 reached in play: start-of-turn states on G16's own path, with
  G16-quality decks and HP. A playout visits deeper and worse states, many of them after its own weak moves. g7f_E's
  data were Silver roots from varied (half perturbed) A0 runs plus 370k A20 Act-4 roots, so it is broader where
  playouts go. Stage 1 measured only G16-path roots and could not see this.
- **Target shape.** Sequential halving gives its finalists nearly equal visits, so V learns flat preferences among
  several good moves. A playout takes the argmax at every step and needs one sharp, robust choice. Silver's visit
  shares (g7f_E's targets, plus a teacher) are sharper.
- The PC follow-up (V' line, offline) agrees: adding g7f_E's old Silver data to V's mix makes G16-root regret worse
  (M vs V +0.13), and more capacity on G16 data alone helps a little (W256 1.849 vs V 1.884). Root regret does not
  rank playout quality, so offline root numbers cannot select a playout policy.
- Caveat: the reference tree was built with g7f_E playouts and favours g7f_E-like picks. This is conservative for the
  candidates but does not explain a 0.3 Q gap that holds in every encounter and is as large at 16k as at 4k.

## Decision

WORSE under PREREG-stage2.md: root targets do not transfer to playouts, and V / X-B are not playout candidates. No
default change. The next playout-prior step, if any, is to train on captured playout states labelled by short
searches (DAgger-style), not on more root data. Stage 3 (Philipp's go 21:59 CET: V in all four roles, whole-run SPRT
gate vs §775's G16) runs separately; its own PREREG and result decide it.

Seeds: §797's 111980000-111980255 (reused, no new seeds). Cost: about 86 lane-hours on 32 workers (4 cores each).
