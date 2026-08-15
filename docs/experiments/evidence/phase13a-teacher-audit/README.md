# Phase 13A counterfactual teacher-strength audit — INVALID RUN PRESERVED

This is a diagnostic-only audit. M0 is loaded into a separate native network
instance and is never used to execute the V4 source trajectory.

**Status of the original run:** INVALID — ownership-selection bug. The original
collector treated every REWARDS state with `cardRewardCount > 0` as V4-owned,
even while live V4 was still auto-collecting gold, relic, potion, or enabled
keys. Its candidate pool, manifest, raw outcomes, and conclusion must not be
used scientifically. They are preserved below for auditability.

## Provenance

- Starting baseline: `main` at `7d9b38eadaaa6c81436f9c64ab9568d9a0a4c50e`
- Branch: `exp/phase13a-counterfactual-teacher-audit`
- V4: `selfplay/models/ooc_strategic_tok_final.native`
- V4 SHA256: `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c`
- Strict M0 durable copy: `docs/experiments/evidence/phase13a-teacher-audit/models/strict_m0_best_ce.native`
- Strict M0 SHA256: `97564d1be6b4f2356ef5807645a3b45126726bf8ae07cc2b7e273a860106e62a`
- Strict M0 checkpoint provenance: `/tmp/strict_m0_best_ce.pt`, SHA256
  `e600d1bfebbebb5c6b4059eb7f29dcb1c08b9a318178c43c6d77d5744f369b2e`
- Combat VNet: `models/v_combat_7k_tuned.txt`, SHA256
  `ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c`

The durable M0 native is a byte-preserved copy of the verified `/tmp` native;
it was not retrained or re-exported.

## Frozen configuration

```text
STS_FAIR=1
STS_SEARCHER3=1
STS_S3_PARTICLES=64
STS_S3_BELIEF=0
STS_S3_CHAIN=0
STS_LIVE_VALID=1
STS_VNET=models/v_combat_7k_tuned.txt
STS_VNET_ALPHA=0.3
STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native
STS_PHASE13A_M0_NN=docs/experiments/evidence/phase13a-teacher-audit/models/strict_m0_best_ce.native
STS_OOC_STRATEGIC_MARGIN=1.0
STS_OOC_STRATEGIC_REST=1
STS_OOC_STRATEGIC_EVENT=1
STS_OOC_STRATEGIC_SHOP=1
STS_OOC_STRATEGIC_TREASURE=1
STS_OOC_STRATEGIC_BOSS_RELIC=1
STS_OOC_STRATEGIC_MAP=0
STS_COLLECT_KEYS=0
STS_SIM_ADAPT=0
OMP_NUM_THREADS=1
```

Both S and R use the existing `finishOocCounterfactual` OOC continuation
chain. S is unchanged Phase-12 Tier-B: K=3, bootstrap enabled, 150/100/50.
R changes only the requested horizon/combat dimensions: `sims=1000`,
`maxFights=-1`, `bootstrap=false`, `stopAfterAct=0`, and no fixed fight
schedule. With keys disabled, R is required to terminate without bootstrap.

## Selection

Pass 1 used fresh source seeds `920000..920007` and produced 119 eligible
states. Selection used `random.Random(1301)`, sampled 16 without replacement,
then sorted by `(sourceSeed, decisionId)`. The manifest was written and hashed
before S/R evaluation:

```text
selection_manifest.csv
SHA256 88795a8b46db5296f453bd2dcd17ebb6453dbf352cbba4a65949d20098857bc4
```

## Analysis

`tools/analyze_phase13a_teacher_audit.py` computes per-decision utility and
win deltas, preference counts, paired-future uncertainty, and sign agreement.
It must be run twice and produce byte-identical summaries.

## Final evidence

The evidence in this section belongs to the invalid original run and is
preserved without overwrite. It is not a scientific result.

