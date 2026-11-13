# Budget ladder per root: learned per-decision sim budget from the full combat state (result, 2026-11-13)

This is the run of [PREREG.md](PREREG.md), frozen in run commit 885ebaa8 (code 96f49f3c, binary 331bb7db; review K
prelaunch FAIL → fix → delta PASS). Launch was 23:13 CET on 2026-11-12 on W1-W40; the last tar arrived at about
03:10 CET on 2026-11-13.

## Run

- `verify_campaign.py`: **256 / 256 units OK, 0 missing, 0 bad, 0 duplicates**, run 885ebaa87321
  (`results/verify.txt`). Every unit's `.done` line has rc 0, so no unit is dropped (PREREG unit rule: 0 of 256 dropped,
  not INCOMPLETE).
- Claims snapshot: `results/claims-snapshot.txt`. Units 111980109, 111980149 and 111980185 lost their lanes in
  container resets. They were re-claimed after the 90-min lease (attempts a2 and a3) and finished at rc 0. The other
  253 units ran once, as attempt a1.
- Cost: **95.3 lane-hours** (dashboard sum of unit wall times). The plan from the smoke was 150-220 lane-hours.
- Packing: `pack_states.py` → `tensorize.py` on the 256 verified jsonl files (`results/pack.log`).
  `results/packed.sha256` is the sha256 of the packed file. That file went to the PC through ref
  `ppo-xfer/blr-data` (b28892e5).
- Analysis: `tools/combat_net/budget_ladder.py` as frozen. M1 ran in the cloud (`results/m1/result.json`) and M2 on the
  PC GPU (RTX 3060 Ti, torch 2.5.1+cu121, init T1 N_f1 with all 89 tensors matched; `results/m2/result.json` and
  `out.log`, ref `ppo-xfer/blr-results` 38f2675c). M2's fit took 118 s.
  - After the data, commit 2d05b31e added the PREREG's co-reported splits (`by`, `uniform_by`) to the result. It does
    not change the primary numbers: the re-run M1 deltas and CIs are bit-identical.
  - **The M2 fit is not deterministic.** `fit_m2` seeds numpy but not torch, so the head starts from a different
    random init in each run, and CUDA adds its own nondeterminism. M2 was therefore run 5 more times on the same data
    and init at code 2d05b31e:
    - `results/m2-rerun` (ref `ppo-xfer/blr-results2` c2560be6);
    - `results/m2-seed3` … `m2-seed6` (ref `ppo-xfer/blr-results3` ce3b41f4).
    - Run 1 (`results/m2`) stays the pre-declared primary, because it was the first run of the frozen code.

## Rows

- **145,407 roots from 256 runs** were used. Dropped roots:
  - 83 because the prior's top action is unvisited in the played tree;
  - 30 with an unmatched ladder pick (per budget 1k-16k: 12 / 14 / 16 / 18 / 15; 16 rerooted, 14 fresh, out of
    116,257 rerooted and 29,387 fresh roots);
  - 207 with an unvisited ladder pick (per budget 0 / 1k / 2k / 4k / 8k / 16k: 0 / 80 / 91 / 91 / 91 / 81).
- Tensorize truncation: cards 4, monsters' numbers 3, edges 67 (of about 155k rows).

## Uniform budgets (Q loss per decision vs the best edge of the played 16k tree; CPU per decision)

| budget | prior (0) | 1k | 2k | 4k | 8k | 16k |
|---|---|---|---|---|---|---|
| loss | 2.042 | 0.884 | 0.773 | 0.668 | 0.565 | 0.505 |
| CPU ms | 0 | 45 | 90 | 179 | 359 | 719 |

All six lie on the lower convex hull. By room class (CPU ms at 1k / 16k):
- hallway 8.6 / 154;
- elite 23.6 / 388;
- boss 131 / 2,050;
- other (events) 10.5 / 187.

A boss decision costs about 15× a hallway decision at the same budget.

## Primary: learned policy against the uniform frontier at the same CPU (Q per decision, 98.33% CIs)

| model @ target | realized CPU ms (target) | mix prior / 1k / 2k / 4k / 8k / 16k | loss | Δ [98.33% CI] |
|---|---|---|---|---|
| **M2 @ 2k** | 90.5 (89.6) | 10 / 21 / 16 / 15 / 27 / 10 % | 0.724 | **−0.0485 [−0.0713, −0.0251]** |
| **M2 @ 4k** | 180.1 (179.2) | 6 / 10 / 13 / 15 / 25 / 31 % | 0.627 | **−0.0406 [−0.0558, −0.0249]** |
| M2 @ 8k | 359.1 (358.7) | 5 / 5 / 6 / 12 / 25 / 47 % | 0.558 | −0.0069 [−0.0215, +0.0088] |
| M1 @ 2k | 93.4 | 4 / 23 / 26 / 18 / 24 / 4 % | 0.718 | −0.0511 [−0.0679, −0.0319] |
| M1 @ 4k | 186.9 | 3 / 8 / 20 / 17 / 28 / 24 % | 0.634 | −0.0299 [−0.0439, −0.0149] |
| M1 @ 8k | 375.7 | 2 / 2 / 8 / 9 / 31 / 48 % | 0.553 | −0.0089 [−0.0204, +0.0045] |

- Δ is the policy's realized loss minus the uniform frontier's loss at the policy's realized CPU.
- **Decision (PREREG rule on M2, run 1): GAIN at 2k and 4k.** Measured on the uniform curve, M2's loss at 2k and at 4k
  equals uniform at about 1.4× the CPU.
