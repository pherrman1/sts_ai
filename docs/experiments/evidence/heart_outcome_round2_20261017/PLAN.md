# Heart-outcome collection round 2 (§503): plan

Status: PREPARED_NOT_DISPATCHED. Needs Philipp's go with the worker count in his words, an independent
pre-launch review (source, canary, export check) and one activation. Only the coordinator starts worker threads.

## Decision (2026-10-17 08:23Z)

Philipp: "Do A+S on 32 workers". Frozen: 32 workers x 64 sources (34 TRAIN / 10 VALIDATION / 20 CONFIRM each) =
2,048 sources (1,088 TRAIN, 320 VALIDATION, 640 CONFIRM), seeds 111101000..111103047, siblings every 8th root.
Plan `dc730f4575c2cfa2cdfdc107eabc6c751497eda9a99c27034a6aebfb72b9ff47`; producer, binary and bundle unchanged
(`5810761d…`). Cloud canary.json on this plan `95930a8cf88d8834daf93439ea2b6c08833d4bb5340fe31bb8ad05702f590f59` (PASS; on/second traces byte-identical to the reviewed 45-worker canary). The 45-worker A+S plan below was reviewed but superseded; its canary does not qualify this plan.

## Goal

More independent completed-run Heart outcomes under the unchanged §497 teacher, for development of the value
head (workstreams 1 and 2), plus a fresh sealed CONFIRM cohort that stays unopened until candidate selection is
frozen. The §497 TEST is consumed and is not reused.

## Teacher (unchanged from §497)

Arm C native `eff2f74f…` tree prior and rollout policy, calibrated A20 CTM, rollout3/native X2-B leaf, 512 OOC
sims with early stop, keys on, full run, exact 10k native Silver real combat, `scientific_environment()` unchanged.
Evidence: the new producer rerunning §497 cloud canary seed 110179996 (capture off) reproduces §497's
`off.trace.jsonl` and `off.mcts.csv.actions.jsonl` byte for byte and the same outcome footer.

## Capture schema (agreed with workstream 2 via the coordinator)

Per source, as §497: `states.jsonl` (header, real-run driver boundaries with public `heart1-public-record-v2`
records, outcome footer = the Heart label), traces, receipts. New, captured sources only:

- `roots.jsonl` (`STS_OOC_MCTS_ROOT_TRACE`, schema `ooc-root-trace-v1`): one row per live OOC MCTS root, aligned
  1:1 with `mcts.csv.actions.jsonl` (validated): seed, decisionIndex, searchSeed, act/floor/screen/selector,
  every root candidate `{id, ooc:v1 key, prior, visits, visitShare, q}`, requested/completed sims, singleton,
  selected key, executed, public record, and a replay-only native snapshot (`screen-leaf-full-state-v1`).
  Snapshots fail on roots whose state carries an untagged continuation callback (canaries: 17-27% coverage);
  failures are counted per screen in each receipt and never censor the source.
- Exact replay key for every root: (producer binary sha, seed, decisionIndex). The run is deterministic, so the
  frozen binary rerun to decision k rebuilds the root state in-process.
- Optional (plan option `--sibling-every 8`): §494 sibling rollout labels, 64 Arm C rollout3 repeats per root
  child, depth 1, at most 64 leaves, on every 8th searched root, in `sib.jsonl` keyed by (seed, decision).

Outcome labels come only from the footer. CTM predictions, rollout surrogates and X2-B are never labels.

## Canary results (this container, Intel Xeon, single-thread producers)

| Unit | Seed | Seconds | Roots | Snapshots |
| --- | --- | ---: | ---: | ---: |
| local off / on | 111100000 | 455 / 447 | 92 | 25 |
| local second | 111100001 | 458 | 82 | 17 |
| cloud off / on | 111100002 | 569 / 546 | 111 | 22 |
| cloud second | 111100003 | 242 | 56 | 15 |
| sibling every 8 | 111100001 | 824 | 82 | 17 |
| cloud, A+S plan: off / on / second | 111100002/3 | 562 / 890 / 328 | 111 / 56 | 22 / 15 |

OFF/ON trace, action and outcome parity PASS in both canaries; the sibling run's trace and actions are byte
identical to the no-sibling run of the same seed. Root trace overhead is within noise. Sibling subsample costs
+80% CPU per source (824 vs 458 s). Compressed output: about 55 KB per source, plus about 190 KB with siblings.

## Size options (45 workers x 4 producers, 6 h deadline, 3600 s source cap)

§497 cost: mean 472 s, p90 763 s, max 1297 s per source (1440 TRAIN/VALIDATION receipts).

| Option | Sources per worker (TRAIN/VAL/CONFIRM) | Total | Sibling | Est. worker time | CONFIRM Heart wins (12%) |
| --- | --- | ---: | --- | ---: | ---: |
| A | 34/10/20 = 64 | 2,880 | off | ~2.1 h | ~108 |
| A+S | 34/10/20 = 64 | 2,880 | every 8 | ~3.8 h | ~108 |
| B | 51/15/30 = 96 | 4,320 | off | ~3.2 h | ~162 |

CONFIRM AUC standard error at AUC 0.75 (Hanley-McNeil): about 0.028 for 900 sources, 0.023 for 1350.
Development TRAIN after A: 1080 + 1530 = 2610 runs (≈310 wins); workstream 1's learning curve gains clearly to
540 and is unresolved beyond, so doubling TRAIN tests that directly. With siblings the slowest §497 source would
take ~2300 s, inside the 3600 s cap; B with siblings would not fit the deadline. Recommendation: A+S.

## Frozen identities (recommended A+S)

Producer source `d8fd2a105a8d2a481b7639e26c683f75e382e3d4`; one_combat `0e17e0f22259afe21f35ba89a0413f2af7663cfae1312311f1ea8c71b00c2d52`
(GCC 13.3 cloud build, reproduced by a fresh-clone `cloud_worker.sh setup`); studentc.bin `eff2f74f…`;
Python 3.13.16 / NumPy 2.5.3. A+S plan `c88256cea6734fe0a0e891c88bf9c40f67fb5d78ce5e45d0ff7ac9f707c06cfc`,
bundle `5810761da0ac09d5ba8a476655e5cd225906a0a86a72f100a65d090c3d40b59c`, cloud canary.json
`95b36d36edf273117cff706e2ee5cd5d27b0d33d4d493dfa9e7d490597126e2a` (PASS). Option A (no siblings) plan
`babf5c7a2ef69c0923458921b466ac8d6dc37b7a68fad9a56361c5736865b878`, cloud canary.json `f51973fa…` (PASS).
Option B needs a new prepare and canary.

## Seeds

Reserved 111100000-111109999 (coordinator informed). Canaries 111100000-111100003 (excluded from data).
Cohort from 111101000 in contiguous split blocks, round-robin within each split (A: through 111103879).
111000000-111000002 were consumed by aborted earlier canary attempts.

## Execution (as §497)

Workers run `cloud_worker.sh` from RUN_COMMIT in their own clone: setup builds and hash-checks the producer;
run re-prepares and hash-checks plan and bundle, checks the activation, runs `heart_outcome_round2.py worker`
unchanged, and writes only `deliveries/wWW` on the share (CONFIRM as `SEALED-confirm.tar.gz`). No retries;
a lost worker may be rerun as two halves (`run W ACT H`) only on Philipp's word. Lead verifies receipts and
archive hashes, builds a delivery index, never opens CONFIRM. Import/seal audit follows as its own reviewed step.
