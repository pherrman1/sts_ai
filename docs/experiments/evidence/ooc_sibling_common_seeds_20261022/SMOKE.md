# STS_OOC_SIBLING_COMMON_SEEDS: smoke, identity and the noise of sibling differences (2026-10-22)

Why: the §577 sibling targets (64 rollout3 repeats per root child) are noisy. In round 2 the gap between the best and
second-best action has a median of 0.016, while a 64-repeat target of one public state scatters by about 0.025
between captures. Each leaf's repeats had their own streams, because the seed included the leaf ordinal
(`ooc_mcts_adapter.cpp`, `siblingLeafExtras`). With `STS_OOC_SIBLING_COMMON_SEEDS=1`, repeat r of every leaf of a
root uses the same stream (common random numbers), so differences between siblings lose part of that noise.

Binaries: `one_combat`, `linux-gcc-release` in the cloud:
- this branch at `a5cf1114`, sha256 `492d94a4…`;
- main `165b5060`, sha256 `353ca004…`.

Seed 111144997 (value-head block), `heartoutcomegen 1 SEED OUT policy` with [tools/run.sh](tools/run.sh). That is
the #806 quick smoke (§621 arm A, `STS_OOC_MCTS_SIMS=256`, `STS_OOC_MCTS_LEARNED_STOP=0`) plus sibling capture:
`_EVERY=4`, `_REPEATS=32`, `_LONG=0`, `_MAX_DEPTH=1`, `_MAX_LEAVES=64`. Round 2 used `_EVERY=8` and `_REPEATS=64`.

| run | binary | `_COMMON_SEEDS` | rc | wall s | sibling rows | outcome |
|---|---|---|---|---|---|---|
| c-main | main | (unknown to main) | 0 | 697 | 403 | Heart killed, floor 56 |
| c-off | branch | unset | 0 | 693 | 403 | same |
| c-on | branch | 1 | 0 | 697 | 403 | same |

- **Identity:**
  - c-main and c-off sibling rows are identical except the CPU-time fields (`rolloutCpuSeconds`,
    `anchorCpuSeconds`).
  - In all three runs these are byte-identical: the policy JSONL lines after the header (422), CTM rows, and the
    trace action and support logs.
  - The header differs only in its CTM file name. The trace summary differs only in `mctsWallSec`/`mctsCpuSec`.
- **Flag on:**
  - All 403 c-on rows carry `"commonSeeds": true`; no c-off row does.
  - The leaves and their order match c-off, so play is unchanged.
  - Per-leaf means are not shifted: on − off is +0.0033 (SE 0.0021) over 403 leaves. The mean SD of a leaf's 32
    repeats is 0.129 off and 0.131 on.
- **Noise of sibling differences:**
  - Data: 18 captured roots, 3,287 pairs of root children with different actions.
  - Measure: the variance over repeats of the paired difference v_i^r − v_j^r, divided by var(v_i) + var(v_j).

  | | pooled | pooled, identical pairs excluded | median pair | by quartile of var(v_i) + var(v_j), pooled / median |
  |---|---|---|---|---|
  | per-leaf seeds (off) | 1.006 | 1.006 | 1.005 | 0.999 / 0.999, 0.994 / 0.996, 0.988 / 1.006, 1.009 / 1.014 |
  | common seeds (on) | 0.363 | 0.436 | 0.869 | 0.889 / 0.941, 0.923 / 0.972, 0.249 / 0.823, 0.402 / 0.176 |

  With common seeds, 165 pairs have identical repeat vectors.

- **Reading:**
  - Pooled, common seeds are worth about 2.8× the repeats for sibling differences.
  - The gain sits in the noisy pairs (top half by variance), which carry most of the label noise. Low-variance
    pairs gain 5–10 %.
  - Probably (not measured) the streams desynchronise once sibling states consume different numbers of draws.
  - One seed, 256 simulations; a capture at the round-2 settings would measure it again.

Files: [results/](results/) has the check output (`crn_check.txt`, `crn_check.json`), the run footers, the c-on
environment and the sha256 of the three sibling files. The files themselves (2.4 MB each) are on the share at
`/mnt/project-files/value-head-research/crn-smoke/`. Reproduce:

```
SP=<dir with student_sel.bin> tools/run.sh BIN OUT c-on 111144997 SHA STS_OOC_SIBLING_COMMON_SEEDS=1
python3 tools/crn_check.py OUT c-main c-off c-on
```
