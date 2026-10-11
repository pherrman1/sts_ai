# §425 — OOC MCTS root picks scored on the A20 gold decisions: not shown better than the heuristic (2026-10-11)

**Question (Philipp, 2026-10-11):** how often does OOC MCTS pick the best option at A20, scored against
the §419 gold labels? All MCTS models (V4 prior, `screengbm`/X2-B leaf, pathb-r2 CTM, `v_win`) are A0-trained.

## Inputs

- Gold set: `/mnt/project-files/v4-a20-retrain/gold-2c89ed97/w00..w24` (read only). 524 labeled decisions
  (409 with ≥2 options) from `strategicgen2` at `2c89ed97`, ASC 20, seeds 69100000+1000W+k, every option played to
  the end of the run 16 times (Silver 2k + prior w400, heuristic continuation); label = mean floor reached (`labelFloor`).
- Code: run commit `d93fad14` (adds `STRATEGIC_MCTS_TARGETS`/`_FORCE`/`_REPS`/`_SEED_SHIFT` to `strategicgen2`,
  default off), binary sha256 `cd0bb658…` (see `inputs-sha256.txt`). One cloud container, 4 CPU, 1 OMP thread per process.
- MCTS search run seeds: gold seed + 3,900,000 + 100,000·rep, rep 0..3 (block 73000000–73324999), decision index = gold decIdx.

## Arms (`env_common.sh`)

| arm | settings |
|---|---|
| `prod` | §411 `prod` / §414 settings: V4 prior, 2048 sims, cpuct 1.5, widen 2/0.5, visits selection, early stop, default `screengbm` leaf (X2-B anchor), pathb-r2 CTM + escape fallback, active Lizard on |
| `rollout3` | §422 profile: as `prod` but `LEAF_VALUE=native`, `LEAF_COMBATS=3` |

## Method

1. `build_inputs.py` assembles the gold rows, `targets.csv` (labeled decisions) and `force.csv` (the recorded chosen
   action per decision).
2. The replay runs the gold main run with the same environment but without Tier-B branching, executes the
   **recorded** action at every decision (`STRATEGIC_MCTS_FORCE`), and at each target decision runs 4 OOC MCTS searches
   on the pre-decision state (V4 is loaded for the search only; the replayed run never sees it). It stops after the
   seed's last target.
   Re-running the gold policy instead does not reproduce the gold trajectories: on seed 69100000 the replay
   took a card where the gold run skipped (decision 116). Cause (verified in review): `finishOocCounterfactual`
   (`apps/one_combat.cpp`) sets `t_curPath = nullptr` on return and `strategicgen2` never restores it to `&path`
   (`counterfactual_gen.cpp` does), so from the first decision with options on (the reservoir fills its first
   slots, and labels are computed before the policy acts) the gold run's main-trajectory policy ran path-blind
   (readers fall back to an empty path; no undefined behaviour). With a review-only patch setting `t_curPath =
   nullptr` at labeled decisions and replaying unforced, seeds 69100000 and 69101007 reproduce the gold rows exactly.
   The labels themselves (branches) are unaffected. **Unverified:** this likely affects every `strategicgen2` run
   with branching, possibly including the A0 corpus behind the deployed V4.
3. `verify.py`/`score.py` compare every replayed row (state + candidate features, `chosen`) with the gold row; a target
   is scored only if all rows of its seed up to and including the decision match.
4. 40 seeds diverged where several actions had the same successor fingerprint (mostly event pages, card-select
   origins). `fix_force.py` tried the alternatives; 25 seeds were repaired (`repaired_seeds.txt`, `force_fixed.csv.gz`)
   and rerun for both arms; 15 stay partial (`fix_log.csv`).

## Coverage

398 of 409 multi-option targets searched, 386 state-verified (both arms). Not owned per search (of 1,544):
`prod` 4 boundary + 28 picks outside the labeled set (e.g. potion discard-to-take); `rollout3` 370 support aborts
(Lizard Tail 316, `hp_envelope` 54), 4 boundary, 6 outside the set. In live play an unowned decision falls back; the
"live" rows use the gold-run choice as fallback. `rollout3` ran on the production pathb-r2 CTM, not the §423 Lizard-capable research candidate (`STS_CTM_RESEARCH_CANDIDATE_MANIFEST`, manifest `64da1776…`); that is the cause of the Lizard Tail aborts, the large majority of its aborts (a follow-up check on 4 gold seeds: 7/8 searches aborted on the production CTM, 0/8 on the candidate; raw `/mnt/project-files/ooc-rollout3-a20-lizard-check/a20-lizard-check.tgz`).

## Results (`score-output.txt`, `report.json`; 10,000-sample decision bootstrap, 95% CI)

On the 378 verified decisions with a recorded choice:

| picker | strict top-1 | tie-aware top-1 | mean floor regret |
|---|---|---|---|
| uniform random (386) | 0.260 | 0.260 | 4.88 |
| heuristic (gold-run choice) | 0.344 [0.296, 0.394] | 0.276 [0.238, 0.315] | 4.55 [3.83, 5.33] |
| OOC MCTS `prod` (live) | 0.252 [0.210, 0.295] | 0.280 [0.242, 0.318] | 4.35 [3.68, 5.09] |
| OOC MCTS `rollout3` (live) | 0.286 [0.247, 0.327] | 0.295 [0.260, 0.332] | 4.22 [3.57, 4.92] |

Paired vs the heuristic: `prod` Δregret −0.20 floors [−0.89, +0.49], Δstrict top-1 −0.092 [−0.151, −0.035];
`rollout3` Δregret −0.33 [−0.77, +0.12], Δstrict top-1 −0.058 [−0.103, −0.014]. `rollout3` owned only (188):
regret 4.38, Δ −0.24 [−0.99, +0.56].

Strict top-1 follows GOLD-RESULT.md (gold-best = first argmax in row order; random = 1/n), which reproduces its
random 0.260 and heuristic 0.354 on all 409. 144 of 409 decisions have tied best labels, and on reward screens the
heuristic's first pick is often the gold pile (61 of 204), which ties with the other pickups and comes first in row
order; MCTS collects forced gold at the root and never picks it. That is why the strict metric penalizes MCTS on
reward screens (0.12 vs 0.29) while the tie-aware share there is 0.19 vs 0.21. Regret and tie-aware top-1 are the
fair comparison.

Searches are nearly deterministic: the modal pick across the 4 search seeds covers 98.5% (`prod`) and 95.3%
(`rollout3`) of searches. `prod` agrees with the heuristic on 46% of owned decisions.

## Interpretation

**Inference:** at A20 neither OOC MCTS profile picks measurably better than the heuristic, and all three are close
to random on these labels (regret 4.2–4.6 vs 4.9 floors; median label spread best-worst is 7 floors). This matches
§419 (V4 Q top-1 0.31). Caveats: every MCTS model is A0-trained; the gold labels have their own noise (16 playouts,
median best-vs-second gap 1 floor); the "heuristic" baseline is the gold run's own choice, i.e. a path-blind variant
of the production heuristic. The CIs still allow a gain of up to about 0.9 floors.
Rerun with A20 floor/win models once they exist (same targets and force file; only the model env changes).

Raw outputs (replay CSVs, logs, per-search JSONL with state rows): container-local tar
`ooc-mcts-a20-gold-raw.tgz` (8.3 MB); the shared folder was at its file limit, so it was not uploaded.
`searches-{prod,rollout3}.jsonl.gz` here hold every search's root summary without the state row.
