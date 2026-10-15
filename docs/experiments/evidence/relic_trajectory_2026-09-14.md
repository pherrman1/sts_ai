# Shared relic trajectory residue protocol

Knowledge impact: native trajectory reconstruction and the frozen offline
qualification protocol; no runtime integration or gameplay change.

Baseline after #172: `b5502a84bb41c736fa72b210dc8766e0a25717e6`.
The existing Codex-app-managed worktree passed preflight and pinned-submodule
checks; no additional worktree was created. PR #172 merged at
2026-09-13T22:47:22Z, and baseline HEAD matched remote main.

## Source-derived reconstruction

| Shared residue | Relics | Native saved-counter equation |
| --- | --- | --- |
| turns modulo 6 | Happy Flower, Incense Burner, Inserter | `(pre + residue) mod 3/6/2` |
| attacks modulo 10 | Nunchaku, Pen Nib | `(pre + residue) mod 10` |
| card-use events modulo 10 | Ink Bottle | `(pre + residue) mod 10` |
| shuffle events modulo 3 | Sundial | `(pre + residue) mod 3` |
| Lizard Tail consumed | Active Lizard Tail when both outcomes legal | `pre - consumed` |

Combat initialization supplies the first turn tick in
`src/combat/BattleContext.cpp:168-195`; subsequent ticks share
`src/combat/Player.cpp:524-549`. Pen Nib internally encodes saved value 9 as
-1 (`BattleContext.cpp:209-215`); attack-use updates at 1745-1761 and exit
conversion at 585-591 preserve the saved modulo-ten equation. Ink Bottle
increments in the attack, skill, power, and other-card use paths at
1711, 1828, 1906, and 1975; copied plays that invoke native use events count.
Sundial advances in `onShuffle` at 2863-2870.

`Player.cpp:322-350` checks Fairy Potion before Lizard Tail; Mark of the Bloom
prevents either revival. Lizard Tail never recharges; exit writes consumed
state at `BattleContext.cpp:598-602`. Existing `legal_posts` remains the
conservative source-derived support authority. Inactive or Bloom-blocked
Lizard Tail copies. Neow's Lament decrements once to a minimum of zero;
Omamori copies outside globally excluded Writhing Mass. Burning Blood, Black
Blood, and Meat on the Bone heal HP without changing saved relic data.
Unrecognized counter mutations fail the audit.

## Frozen experiment

Corpus SHA256:
`74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
Nested source split SHA256:
`58e35f9f85eefd7617e616ddbfa7ee227c429ed4d312f7dacd470828f9a09094`.
TRAIN combines nested TRAIN and VALIDATION, HOLDOUT remains nested HOLDOUT.
Only globally supported, potion-certified victories participate.

The 20260912 #172 HP checkpoint is selected by convention and verified against
`a667a3cfa7d7eca3cb07b46f50321e443c75e8a58f7627becb1fd69bf90f08c9`.
Joint potion weights:
`8e04bcd5265fb11b8fa91b4553a84690915f437e7b3afee0b93358e312de3ad6`.
The existing potion encoder also stays frozen; hash:
`2085010f1aeef7a7957cdc45c851b2424d640037fd0fa981eb7ae7274190f6ef`.
HP state embeddings use the qualified HP model's AMP evaluation convention
and are cached as FP32. Decoder arithmetic and optimization are FP32.

Implementation: `tools/combat_transition_relic_trajectory.py`; native rules:
`tools/combat_transition_relic_legality.py`. The module's `RECIPE` freezes
three seeds 20260912/13/14, ten epochs each, AdamW 1e-3, decay 1e-4, batch
2048, gradient clip 1.0, no epoch selection. TRAIN-only bias logits use the
same partial-label likelihood, row weighting, and fixed optimization.
A six-class turn label sums probability over every compatible residue;
multiple relics intersect constraints. No hidden trajectory or RNG inputs.

Primary evaluation sums observed group constraint NLLs, averages paired row
differences over seeds, then bootstraps sources 1000 times. The 95% CI must
be strictly negative to pass. Exact counters are descriptive. Exposure uses
16 HP→potion→relic draws, observed max-HP conditioning, log of mean observed
vector probability, then mean per-row group-normalized excess NLL on
informative rows. Mean excess above 0.1 nat is an exposure gap. Final
qualification also requires zero structural/coherence violations. Positive
primary CI or mechanical invalidity rejects; remaining cases are inconclusive.
No criteria are selected from HOLDOUT results.

Calibration bins compare mode confidence with compatible-label correctness.
Partial turn labels cannot identify full six-class calibration; exact-label
counts and NLL are separately reported. Per-relic counter metrics cover each
listed relic. Absent stochastic-head supervision is reported explicitly and
cannot certify deployment on that unobserved support.

All checkpoints, caches, raw probabilities and trajectories remain external
under `/home/philippherrmann/sts_sweep/runs/relic-trajectory-20260914/`.
Preparation audits every globally supported corpus row, including deaths,
before generating frozen features. Fitting requires a clean independently
reviewed implementation SHA and unchanged cache/recipe/upstream hashes.
Independent implementation review passed before fitting; execution results follow below.

```bash
python3 -m tools.combat_transition_relic_trajectory prepare \
  --output-dir /home/philippherrmann/sts_sweep/runs/relic-trajectory-20260914 \
  --baseline-sha b5502a84bb41c736fa72b210dc8766e0a25717e6
