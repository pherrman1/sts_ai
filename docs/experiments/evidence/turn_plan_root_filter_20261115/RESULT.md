# Turn-plan enumeration and a learned plan scorer as a Gumbel root filter, offline (#1058, 2026-11-15)

**Question (Philipp, 2026-11-15 17:08 CET, "Öffne ein Thread pro Issue ... und arbeite das jeweils ab"):** issue #1058
ports spire-mentor's turn-plan root filter: enumerate the deterministic plans of a decision, score them with a small
learned model, and let the Gumbel root only search first actions of the best plans. Does such a filter keep G16 + mb4's
decisions while saving enough root simulations to pay for what it drops?

Offline only. No game seed is played; the data are §797's recorded roots.

## Data

- **Roots:** §797's budget-ladder corpus (seeds 111980000-111980255, 256 G16 + mb4 runs, share
  `budget-ladder-roots/units`). The corpus has 155,598 root rows; 145,727 are used (searched roots with ≥ 2 edges, a
  Gumbel pick, and a visited pick). Each row has the root's wire state, its edges with the g7f_E root prior, visits and
  the played 16k tree's max-backed Q (`qBacked`), and G16's pick (`gumbelChoice`).
- **Enumerator:** `search::enumerateTurnPlans` (`src/sim/search/SilverTurnPlan.cpp`), run through
  `one_combat turnplanenum` (`apps/one_combat/turn_plan.cpp`) on main 6126315b plus this change. A plan ends at
  END_TURN, at the first action that advances a combat RNG stream (Silver's own chance test from the expansion), or
  when the fight ends. Silver's canonical root edges are used. States are merged by `hashBattleState`. A plan's
  first-action set is every root action from which a line reaches it. A plan's `length` is the depth at which the
  depth-first search first reached its state, not necessarily the shortest line. A CHANCE plan's features come from
  the state after its stochastic action under one fixed search-RNG realisation (the `plannerRoot` key): deterministic,
  but a single sample. Caps: 512 plans or 20,000 states; on a cap
  the root stays unfiltered. The g7f_E policy (`STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt`) gives each
  plan the summed log prior of its best line. Every root action of every row mapped to a recorded edge (0 mismatches).
- **Scorers** (`tools/turn_plan/filter_eval.py`):
  - `prior`: g7f_E root prior (the baseline, = E1's candidate rule).
  - `planprior`: no learning; each action gets the best plan's summed g7f_E log prior among the plans it starts.
  - `plan_mlp`: a 2 × 64 MLP on 32 hand-built end-state and context features (spire-mentor's 18 + 6, adapted).
  - `plan_mlp+prior`: the same MLP plus the plan's log prior, the best line's first-action prior, and a learned
    weight on the action's own log prior.
  - The learned scorers give each action the logsumexp over the plans it starts. They are trained with softmax
    cross-entropy against G16's pick, cross-fitted by run (5 folds by seed hash, 6 epochs, torch 2.15 CPU, seed 20261115).
- **Filter rules:**
  - Keep the top m actions by the scorer, with m = n − 1, n − 2, ceil(n / 2), 4 or 6.
  - spire-mentor's rule: top-K plans (K 3 or 6) plus anchors (a winning plan, max enemy damage, max block, the prior's
    greedy line). The root keeps their first actions.
- **Metrics (per root, averaged):**
  - Recall: G16's pick kept. The flip rate is 1 − recall.
  - Regret: Q_ref(best visited edge) − Q_ref(best kept edge), in the played tree's max-backed Q (§797's currency).
  - Saved: the share of the root's visits on removed edges, a stand-in for the simulations a filtered search would
    not spend there.
- **Exchange rate (Inference):** §797's uniform loss curve (8k 0.57, 16k 0.51 Q per decision) gives about 0.06 Q
  per budget doubling near 16k. A filter saving a share s of the root budget is credited 0.06 · log2(1 / (1 − s)) Q.
  **Net = credit − regret.** A filter is worth an equal-CPU test only if its net is clearly positive.

## Result

Enumeration (issue step 1), by room group over 155,598 rows:

| group | roots | cap rate | plans median / p90 | states median | CPU mean / p99 |
|---|---:|---:|---:|---:|---:|
| hallway | 66,998 | 7.0 % | 16 / 144 | 10 | 0.49 / 3.8 ms |
| elite | 42,679 | 7.1 % | 14 / 143 | 10 | 0.49 / 3.8 ms |
| boss | 32,864 | 7.8 % | 15 / 144 | 10 | 0.51 / 3.9 ms |
| Act 4 | 13,057 | 8.4 % | 15 / 150 | 8 | 0.52 / 4.0 ms |

Enumeration costs well under 1 % of a 16k search (about 720 ms per decision in §797).

Filter quality, all 145,727 roots (`results/result.json`, `results/eval.log`):

| rule / scorer | recall | regret Q | saved | credit Q | net Q |
|---|---:|---:|---:|---:|---:|
| n − 1 / prior | 96.85 % | 0.097 | 10.5 % | 0.010 | −0.088 |
| n − 1 / plan_mlp+prior | 97.26 % | 0.074 | 10.2 % | 0.009 | −0.065 |
| ceil(n/2) / prior | 85.65 % | 0.259 | 26.8 % | 0.027 | −0.232 |
| ceil(n/2) / planprior | 83.21 % | 0.332 | 28.9 % | 0.030 | −0.302 |
| ceil(n/2) / plan_mlp | 87.10 % | 0.246 | 25.6 % | 0.026 | −0.220 |
| ceil(n/2) / plan_mlp+prior | 88.86 % | 0.193 | 24.8 % | 0.025 | −0.169 |
| top 4 / prior | 91.27 % | 0.145 | 14.6 % | 0.014 | −0.131 |
| top 4 / plan_mlp+prior | 93.53 % | 0.109 | 13.2 % | 0.012 | −0.097 |
| top 6 / prior | 97.49 % | 0.042 | 4.9 % | 0.004 | −0.038 |
| top 6 / plan_mlp+prior | 98.27 % | 0.033 | 4.3 % | 0.004 | −0.029 |
| top-6 plans + anchors / plan_mlp+prior | 97.79 % | 0.038 | 5.8 % | 0.005 | −0.033 |
| top-3 plans + anchors / plan_mlp+prior | 92.76 % | 0.123 | 13.7 % | 0.013 | −0.111 |

- Every scorer and rule has a negative net, in every room group. The best net is top 6 by plan_mlp+prior (−0.029 Q,
  recall 98.3 %); spire-mentor's rule follows at −0.033 (recall 97.8 %). The boss and Act-4 groups are the worst: at ceil(n/2),
  plan_mlp+prior's regret is 0.29 (boss) and 0.36 (Act 4), against 0.10 in hallways.
- The best learned scorer (plan_mlp+prior) cuts the prior's regret by about 25 % at equal width (ceil(n/2): 0.193 vs
  0.259; n − 1: 0.074 vs 0.097). Plan features alone (plan_mlp) are about as good as the prior. The untrained plan
  prior is worse than the prior.
