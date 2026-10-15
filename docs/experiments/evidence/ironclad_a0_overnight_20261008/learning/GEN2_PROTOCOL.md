# GEN=2 public-continuation contract and cost canary

**Superseded, unlaunched:** the coordinator held this source736d proposal after confirming optional Ruby RECALL remains in the keys-off candidate set. The teacher/freeze files below remain immutable custody records. Do not launch them. The four CF source seeds remain unopened; a new reviewed producer and new freeze directory are required for the corrected baseline.

Status: **FROZEN; NOT LAUNCHED**. Owner: learning specialist; launch remains with the coordinator after capacity is released. Independent integrity review accepts the four-source contract/cost canary only. Frozen producer source `736d1ff7e61725d9c6a50326064b2e3060ce6ae4`, binary SHA256 `3f69f5fd251ac699580bca8eb8da707282c77bc5263732f10e83f8e2670aba2d`; freeze is `learning/gen2_canary_736d/freeze.json`, SHA256 `119a2472e515ee44a07a676e93b20dd0b645205f9e2355a58a3df78b75f82e0a`.

Question: can existing GEN=2 produce complete, publicly conditioned sibling labels under the current fair-corrected Fprod continuation cheaply enough to support a decision-level challenger? Competing explanations are weak V4 action ranking, noisy labels at small K, and feature/teacher mismatch. This canary measures contract and cost, not playing strength.

## Frozen proposal

| Item | Canary | Conditional next tranche |
|---|---|---|
| Source seeds | `610084000..610084003` (4) | `610084100..610084131` (32), new discovery sources |
| Screens | `CARD_REWARD,BOSS_RELIC` | same |
| Retained states | at most 2 per source; producer takes at most one per type | same |
| Futures/option | K=4 | K=8 |
| Selection futures | k=0,1 | k=0,1,2,3 |
| Independent evaluation futures | k=2,3 | k=4,5,6,7 |
| Max branches | 4*2*6*4=192 plus 4 source trajectories | 32*2*6*8=3072 plus 32 sources |
| Concurrency | at most 4 independent processes, OMP/BLAS=1; campaign total at most 6 | decide from canary cost, max available coordinator allocation |
| Stop budget | 30 minutes wall per source process; retain all incomplete files | freeze total CPU/wall cap from canary before launch |

All use A0, Ironclad, project-fair combat, `STS_COLLECT_KEYS=0`, `STS_STOP_AFTER_ACT=3`, `STS_OOC_MCTS=0`, and reviewed `STS_OOC_PUBLIC_FUTURES=8`. Continuation is fair-corrected Fprod, with exact-root budgets off, adaptive off, learned stop on, allocated reuse cap 32768, original V4 strategic gates/margins. Do not substitute the old `run_corpus.sh` environment: it lacks the new public-futures flag. No training, GPU work, final confirmation seeds, or production-model change in this canary.

Freeze `one_combat vwinrefreshpolicyspec` under that exact clean environment. Use existing `ooc_cf_pilot_20261007/make_teacher.py` to construct the ordinary learned-stop teacher, then bind **all effective STS variables including the new public-futures flag and Act-3 cutoff** in its environment. Recheck teacher `ooc_policy` equals the native effective policy. The new policy field must be serialized by the fairness implementation; reject a teacher that merely records the environment flag while its policy ignores it. Freeze source SHA, immutable binary SHA256, teacher SHA256, all loaded model hashes, and the canary seed list before source trajectories run.

Per-source command, with absolute paths and the clean frozen teacher environment:

```text
bash tools/seed_guard.sh IMMUTABLE/one_combat ooccfpilotgen 1 NEW/seed-610084000 610084000 NEW/teacher.json 4 2 1 2 CARD_REWARD,BOSS_RELIC
```

Repeat for the other three explicitly allocated source seeds, each with a fresh output prefix; no auto-resume, deletion, replacement seed, or silent retry. `CARD_BOSSES=1` is syntactically required but ignored by GEN=2. The continuation index k is hashed with source seed and decision index; it is shared across sibling actions. Sources cannot be divided across learned-data partitions. Different sources and historical inspected decisions cannot enter final confirmation.

## Gates and analysis

