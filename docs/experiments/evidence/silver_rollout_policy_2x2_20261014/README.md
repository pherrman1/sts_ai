# §479 evidence: Silver leaf-rollout variants × gen-6 tree prior at A20 (fight level)

- Pre-registration: [`PREREG.md`](PREREG.md) (frozen; pre-launch review FIX REQUIRED at `7b3db2a6`, delta PASS at
  `d41a4386`, quick delta PASS at the run commit). Reviews: `/mnt/project-files/silver-rollout-2x2/REVIEW-*.md`.
- Run commit `df88c0f4`, code `7a413622`, binary sha256 `a1405f6d…097e78` (every worker's `FROZEN.txt` agrees).
  Philipp (2026-10-15 06:44Z): 8 workers, the two 10k uniform arms dropped.
- 8 cloud workers (2026-10-15 07:10–07:29Z), each `worker.sh run W` = `run.sh OUT 8 105000000+8(W−1) "0 1 2 3" 6h`;
  all 32 shards rc=0, shard wall 140–999 s. Seeds 105000000–105000063.
- Raw: `/mnt/project-files/silver-rollout-2x2/wWW.tar` (W = 01..08), each with `wWW.DONE.txt`. sha256, checked from
  the lead container against each DONE file:

```
19031e902fdb80a9189e94ce4594b982e23f098798f4f5a84a6e99b8e54cb5a2  w01.tar
c46cf408b163e8ac3de9939be9398fa1afbf466f23fd1913a3a708b87078aede  w02.tar
71b029f486aa72cf2718c4f0153dd2f277596280419a55750718b1570e41df02  w03.tar
e54598180b4a65927e1a9e061afe412cac5917e696a1145b98ac322d6a8e1d9d  w04.tar
1d63dab0dd9559bc19cfcf82ae432b3e18de5b39e3d99ed37affb48e2387a6b0  w05.tar
81e17fa9073f855d4ddf78161c5cd4e4b82531a4f8b810fba7a54e4e680f688b  w06.tar
8c01cc025d9124163afba2b2b22a3e595c3d822c98c50a8e399365f39d13d20a  w07.tar
d9994b0f47e694c80a7ca88862e9716d6435bb18481df84f4768a26115568145  w08.tar
```

- Output: [`analysis.json`](analysis.json) from `python3 analyze_479.py analysis.json w01 … w08` over the extracted
  tars (rerun gives a byte-identical file).

## Exclusions
703 fights replayed, 689 valid in every arm (125 boss, 334 elite, 206 normal, 24 event). Excluded
(`invalid_arm_row`) by root reason: 7 `escape` (175 escape-quarantined rows; 14 escaped replicates per arm, the same
fights in every arm) and 7 `control_replay_mismatch`, all act-3 bosses
(4 Time Eater: s105000025-f28, s105000036-f24, s105000049-f27, s105000056-f27; 2 Awakened One: s105000050-f24,
s105000054-f24; 1 Donu and Deca: s105000031-f27). Replaying seeds 105000025, 031, 036, 049, 050, 054 and 056 with
main's binary (`2195b648`, §476 `mlpsweep` armset at 625, teacher regenerated for that binary) gives the same 7
control mismatches with identical control outcome and terminal HP, so they predate this change. `truncatedRows` and
`incomplete_shard_abort`: 0. The run gave 10.8 valid fights per seed against 15.75 in the 4-seed smoke, so 689
instead of the planned ~1,000.
