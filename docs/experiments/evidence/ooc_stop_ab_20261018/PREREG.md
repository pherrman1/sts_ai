# OOC MCTS stop rules on the CTM-Act-4 A20 stack: pre-registered plan

Authorization: Philipp 2026-10-18 18:15Z ("act 4 fights can just be done by the ctm now. so turn that on, then
test adpative stop or a model which predicts whether we wont need more simulations"), decision card 21:45Z
("All three": no stop, gap ladder and learned stop in one paired A/B), 22:09Z ("8 workers. make sure we rethink
this approach when we chang ethe root emperature"). Code commit `code_commit` in `campaign.manifest`. The result
gets the next free ledger § when it is recorded; the offline evidence is the learned-stop ledger entry (§TBD at
freeze).

## Question
Do the two adaptive OOC stop rules play as well as the full search (exact visit lock only) at A20, and how much
CPU do they save? Offline, on 2,210 CTM-Act-4 roots, both keep 99.5% of the full search's actions; the learned
stop at an estimated 0.50x OOC CPU, the gap ladder at 0.66x. What a changed action does later in the run, and
the real CPU, are what this run measures.

## Arms (same binary, same seeds, paired; `run_unit.sh`)
| Arm | OOC MCTS stop |
| --- | --- |
| N (control) | exact visit lock only (`STS_OOC_MCTS_EARLY_STOP=1`, as today) |
| G | N + `STS_OOC_MCTS_GAP_STOP=1024:0.7` (§539) |
| L | N + `STS_OOC_MCTS_LEARNED_STOP=models/candidates/ooc_learned_stop_trees.txt:0.99` (sha256 aa928b83…) |

Common, the §539 A20 stack minus `STS_OOC_MCTS_ACT4_SILVER_SIMS`: OOC MCTS 4096 sims, student_sel
(`STS_OOC_HEART1=student_sel.bin`, sha256 cf6bf7fb…) as heart1full prior with `TARGET_PRIOR=1`,
`LEAF_SELECTS=heart1`, `LEAF_POLICY=heart1`, rollout3 native leaf, `TEMPERATURE=1`, cPUCT 1.5, widening 4/0.75,
tree rules, 8 public futures; imagined fights on the A20 CTM, with Shield and Spear and the Heart through the
ADR-0048 survival model, CTM-refused fights on Silver 500 (`UNSUPPORTED_SILVER_SIMS=500`); real combats on
Silver flat exact 10k with the g7f_E root and tree prior (weight 400, K=8; ADR-0049, Philipp 2026-10-18 23:53Z)
and main's defaults (g7f_E rollout root table, #675 prior playouts in real boss and elite fights). A20 full runs to the Heart (`STS_STOP_AFTER_ACT=0 STS_COLLECT_KEYS=1 STS_FAIR=1`), one thread per
process.

A unit is rc=97 when its OOC MCTS banner does not show exactly its arm's stop rule, and rc=96 when the Act-4
survival model did not load.

## Seeds and size
512 seeds 111199495-111200006, 3 arms, 1,536 units in `units.txt` (arm-major, so a seed's three units land on
the same worker, i%8+1). 8 workers, 4 units at a time, unit timeout 6 h (rc 124).

## Endpoints and decision rules (`analyze.py`)
A seed counts only when all three arms finished with rc 0 and wrote their result rows; dropped seeds are listed.
- **Primary (two):** reached Act 4 (`act >= 4` or `won`), paired L − N and G − N, Newcombe (1998, method 10) 95%
  intervals. Each: NON_INFERIOR when the lower bound > −5 pp; LOSS_SHOWN when the upper bound < 0; otherwise
  NOT_SHOWN.
- **Secondary:** Heart kills (paired interval, exact McNemar p), mean floor, mean process CPU seconds per run
  (`sec`) and the CPU ratios L/N and G/N.
- L − G: descriptive only.
- A rule is proposed as a default only if it is NON_INFERIOR and saves CPU; that is Philipp's decision.

## Model validity
The checkpoint data came from the g6_E-prior stack before #675; those settings change real fights only, not the
OOC search the model reads, so the model is used as trained (Inference). The learned model was trained at `STS_OOC_MCTS_TEMPERATURE=1` with student_sel root priors and refuses any other
temperature. A change of root temperature, prior network or simulation budget needs new checkpoint data and a
retrained model before its result applies (Philipp 22:09Z).

## Smoke (seeds 111198370-111198372, not part of the test; branch binary before freeze)
Flag off: play files byte-identical to main c890da5b on 111198370. L on 111198370: same 70 actions, OOC CPU
804 → 516 s; on 111198371: first different action at decision 71 of 104, OOC CPU 945 → 543 s. 111198372:
temperature-guard check only.

## Cost estimate (Inference from the 36 checkpoint runs, `sec` ≈ 1,000 s per control run)
About 2,400 CPU-seconds per seed for all three arms, about 340 core-hours; per worker roughly 10-11 h wall.
