# Corrected GEN2 four-source canary addendum

Preparation status: **FROZEN_NOT_LAUNCHED; independent freeze/protocol review PASS.** Runtime launch/completion status is recorded separately by the coordinator. This new package supersedes the unlaunched source736d canary for execution. `gen2_canary_736d/`, its original preparation script and original protocol remain intact. No source trajectory was launched during this preparation.

The purpose remains a contract, public-conditioning and cost canary for GEN2 CARD_REWARD and BOSS_RELIC siblings. Competing explanations are weak V4 action ranking, noisy K4 labels and feature/teacher mismatch. This canary is not a training run, online policy qualification or population-strength comparison.

## Frozen identities and corrected baseline

| Component | Identity |
|---|---|
| Source | `3ed91ab3491a4cdc1a7de687b2ad87dcc7774fc0` |
| Immutable binary SHA256 | `27a78efd3f5da731897d36dd9b50a622d2ace4f54dae69dfc157bf6712b027c7` |
| Freeze | `learning/gen2_canary_3ed9/freeze.json` |
| Freeze SHA256 | `8c7a1b9060159983b3a09e43e673e891c59be918e82c405784455143235d10bf` |
| Teacher SHA256 | `cf30c66df49aa9a11097320511b5bc70564e838541089465e3c315c2c4815040` |
| Native policy SHA256 | `1d7f29703b20fbb4f9f37740438a316f5ae144a3d2133eec1e56e8239bcec188` |

The clean effective environment is the `Fprod` profile from `protocols/corrected_canary.json`, plus the frozen executable source identity. It uses A0 Ironclad, public encounter marginalization8, optional Recall exclusion1, keys collection0, Act-3 cutoff, MCTS0, REST_WIN0, unchanged V4 gates/margins and original loaded models. Native policy serialization explicitly has `flags.skip_optional_recall=true` and `parameters.native_ooc_public_futures=8`; the full environment is bound identically in the teacher and freeze. The teacher records learned stopping, native Silver, 10,000 cap, exact-root0, adaptive0, allocated reuse32768 and `final_boss_binary=false`. This is a corrected policy reference; old numerical results are not relabeled or reused.

The optional Recall filter covers V4 REST candidates and random fallback under this profile. Sole-legal-action Recall remains an explicit exception. The source and every continuation honor the configured learned-stop teacher; nominal sims10000 is not an exact-root override. The original three model artifacts and compiled stop-model source hash are verified against corrected runtime custody before freezing.

Only the native, seed-free `vwinrefreshpolicyspec` query ran. Its command, zero exit code, native model-load/banner log and exported policy are retained in the new directory. The existing maker constructs the teacher, after which all effective environment variables and `final_boss_binary=false` are bound. Preparation is reproducible with `learning/prepare_gen2_canary_corrected.py`, which refuses an existing destination.

## Allocation and process limits

| Item | Frozen value |
|---|---|
| Source seeds | `610084000,610084001,610084002,610084003`; previously reserved and unopened at authorization |
| Generation | GEN2, source games1 per invocation, at most2 states/source |
| Types | `CARD_REWARD,BOSS_RELIC`, at most one retained state/type/source |
| Futures | K4, actual k0..3 |
| Selection block | k0,1 |
| Evaluation block | k2,3 |
| Maximum work | 4 source trajectories + 192 sibling continuations; actual state/option coverage can be smaller |
| Process limit | At most2 GEN2 processes; each OMP/BLAS thread count1 |
| Shared campaign limit | At most6 game processes total; authorization allocation is3 development +1 targeted REST +2 GEN2 |
| Timeout | 1800 seconds wall per source process |

The runtime-canary protocol's `allowed_seeds` is not reused as a GEN2 allocation. This separate reviewed freeze authorizes only the four named counterfactual-reserved sources. The coordinator controls process capacity; the single-source launcher does not enforce aggregate concurrency. Do not launch if the shared six-process cap would be exceeded. Preserve any timeout/failed partial outputs. No retries, replacement sources, overwritten prefixes or automatic extension are authorized by this canary.

## Launch and verification handoff

The coordinator can run the existing dynamic-freeze launcher once per named source after review. Substitute only each reserved source in both seed and prefix. This command is a handoff template and was not executed during preparation:

```text
python3 docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/run_gen2_source.py --freeze docs/experiments/evidence/ironclad_a0_overnight_20261008/learning/gen2_canary_3ed9/freeze.json --seed 610084000 --prefix build/overnight_20261008/learning/gen2-canary-3ed9/seed-610084000
```

The launcher binds binary/teacher/model hashes, adds only the runtime tree-profile path, refuses all existing outputs and calls `tools/seed_guard.sh` internally. Source and sibling output identities remain joined to the same frozen teacher.

After all four processes finish, run `learning/verify_gen2.py` with this freeze, all four `--prefix` paths and a fresh `--out`. Its existing strict source/output/model/semantic/future/MAP/health gates remain applicable. For this corrected freeze it additionally requires exact teacher-versus-freeze environment, native policy hash/equality, serialized Recall eligibility and the runtime optional-Recall startup banner. The old unlaunched freeze remains verifiable without claiming corrected coverage. Focused seed-free verifier checks passed old-freeze compatibility, corrected binding, and rejection of a missing policy field, missing freeze environment and changed teacher environment.

The verifier reads label validity but emits no evaluation outcomes. Keep evaluation k2,3 outcomes out of selection review. For each retained state, select the action using mean `finalWon` on k0,1 only; ties favor the actual captured source choice when tied, otherwise canonical semantic-key order. Save and hash the selected-action artifact before opening/reporting evaluation outcomes. Compare that frozen action with the actual source choice only on paired k2,3. A same-k best action is an oracle diagnostic, not achieved improvement.

Report **every allocated case**: completed and incomplete sources, reached and absent types, all retained states/options/futures, invalid/error/no-MAP branches and no-change states. Do not restrict reporting to disagreement or favorable cases. Every valid sibling must retain its actual finalWon target and its first completed post-decision MAP row; a terminal branch with no MAP is an explicit contract limitation, not a row to drop. Source-level `trajectoryValid` remains mandatory; any present fatal/quarantine/health counters must be zero. Root profiles must be nonempty, source-consistent, error-free and nonadaptive. Profiles combine sources and branches, so teacher/source binding supplies the per-continuation budget claim.

`CONTRACT_CANARY_PASS` requires all four sources accounted for, all retained sibling rows valid and present, complete exact identities and public-conditioning checks, and no unexpected model fallback. Report source/branch CPU, wall sums, state/type/act coverage, branch fights and cost projections. Four sources cannot qualify a policy. No training, next tranche, final confirmation opening, model replacement or production-default change follows automatically from a pass.

Knowledge impact: corrected experimental protocol and frozen custody evidence; no additional gameplay implementation or model training in this preparation.

Independent integrity review rehashed the frozen binary, models, teacher, policy and corrected runtime protocol; verified exact environment/native-policy equality and Recall/public fields; and approved the dynamic launcher and conditional verifier for this four-source K4 contract/cost canary only. No source games or outcomes were opened by that reviewer.
