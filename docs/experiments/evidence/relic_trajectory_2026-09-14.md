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
No fitting or predictive qualification is claimed before that review.

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
