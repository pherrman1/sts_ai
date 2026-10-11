# §426 — rollout3 with the §423 Lizard-capable CTM on the A20 gold decisions: aborts gone, not shown better (2026-10-11)

**Question:** §425 `rollout3` ran on the production pathb-r2 CTM and aborted about a quarter of its A20 searches on
active Lizard Tail states (Fairy Potion or Entropic Brew held with an unused Tail). With the §423 Lizard-capable
research candidate CTM, does rollout3 pick better than the heuristic on the same gold decisions?
Plan frozen before the run: [PREREG.md](PREREG.md), commit `78aee118` (author date 13:35:31Z; the runner wrote its job
list at 13:35:35Z and the first search output at 13:36:01Z). `compare.py` was written during the run, before any result was read.

## Inputs and run

- Replay tool and binary as §425: `one_combat` sha256 `cd0bb658…` built from #476 head `6cd03972` (#476 has since
  merged; `strategic_gen.cpp` on `main` differs only in the unrelated `strategicMargGen` from #482).
  All gold inputs match §425 byte for byte ([inputs-sha256.txt](inputs-sha256.txt)).
- Arm `lizard` = §425 `rollout3` environment + the §423 candidate (`combat_transition_deepsets_pathb_r2_lizard.native`
  `c6d56bbc…`, manifest `candidate-v3-lizard.json` `64da1776…`, active Lizard on). [run_lizard.sh](run_lizard.sh).
- Search run seeds 74004000–74005047 (74004000 + 4i + rep, i = gold seed index, one replay per (seed, rep),
  `STRATEGIC_MCTS_REPS=1`), through `tools/seed_guard.sh`. One cloud container, 4 processes, about 95 min wall.

## Validity

1,048/1,048 replays rc=0; every log prints `[ctm-research-candidate] candidate_id=pathb-r2` and the candidate
`combat_model`; the replay rows of reps 1–3 equal rep 0's for every seed. Same coverage as §425: 398 of 409
multi-option targets searched, 386 state-verified, 378 with a recorded heuristic choice. No Lizard aborts.

## Result ([score-output.txt](score-output.txt), [compare-output.txt](compare-output.txt), 10,000-sample decision bootstrap)

On the 378 verified decisions (1,512 searches):

| arm | mean floor regret (live) | tie-aware top-1 | searches without a selection |
|---|---|---|---|
| heuristic (gold-run choice) | 4.55 [3.83, 5.33] | 0.276 | – |
| §425 `prod` | 4.35 [3.68, 5.09] | 0.280 | 4 (0.3%) |
| §425 `rollout3` | 4.22 [3.57, 4.92] | 0.295 | 363 (24.0%): Fairy+Tail 162, Brew+Tail 143, `hp_envelope` 54, boundary 4 |
| **`lizard` (§426)** | **4.15 [3.49, 4.83]** | 0.297 | 57 (3.8%): `hp_envelope` 53, boundary 4 |

- **Primary:** `lizard` − heuristic Δregret −0.40 [−0.96, +0.16] → **NOT_SHOWN**. Strict top-1 Δ −0.073
  [−0.125, −0.022] (the §425 reward-screen gold-pile tie artefact; tie-aware top-1 0.297 vs 0.276).
- Paired: `lizard` − §425 `rollout3` Δregret −0.08 [−0.33, +0.20]; `lizard` − §425 `prod` −0.21 [−0.70, +0.26].
- Owned only (356 decisions): regret 4.18, Δ vs heuristic −0.44 [−1.03, +0.17]. Agreement with the heuristic 0.51;
  modal pick share across the 4 searches 0.94.
- Mean simulations per search 1,051 (§425 `rollout3` 916, `prod` 1,088); 9.6 s per search on 1 CPU (§425 `rollout3`
  9.1, `prod` 0.4).

## Reading

The candidate CTM removes every Lizard abort at A20 as it did at A0 (§423); only `hp_envelope` (#369) remains.
Searching the formerly aborted decisions changes the picks little: the regret point estimate moves from 4.22 to
4.15, inside noise, and none of the three MCTS arms is shown better than the heuristic or each other.
The gold labels are noisier than their "16 futures" suggest: the §419 branch futures only changed the agent RNG,
which native Silver combat does not consume (found in commit `65ed71f4`, unmerged branch
`claude/project-thread-ay2czp`), so each label is close to a single playout. That noise can only hide a real
difference, so it weakens the power of this comparison but not the NOT_SHOWN reading.
**Inference:** the §425 rollout3 result was not held back by its Lizard fallbacks; with A0-trained models the
open question stays whether A20 leaf/prior models help. No default change; the candidate stays a research artifact.

Raw replay outputs (CSVs, logs, per-search JSONL with state rows): `/mnt/project-files/ooc-rollout3-a20-lizard-check/ooc-rollout3-lizard-a20-gold-raw.tgz`
(sha256 `ee3b67f5…`). [searches-lizard.jsonl.gz](searches-lizard.jsonl.gz) holds every search's root summary
(without the state row). [report.json](report.json) and [compare.json](compare.json) are the scorer outputs.

Reproduce: §425 `build_inputs.py` into `~/g`, copy the force files, binary and prior there, `run_lizard.sh`, then
`python3 docs/experiments/evidence/ooc_mcts_a20_gold_20261011/score.py lizard` and
`python3 compare.py docs/experiments/evidence/ooc_mcts_a20_gold_20261011 docs/experiments/evidence/ooc_mcts_a20_gold_20261011`.