- **M2 across all 6 runs** (Δ, each with its own 98.33% CI):

  | run | 2k | 4k | 8k |
  |---|---|---|---|
  | 1 (primary) | −0.0485 [−0.0713, −0.0251] | −0.0406 [−0.0558, −0.0249] | −0.0069 [−0.0215, +0.0088] |
  | 2 | −0.0561 [−0.0748, −0.0365] | −0.0515 [−0.0693, −0.0352] | −0.0133 [−0.0247, **−0.0022**] |
  | 3 | −0.0589 [−0.0768, −0.0405] | −0.0450 [−0.0593, −0.0306] | −0.0032 [−0.0179, +0.0136] |
  | 4 | −0.0450 [−0.0664, −0.0229] | −0.0423 [−0.0565, −0.0278] | −0.0063 [−0.0210, +0.0095] |
  | 5 | −0.0495 [−0.0681, −0.0303] | −0.0437 [−0.0622, −0.0270] | −0.0029 [−0.0161, +0.0111] |
  | 6 | −0.0640 [−0.0810, −0.0464] | −0.0476 [−0.0656, −0.0313] | −0.0092 [−0.0198, +0.0013] |
  | mean (sd) | −0.054 (0.007) | −0.045 (0.004) | −0.007 (0.004) |

  All 6 runs are GAIN at 2k and 4k. Only run 2 is also GAIN at 8k, so the 8k result depends on the run. The
  run-to-run spread of M2 is about 0.01 Q.
- M2 vs M1: at 4k M2 is ahead in every run (−0.041 to −0.052 vs −0.030); at 2k and 8k M1 lies within M2's spread.
- The oracle (per-root argmin of realized loss + λ · CPU) reaches about 0.09 at 2k-8k (Δ ≈ −0.67). It uses the noisy
  label itself, so it is not a reachable bound.

## Co-reported (M1 @ 2k, `results/m1/result.json` → `by`)

- **The budget moves between rooms:**
  - boss decisions get mostly 1k-2k (prior / 1k / 2k / 4k / 8k / 16k: 6 / 58 / 27 / 7 / 2 / 0 %);
  - hallway decisions get 4k-8k (4 / 11 / 28 / 23 / 32 / 3 %);
  - elite decisions are in between, with more 8k-16k (4 / 10 / 24 / 22 / 33 / 9 %).
- By act: Act 4 goes mostly to 1k-2k (55 / 34 %), Acts 1-3 spread from 1k to 8k.
- Inherited (rerooted) roots: loss 0.64 at 87 ms; fresh roots: loss 1.02 at 119 ms. The mixes are similar.

## Post-hoc (not in the PREREG): an act × room table does as well

`table_baseline.py` uses the same rows, folds, λ search and contrast. Its predicted loss and CPU are the cell means
of (act, room class) on the training folds:

| target | realized CPU ms | loss | Δ [98.33% CI] |
|---|---|---|---|
| 2k | 88.9 | 0.725 | −0.0506 [−0.0681, −0.0308] |
| 4k | 177.9 | 0.626 | −0.0437 [−0.0560, −0.0315] |
| 8k | 358.1 | 0.552 | −0.0131 [−0.0266, +0.0023] |

The table lies within M2's run-to-run variation at every target (`results/table_baseline.json`; M2 mean −0.054 /
−0.045 / −0.007). No paired test of M2 against the table was made. **Most of the gain can be had by moving budget
between act × room cells.** The main move is away from bosses, where a simulation costs about 15× more, toward hallways
and elites. These data show no clear extra gain from the full combat state (M2) or from the root statistics (M1) on top
of that.

## Interpretation (Inference)

- At equal CPU, a per-decision budget beats uniform budgets by about 6% of the Q loss at the 2k-4k CPU levels (≈ 25-30%
  CPU). Within M2's run-to-run variation, the data cannot separate it from a fixed act × room table.
- **The GAIN holds only in Silver Q per decision.** Every decision is weighted equally, so a boss decision counts like
  a hallway decision. Boss simulations cost about 15× more, so this currency favours starving bosses almost by
  construction.
- **The policy's main move runs against the whole-run Heart evidence.** The move is less boss and Act-4 search (58% of
  boss decisions at 1k under the 2k target, 89% of Act-4 decisions at 1k-2k) and more hallway search.
  - §792's H4 cut hallway sims to 4k without a Heart loss (NOT_WORSE).
  - §790's E0, with cheaper boss and elite search (no prior playouts), lost −5.5 pp.
  - §792's A4P showed that Act-4 search strength buys Heart kills.
  - §796's per-fight room policy in Heart pp was NOT_SHOWN (room @ 4k −1.77 pp per run [−4.15, +0.62]).
- Only a whole-run gate can show whether any of this Q gain reaches Heart %, and the prior evidence makes a negative
  result likely for the full table.
- The fresh ladder searches have no tree reuse. The stack reuses trees, so a deployed policy would see cheaper
  rerooted decisions than the ladder.

## Decision

GAIN by the PREREG rule (M2 run 1, 2k and 4k; all 6 M2 runs agree at 2k and 4k), **in Silver Q per decision only**.
There is no default change.

Under the PREREG, a whole-run gate needs its own go. A gate of an act × room table is a risky candidate, because its
main move contradicts §790/§792. Such a gate must include a variant that keeps the boss and Act-4 budgets and applies
the table only to the Act 1-3 hallway and elite decisions.

Seeds: 111980000-111980255 (data only). Cost: 95.3 lane-hours, plus about 3 min on the PC GPU per M2 run (6 runs).