1. Verify schema `ooc_cf_pilot_v2`, exact source/binary/teacher/policy identity, requested seed coverage and screen filter, all file hashes, finite CPU values, every source `trajectoryValid=1`, one chosen option per state, 1..6 retained semantic options, chosen/skip retention, no duplicate canonical card-occurrence classes, one row for every retained option and k, and identical futureSeed across siblings at each k. Any supplied source fatal/quarantine/health counters must be zero. Current GEN2 does not separately serialize those counters: `trajectoryValid` is the available source gate and the verifier reports that limitation. Existing manifest lacks uncapped action counts; retained completeness is checkable, full legal-action coverage needs source instrumentation/review. The chosen option is the actual captured source-policy choice, not an assumption that the V4 gate owned every action.
2. Count every invalid/error/no-map/unfinished branch. Existing code requires `mapRecorded` to mark GEN=2 valid, even when `finalWon` is terminal; any such row blocks training reuse. Never silently drop it. This is a producer contract limitation to investigate, not evidence its action is poor. Every valid label must join one first-post-decision-MAP feature row. Only finalWon is the target; first-boss win/HP are diagnostic.
3. Audit that the first MAP row is after finishing the screen; source implementation calls `vwinResumeContinuation` before recording it. Exclude hidden-future queue features from new predictors. Post-action next-act maps are public *after* the action, so action selection must average over legitimately sampled maps/futures rather than use the realized future map.
4. Before viewing evaluation k, choose the rollout action from selection-k mean finalWon. Resolve exact ties in favor of the source/chosen option if tied, otherwise semantic-key order. Save the selected-action artifact and its SHA256 before reporting evaluation-k outcomes. Evaluate that fixed action and source choice on evaluation-k only, paired by k. A same-k optimistic best action is an oracle diagnostic and must not be reported as achieved improvement. Report both per-source differences and pooled point estimate; four sources cannot qualify a policy.
5. Report total/source/branch CPU, wall, number of states per type/act, fights per branch, invalid counts, and projected next-tranche cost. Estimate remaining core-seconds as observed CPU/state-future times proposed state-futures, with the max-source cost as a conservative tail allowance. Do not assume seed count equals state count.

Decision rule: `CONTRACT_CANARY_PASS` only with complete source coverage, 0 invalid/missing branches, faithful public conditioning, exact identity/hash gates, and no unexpected model fallback. A pass permits discussion of the next tranche, not automatic launch. The 32-source K=8 tranche is worthwhile only if it fits the speculative window with at least 30 minutes margin before 07:23 Europe/Berlin and leaves the final confirmation allocation untouched. A failed canary is preserved and diagnosed at the narrowest violated gate.

## Minimal learning alternative after usable data exist

First compare exported historical P0-s0 and F2-s0 predictions averaged across selection-future post-MAP rows with V4 and rollout selection, evaluated only on independent evaluation futures. This is a zero-training representation probe. If model ranking disagrees with independently supported rollout preferences, prepare one fixed public XGBoost absolute-value model on source-disjoint training sources with each source decision receiving equal total weight. Reserve source decisions for independent selection evaluation. A pairwise ranker is a separate later hypothesis and must not be installed as an absolute calibrated leaf. No model training is justified by four canary sources.


## Frozen launcher and receipt check

The existing `runCombatEvalGenSeed` nominal `sims=10000` is not an exact-budget override. Source exploration and every continuation use the same configured native learned-stop backend; `loadWholeCombatTeacher(..., allowLearnedStop=true)` verifies it. The frozen teacher explicitly records `final_boss_binary=false` (the loader also accepts its absence as false). Runtime tree profiles must be nonempty, error-free, source-consistent, and nonadaptive. The verifier reports actual early roots and singleton skips. These profiles interleave source and continuation roots, so they cannot separately prove each branch's policy without the producer source/teacher binding.

From the campaign worktree, the coordinator invokes this command exactly once for each of the four allocated sources, substituting only `610084001`, `610084002`, or `610084003` in both places. The launcher checks frozen identities, refuses any existing output, uses a clean frozen environment plus a tree-profile path, passes through `tools/seed_guard.sh`, and has no scheduling, retries, or replacement sources:

```bash
.venv/bin/python docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/run_gen2_source.py --freeze docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/gen2_canary_736d/freeze.json --seed 610084000 --prefix build/overnight_20261008/learning/gen2-canary-736d/seed-610084000
```

After all four invocations finish, the independent read-only contract/cost check is:

```bash
.venv/bin/python docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/verify_gen2.py --freeze docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/gen2_canary_736d/freeze.json --prefix build/overnight_20261008/learning/gen2-canary-736d/seed-610084000 --prefix build/overnight_20261008/learning/gen2-canary-736d/seed-610084001 --prefix build/overnight_20261008/learning/gen2-canary-736d/seed-610084002 --prefix build/overnight_20261008/learning/gen2-canary-736d/seed-610084003 --out build/overnight_20261008/learning/gen2-canary-736d/contract-receipt.json
```

The verifier checks complete invocation receipts, exact arguments/environment, source/binary/teacher/model hashes, all output paths/bytes/hashes, runtime profile and banners, source trajectory validity, complete retained action/future/MAP joins, coupled future hashes, and invalid labels. It reads labels to validate them but does not emit evaluation outcomes. Selection analysis must still create and hash its immutable chosen-action artifact before evaluation outcomes are reported. This verifier does not authorize a next tranche or model training.

The fixed source list, selection/evaluation k split, 1800-second per-source wall cap, 4-source process cap, and 6-game campaign cap are recorded in the freeze JSON. The launcher cannot enforce the global process cap; the coordinator controls available capacity. Source and branch CPU sums plus per-process wall sums are returned for cost estimation. Any failure preserves all partial output and blocks a clean canary result.