- spire-mentor's kill rule holds: recall at top-6 plans ∪ anchors is 97.8 %, ≥ 95 % and above the prior's top 6
  (97.5 %). Its net is still −0.033 Q: the kept set is 89 % of the actions, so it saves little, and the 2.2 % of G16
  picks it drops carry most of the regret.

## Interpretation (Inference)

- A root filter pays only if its regret stays below the budget it frees. In this data, removing even the single
  lowest-ranked action frees about 10 % of the root visits, worth about 0.01 Q. The best scorer still loses 0.07 Q
  there, because G16 picks the action the scorer ranks last at 2.7 % of roots. To break even at ceil(n/2), a
  scorer would need a regret of about 0.025 Q, 10× below the prior's; the plan scorer gets 1.3× below it.
- Recall alone overstates a filter. Recall ≥ 95 % is reachable only when the filter removes almost nothing. §791's
  whole-run result (E1, prior top-4 at 8k WORSE, about the full loss of halving the budget) agrees with this
  accounting: top-4 / prior has net −0.13 Q here.
- The saved share is a proxy. A narrower root also redistributes its halving phases, and the evaluator's Q of
  edges eliminated in phase 1 rests on fewer visits. Both effects are small next to the gap between regret and credit.
- Bigger scorers (a card embedding, end-state CombatNet features, plan-level Q labels from 500-sim pricing as in
  spire-mentor) could narrow the gap. They would have to close a further factor of about 8 (0.193 → 0.025 Q), which a 25 % gain does not
  approach. T1's distilled net moved hit@4 from 88.6 % to 91.9 % (cheap-combat step 0) and still lost in §791.

## Reproduce

From the repository root, with the release build of this commit and the §797 tars from the share:

```bash
python3 tools/turn_plan/extract_roots.py /mnt/project-files/budget-ladder-roots/units DATA
zcat DATA/roots_wire.jsonl.gz | split -n r/4 -d - DATA/chunk_
one_combat turnplanenum names DATA/names.json
for i in 0 1 2 3; do   # any positive weight gives the same normalized prior
  STS_SILVER_ROOT_PRIOR=models/combat_policy_mlp_g7f_E.txt STS_SILVER_ROOT_PRIOR_WEIGHT=400 \
    build/linux-gcc-release/one_combat turnplanenum DATA/plans_$i.jsonl < DATA/chunk_0$i &
done; wait
python3 tools/turn_plan/filter_eval.py --roots DATA/roots_compact.jsonl.gz \
  --plans DATA/plans_0.jsonl DATA/plans_1.jsonl DATA/plans_2.jsonl DATA/plans_3.jsonl \
  --names DATA/names.json --out results/result.json --epochs 6   # hidden 64, seed 20261115 (defaults)
```

Run the binary from the repository root (`models/` paths are relative).

## Decision

NOT_PURSUED: the offline gate failed. No online root filter is built, no equal-CPU test or whole-run gate is proposed, and
nothing changes by default. The enumerator stays as a research tool: `one_combat turnplanenum`, and ctest
`turn_plan_enum` on four recorded roots. The issue's step 5 (plans as macro actions for a search-free policy) would
reuse it. That needs its own question.

Seeds: none played (§797's 111980000-111980255 reused as data). Cost: about 4 CPU-minutes enumeration, about 30
CPU-minutes training and evaluation (cloud, 4 cores).
