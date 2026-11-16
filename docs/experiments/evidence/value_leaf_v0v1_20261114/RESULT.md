# Value-net leaf V0 / V1 (offline): is a learned value worth more than Silver's rollout as the leaf value? (result)

Status: final (offline, 2026-11-14 / 2026-11-16). Combat plan stage "value net as leaf"
([plan](https://claude.ai/artifact/KUwu6EgSVz44DEt2UXYGeh)). Philipp asked on 2026-11-14 for a combat value net that
measurably beats a single Silver rollout as the leaf value ("Ja dann versuch das value Netz"; "Kann auch etwas teurer
sein"). No gameplay change; the fight test is V2 ([../value_leaf_v2_20261116](../value_leaf_v2_20261116/RESULT.md): NOT_SHOWN).

## Question

Silver values every new tree leaf by one playout to the end of the fight (`rolloutToEnd`; in boss rooms and Act 4 a
g7f_E prior playout). Can a net value that leaf better than one rollout, per unit of CPU?

## Data and truth

- **Roots:** the played decision roots of D2 (§787's Gumbel-16k + max-backup teacher runs, seeds 111950000-111954095)
  whose run has T1's `split_of(seed) = (seed * 2654435761 mod 2^32) mod 10 = 0`, the gate split that no T1 / V1 net
  trained or validated on (`extract_split.py`). 564 runs, 60,869 searched multi-edge roots.
- **Truth T** of a root edge = its `qBacked` (max-backed value) in the played 16k G16 + mb4 search, for edges with at
  least 256 visits. Only roots with two or more such edges count.
- **Estimators per edge**, from the edge's child state (`one_combat leafbench OUT 256 K [NET.ctn]`, code f2852b16,
  D2's `record_env.sh`, so rollouts are the production playouts of that room):
  - `Rk`: the mean of k Silver rollouts (k = 1 is today's leaf); V0 drew 8 per edge, the boss / Act-4-elite rerun 32.
  - `NET`: T1's N_f1 value head (§787) calibrated per encounter (cross-fitted by run); `NETd` its root-demeaned
    (difference-calibrated) variant.
  - `QNET` (V1): the new per-edge Q head of the parent root, one forward pass per root (`leaf_v1_predict.py`).
- **Metrics** (`analyze.py`, run-clustered bootstrap, 1,000 resamples, seed 20261114):
  - Sibling-difference MSE against T's differences (all edge pairs of a root, each root weight 1) and level MSE.
  - Order accuracy on edge pairs with |ΔT| ≥ 2 (pair-pooled): the share of pairs the estimator orders like T.
  - `k_ord`: the number of rollouts whose mean orders as well, log-linear on the R1..R32 curve, with the bootstrap CI.
  - Cost ratio c = one forward pass / one rollout on the same roots and core; a forward serves all edges of a root
    (6.1 rollout edges per boss / Act-4-elite root).
- Roots with any rollout more than 500 from the edge's T are dropped (`STS_V0_DROP_OUTLIER=500`; Silver's loss
  shaping gives rare playouts down to −67,000): 8 of 60,869 in V0, 24 of 17,479 in the 32-rollout set.

## Decision rule (fixed before V1 was trained)

After V0 showed that its first rule (net beats R1 in level MSE) was met by trivial baselines, the rule was revised and
recorded in the plan before any Q head existed:
- **LEAF_PAYS** if lo95(k_ord) ≥ c on boss rooms + Act-4 elites pooled, and no boss act is significantly worse than
  one rollout.
- **LEAF_HELPS** if significantly better than R8 at any cost.
- Else **NOT_SHOWN.**

## V0 result (N_f1's value head, 2026-11-14)

All rooms (60,861 roots, 363,373 edges): order accuracy R1 0.728, R8 0.802; NET 0.748 (k_ord 1.7), NETd 0.771 (3.1).
Boss + Act-4 elite: NET 0.691 against R1 0.688 (+0.003 [−0.003, +0.008]), k_ord 1.1 at c = 26 (N_f1 is d 128 /
4 layers, 4.2 ms per root against 0.18 ms per boss playout). → **NOT_SHOWN.** The value head of a policy-trained net
predicts the fight's outcome but not the differences between sibling actions, which is what a leaf must get right.

## V1: a per-edge Q head trained on sibling differences

- **Head** (`tools/combat_net/model.py`, `--q-head`): an MLP on [CLS, action token, target token] per edge →
  Q in Silver score units (scale 100). Loss on edges with ≥ 64 visits: Huber level term + 4 × the within-root
  residual variance (the pair term), against `qBacked` (`--q-source backed`).
- **Data:** T1's tensors of D2 (3.33 M roots; training splits 2-9, 2.67 M rows; validation split 1, 330,542 rows).
- **Nets** (PC, RTX 3060 Ti):
  - `V1_d64`: d 64, 2 layers, 325,465 parameters, from scratch, 3 epochs (31,311 steps, 425 s).
    `model.pt` sha256 8d6b6330…e926, native `V1_d64.ctn` sha256 4584901e…4e4c.
  - `V1_d128`: d 128, 4 layers, 1.32 M parameters, initialised from N_f1, 1 epoch.
    `model.pt` sha256 4e0a7bb4…17f7, `V1_d128.ctn` sha256 0b55a302…c18c.
- **Validation split** (edges ≥ 256 visits): order accuracy d64 0.822 (boss 0.790), d128 0.826 (boss 0.792);
  sibling-difference MSE 93.4 / 88.9 against 220.9 for "all siblings equal".

## V1 result on the gate split (2026-11-16)

Boss rooms + Act-4 elites, 32 rollouts per edge (17,455 roots, 105,821 edges, 519 runs):

| Estimator | Order accuracy | k_ord [95%] | Cost per root (rollouts) |
| --- | --- | --- | --- |
| R1 (today) | 0.687 | 1 | 6.1 |
| R8 | 0.753 | 8 | 49 |
| R32 | 0.797 | 32 | 195 |
| N_f1 value (V0's 8-rollout set) | 0.691 | 1.1 | 26 |
| **V1_d64 Q head** | **0.787** | **23.4 [20.2, 26.9]** | **6** |
| V1_d128 Q head | 0.790 | 26.0 [22.6, 30.0] | ≈ 24 |

- By room (d64, k_ord [95%], c): act-1 boss 10.4 [7.9, 13.7] at c 8; act-2 boss 26.2 [19.4, >32]; act-3 boss 27.2
  [22.6, >32]; Act-4 boss 27.5 [18.1, >32]; Act-4 elite 18.8 [13.4, 27.2], all at c 5-7. No boss act is worse than R1.
- Cost: d64 forward 1.06 ms per root, a boss-room playout 0.18 ms (c = 6.0); one forward values all 6.1 edges, so
  the net costs about one rollout per edge.
- All rooms against 8 rollouts (60,822 roots): Q head 0.821 [0.817, 0.824], R8 0.803 [0.799, 0.806]. Act-1 hallway
  and elite roots are the only cells where the Q head is not ahead of R8 (k_ord 3.8 and 7.9); hallway playouts are
  much cheaper than boss playouts (0.07 ms on average over all rooms), so c is far higher there.
- Level MSE is worse than R8's (all rooms 314 vs 109): the head ranks siblings well but its absolute level is off.

→ **LEAF_PAYS** for `V1_d64` (lo95 20.2 ≥ c 6; act-1 boss lo 7.9 ≥ 1).

## Interpretation (Inference)

- A Q head trained on sibling differences of the teacher's own backed values orders the actions of a boss root like
  the mean of about 23 rollouts, at the cost of about one. A value head trained on fight outcomes does not.
- Caveats: only played roots were tested, not the deeper and odder states a search tree visits; T comes from the
  same search family as the training targets (the net may share the teacher's biases, which would flatter it against
  rollouts); the level error matters wherever net-valued leaves are compared with exact terminal values or with
  rollout-valued nodes. Only a fight test can say whether this becomes play strength.

## Decision

LEAF_PAYS (offline). V2 then tested `V1_d64`'s Q head as Silver's leaf value in boss fights behind
`STS_SILVER_LEAF_QNET` (default off): it played clearly worse, so the offline result did not carry over. No default change. Seeds: none new (D2's gate split).
Cost: leafbench on one 4-core cloud container (V0 and the 32-rollout rerun), under 0.5 GPU-h training (PC).

## Files

- `analyze.py` (this directory): the V0/V1 analysis (`STS_V0_DROP_OUTLIER`, `STS_V0_QNET=1` for the Q head).
- `extract_split.py`, `run_v0.sh`: the gate-split extraction and the 4-lane leafbench run.
- `results/`: `v0_nf1_drop500.json`, `an8_V1_d64.json`, `an8_V1_d128.json` (all rooms, 8 rollouts),
  `an32_V1_d64.json`, `an32_V1_d128.json` (boss + Act-4 elite, 32 rollouts).
- `tools/combat_net/leaf_v1_predict.py`: writes the Q head's per-edge values into leafbench rows.
- Raw data (share): `/mnt/project-files/combat-plan/value-leaf/v0/` (leafbench shards, fights) and `v1/` (nets,
  32-rollout shards, analyses, `SHA256SUMS`).