- Candidate pool: `run/candidates_920000_8.csv`, 119 eligible rows.
- Raw evidence: `raw_evaluations.csv`, 256 rows, SHA256
  `81e686d4eab32500df2397345b44f4c6d19a377dac97b2edf4a5c528b0e2e7c0`.
- Decision table: `decision_summary.csv`, SHA256
  `ab98759b31e9bb5e09e257e5a2acf024590086b92cee760dfee1df634067536a`.
- Selection manifest SHA256:
  `88795a8b46db5296f453bd2dcd17ebb6453dbf352cbba4a65949d20098857bc4`.

The scientific command was the following, run as four disjoint four-decision
parts in parallel to avoid the local wall-clock limit; each part used the same
exact environment below and the evaluator defaults (`R sims=1000`, `H=4`):

```bash
tools/seed_guard.sh ./build/one_combat phase13a_eval \
  docs/experiments/evidence/phase13a-teacher-audit/scientific_partN.csv \
  docs/experiments/evidence/phase13a-teacher-audit/scientific_partN.raw.csv 0
```

The four raw parts were concatenated in manifest order. The initial single
process attempt timed out after 15 minutes and is not used as evidence.

## Result and limitation

The complete table contains 15 fully valid decisions and one unstable decision:
two R futures for `(sourceSeed=920000, decisionId=12)` failed the existing
Searcher3 simulator-health contract (`TRANSIENT` / `SECRET_WEAPON`,
`ACTION_SELECTION_FAILED` and `UNDECIDED_BATTLE_EXIT`). Those rows have
`valid=0`, `bootstrap=-1`, and `healthDelta=2`; they are retained in raw data
and excluded from aggregate arithmetic. No replacement futures were run.

For the 15 valid decisions: mean `refDelta=-2.05`, mean
`refWinDelta=-0.083333`; S preferences were M0/V4/tie = 8/2/5 and R
preferences were 3/5/7. Strict sign agreement was S-vs-R 3/15 and
Because ownership was wrong, the original result is **INVALID**, not H4
inconclusive. The reference-health failure is secondary and must not be
repaired before rerunning corrected ownership.

## Corrected rerun

The corrected collector mirrors live V4 gate precedence. REWARDS is owned only
when gold, relic, potion, and enabled-key actions are exhausted and card rewards
remain. REST, UPGRADE_SELECT, EVENT, SHOP, TREASURE, and BOSS_RELIC require the
corresponding enabled strategic gate and a non-empty legal action set. MAP,
REMOVE, and regret-gate ownership are excluded. The collector records
`gateOwned`, `liveV4Idx`, and `liveV4Margin`; the smoke asserts these match the
ordinary live margin computation before any outcomes are evaluated.

The corrected scientific rerun used fresh source seeds `940000..940007` with
the exact source/replay budget `sims=1000`. It produced 70 eligible states and
froze 16 before evaluator outcomes. The corrected manifest SHA256 is
`a84de37a038ead6750115bc8cb95d697710e8b60cd7788070b56297d1b1752db`.

Corrected raw evidence contains 256 valid rows, SHA256
`1f7778f3ce7200a08eec34f05885a0f8d08b373a36e798d8477657014dec1fa3`.
The corrected decision summary SHA256 is
`0f68996e239a960fdc9de3365d7951463119b401758e9aa88e2733d942543690`.

Corrected results:

```text
mean refDelta      = -13.843750
mean refWinDelta   = -0.250000
S preference       M0=9 V4=5 tie=2
R preference       M0=6 V4=9 tie=1
strict agreement   short/reference=6/16 model/reference=6/16
three-way agreement short/reference=7/16 model/reference=6/16
invalid rows=0
```

All 128 R rows have `bootstrap=0`; all 256 rows are valid, with no replay or
simulator-health failures. Under the preregistered rules, the corrected result
is **H4 inconclusive**: R favors V4 on 9/16, below the 10/16 threshold, and
neither the short teacher nor R favors M0 on at least 10/16. This valid result
does not support M0 promotion or distinguish the teacher, model-fitting, and
objective hypotheses.