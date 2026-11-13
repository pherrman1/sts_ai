# Cheap rollouts stage 2: smoke (2026-11-13, cloud container)

Binary: `linux-gcc-release` build of code f9601609 (the campaign's x86-64-v3 preset has no FMA contraction, so its
floats match). Environment [record_env.sh](record_env.sh) except `STS_AZGEN_ROLLOUT_LADDER=greedy:16000,sttt:16000`,
`STS_AZGEN_ROLLOUT_STUDENT` = the same s32 student, no per-encounter students. Seed 111980000 (§797's first seed;
`STS_STOP_AFTER_ACT=1` was set but silverazgen plays the whole run, so this is one full run). Smoke data only.

## Main line bit-identical to §797

- 541 root rows here and in §797's `natural-111980000.jsonl.gz` (budget-ladder-roots share), the same (fight,
  decision) keys; `chosen` differs on 0 of 541 and the `edges` lists (bits, visits, Q, max-backed Q, prior) on 0 of
  541. The log's tree-reuse line: reroots 453, inherited 4,432,336, cap resets 22.

## Rollout ladder

- 214 searched multi-edge prior-playout roots got both arms (224 boss / Act-4 roots, 10 single-edge or skipped);
  0 of 428 picks unmatched.
- CPU on those roots: greedy:16000 36.5 s, sttt:16000 84.4 s; §797's P1 16k ladder searches of the same roots 222.0 s
  on §797's machines, ×1.171 for this container (ratio of the played searches' `mainCpu`, 260 s): greedy 0.14×,
  sttt 0.32× P1 16k.

## Student export parity

`one_combat silverpolicymlpcheck students/s32.txt` vs `silver_az_mlp.py parity` on 297,145 captured roots (1.51 M
edges): max |Δ logit| 1.6e-5, PASS.