# After independent implementation review:
python3 -m tools.combat_transition_relic_trajectory fit \
  --output-dir /home/philippherrmann/sts_sweep/runs/relic-trajectory-20260914 \
  --baseline-sha b5502a84bb41c736fa72b210dc8766e0a25717e6 \
  --reviewed-sha REVIEWED_SHA
```

## Executed qualification results

**`RELIC_TRAJECTORY_QUALIFIED`** on the audited composed corpus support. Active Lizard Tail remains outside qualified learned support (zero active/supervised rows).

Independently reviewed execution SHA: `66350924cd3b4c7ca82d967e282f68cd677736b2`. All three fixed fits completed before HOLDOUT scoring; no epoch selection, upstream retraining, new collection, gameplay, runtime integration or RNG change.

| Seed | Decoder joint NLL | TRAIN-only prior NLL | Paired difference | Normalized ancestral gap |
| --- | ---: | ---: | ---: | ---: |
| 20260912 | 0.519639530 | 0.530241176 | -0.010601646 | -0.002224881 |
| 20260913 | 0.520132425 | 0.530254280 | -0.010121855 | -0.002137685 |
| 20260914 | 0.519593622 | 0.530250808 | -0.010657186 | -0.002858437 |

Mean paired difference: -0.010460229; 1,000-repetition source bootstrap 95% CI: [-0.013335116, -0.007743432], 1979 eligible source groups. The CI is strictly below zero.

Ancestral mixture joint NLL mean: 0.519052762; teacher-forced mean: 0.519788526. Per-row group-normalized excess: -0.002407001 nat → `ANCESTRAL_OK`. Each seed uses 16 upstream draws per eligible row (406,368 trajectories; 1,219,104 total across seeds). Max HP stays observed.

| Reconstructed metric (mean over fixed seeds) | Decoder | Native + copy-through |
| --- | ---: | ---: |
| Full relic-vector exact | 0.805667113 | 0.792700213 |
| Vector exact where learned counter changed | 0.174612219 | 0.000000000 |
| Token exact | 0.960958156 | 0.958045697 |
| Changed-token exact | 0.222380125 | 0.021159008 |
| Token MAE | 0.108103901 | 0.133442974 |
| Changed-token MAE | 2.209221538 | 3.113374388 |

25,398 row vectors, 147,756 relic tokens; 5,265 rows with changed learned counters and 6,333 changed tokens. Exact modes are descriptive and do not override NLL.

| Head | TRAIN / HOLDOUT supervision | Mean constraint NLL | Mode compatibility |
| --- | ---: | ---: | ---: |
| turns | 18522 / 2213 | 1.267491769 | 0.321283326 |
| attacks | 27906 / 3121 | 2.219669568 | 0.148349888 |
| cards | 9311 / 1133 | 2.321073565 | 0.096498970 |
| shuffles | 8983 / 897 | 0.935635028 | 0.532144184 |
| lizard | 0 / 0 | — | — |

Exact-label counts/NLL, compatible-set calibration bins, active/both-legal Lizard counts and binary metrics are in the machine-readable evidence. Lizard learned NLL/Brier/exact are undefined because no supervised/active row exists.

| Relic | HOLDOUT carrier rows | Token exact | Changed-token exact | Token MAE | Changed-token MAE | Native token exact |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HAPPY_FLOWER | 1664 | 0.357171474 | 0.345503117 | 0.857972756 | 0.864945088 | 0.325120192 |
| INCENSE_BURNER | 596 | 0.221476510 | 0.238555770 | 1.664988814 | 1.631850419 | 0.132550336 |
| INSERTER | 0 | — | — | — | — | — |
| NUNCHAKU | 1658 | 0.141938078 | 0.137666886 | 2.834941697 | 2.790544977 | 0.081423402 |
| PEN_NIB | 1618 | 0.153893696 | 0.144548704 | 2.887721467 | 2.828194817 | 0.077873918 |
| INK_BOTTLE | 1133 | 0.096498970 | 0.087139618 | 3.209179170 | 3.251376741 | 0.091791703 |
| SUNDIAL | 897 | 0.532144184 | 0.481553398 | 0.606837607 | 0.700323625 | 0.425863991 |
| LIZARD_TAIL | 456 | 1.000000000 | — | 0.000000000 | — | 1.000000000 |

Per-relic changed-row/full-vector and native counter metrics, plus descriptive teacher/ancestral slices by act, room, true/sampled loss bins, true/sampled potion use and group count, are retained in the JSON evidence. Sampled loss bins include the actual draw-conditional NLL; mixture-row summaries are separately labeled. No slice changes the decision.

All structural audit counts and all sampled legality, same-group consistency, unsupported mutation and deterministic native mismatch counts are **zero**.

Decoder parameter count: **12895**. Batch-1 FP32 CPU decoder forward: mean **0.034997 ms**, p95 **0.036728 ms**; one thread, ten warmups, 100 measurements. This excludes upstream encoding, sampling and native reconstruction.

External `artifact-hashes.json` records exact cache, checkpoint, prediction and result hashes. Machine-readable summary: [relic_trajectory_2026-09-14.json](relic_trajectory_2026-09-14.json). Checkpoints and raw arrays remain external. Independent implementation review passed; focused relic tests: 12 OK; upstream combined tests: 36 OK before metric corrections; all three affected CTests passed; CMake configure and one_combat build passed; final baseline-range diff check passed. Gameplay, new simulator collection, sampled max-HP composition and runtime integration were not run because they are outside scope. GitHub Linux GCC remains authoritative.

Independent scientific verification replayed all six frozen checkpoints,
checked initialization and ten-epoch batch provenance, recomputed the paired
source bootstrap and ancestral mixture-before-log diagnostic, and checked
all 1,219,104 sampled relic vectors with vectorized native domains/copy/shared
congruence rules. Exit 0; no mismatch beyond checked CPU/GPU roundoff.
Raw command: `python3 /home/philippherrmann/sts_sweep/runs/relic-trajectory-20260914/verify_independent.py`;
external `verification.json` records outcomes and is hashed in the tracked
JSON summary. Linux GCC passed on reviewed execution SHA `66350924cd3b4c7ca82d967e282f68cd677736b2`.
[Frozen recipe JSON](relic_trajectory_recipe_2026-09-14.json).
