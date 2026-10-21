# OOC value head: monotonicity penalty (written before training)

Requested by Philipp 2026-10-21 13:47Z/13:51Z (gen-2 thread): enforce a few monotone rules on the value head
("more HP, more max HP, more gold is better") with a training penalty and rerun the training. Offline only: the value
head is not used by OOC search today (leaf = rollout3 + X2-B), so any use in search needs its own A/B.

## Why
Gen 1b failed the OOC-label teacher check (`/mnt/project-files/silver-leaf-eval/ooc-label-leaf/DESIGN.md`): max-HP price
negative (−0.87 HP per point), gold sign flips (p10 −0.07), −3 HP sign wrong in 11% of post-combat states. The labels
are one run outcome z per run, so small within-run differences carry little signal; a hinge on pairs (state, state
with one variable improved) adds the prior that these differences have a known sign.

## Rules (`tools/heart1/monotone.py`)
The copy differs from the row in one variable; the better of the two must not get the lower value:
- `hp`: current HP (heal up to max HP if there is room, else lose HP, never below 1);
- `mhp`: max HP with current HP fixed;
- `gold`;
- `potion`: one filled potion slot emptied (the copy is worse);
- `curse`: one curse appended to the deck (Clumsy, Decay, Doubt, Injury, Normality, Pain, Regret, Shame, Writhe; the
  copy is worse).
Inputs: `obs.fixed_observation[0..2]` (hp, max HP, gold) and the potion / deck tokens, edited on collated tensors, so the
encoded-tensor cache is reused unchanged. Caps: HP 200, gold 1,800 (silverbot's sinusoid limits).

Training (`--mono-weight M`): one random applicable rule per row, deltas uniform (HP 1–10, max HP 1–10, gold 1–100, random
filled slot, random curse), loss `+ M · mean relu(sign · (v − v'))` on value logits over all training rows (policy and
value-only rows). Epoch choice is unchanged (selection objective = policy KL + 0.3·value BCE + 0.3·anchor KL; the penalty
is not in it).

Report (`--mono-report`, implied by `--mono-weight`), chosen epoch, fp32, selection and validation folds: per rule,
rows, violation rate (better state strictly lower value logit), rate with a probability tolerance 0.001, median
better-minus-worse probability. Fixed deltas: −3 HP, +5 max HP, +50 gold, first filled potion slot, Clumsy.

## Runs (gen-2 pick recipe, otherwise unchanged)
Recipe = `S_d64L2_lr1e-4_a0.3_v0.3` of the gen-2 sweep (data branch `claude/az-gen2-data` `e07ad88f`,
`gen2/sweep/results.md`): init student_sel, d64/L2/mult 4/heads 4, lr 1e-4, anchor 0.3, value weight 0.3, K=32 value-only
rows per run per epoch, `--pack --val-at-end --patience 3 --epochs 20 --select fold --extra-inputs --trim-map --amp`, same
rows (`67f510f`, 2,688 files) and folds (validation seed % 8 == 7, selection == 6),
`STS_OOC_HEART1_WING_BOOTS_COUNTER=1`. `STS_ACTIVE_POWER_FEATURES` does not apply (OOC net). distill.py = the sweep's file
(`gen2/sweep/tools/distill.py`, sha256 `0f25037c…`) + `apply_mono.py` here; driver `run.sh` here. No game seeds.
1. `B_s0`: M = 0 with `--mono-report` (training identical to the sweep's pick; must reproduce selection KL 0.0554).
2. `M0.3_s0`, `M1_s0`, `M3_s0`.
3. Seeds 1 and 2 for B and for M* (below).

## Decision rule
- M* = the M with the lowest mean selection-fold violation rate over the five rules among the M whose selection policy
  KL ≤ 0.0560 (B 0.0554 + 3× the seed spread) and selection value BCE ≤ B's + 0.003. None qualifies → NOT_SHOWN.
- PASS (offline) if over seeds 0–2 M* has a lower violation rate than B on each of `hp`, `mhp`, `gold` (selection fold)
  with mean selection KL ≤ B's + 0.0006 and mean value BCE ≤ B's + 0.003; and its exported head passes the two
  `prices.py` teacher-gate items it targets (max-HP price > 0 in ≥ 90 % of states, −3 HP sign right in ≥ 95 %). The
  potion-type and Fairy items are not targeted (the rules carry no per-type information) and are reported only.
- Reported, never used to choose: validation-fold numbers.
- A PASS makes M* a candidate for a value-leaf A/B; it says nothing about online strength by itself.

## Execution
Philipp's GPU via Remote Control (only one GPU job at a time; the gen-2 thread released it), scratch clone
`~/Documents/sts/value-mono`, the gen-2 tensor cache `~/h1distill/gen2/cache` read-only (the cache key covers only
`collate`, which is unchanged). Weights, logs and `summary.json` per run go to the data branch under `gen2/mono/`.
