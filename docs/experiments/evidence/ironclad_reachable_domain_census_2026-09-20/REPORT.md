# Ironclad reachable-domain census

Audit/measurement only. No simulator behavior, model input, model artifact, or search behavior is changed.

Audited source head: `7f239baa8bbea3c5db815176c0f91887d70fb841` (requested baseline was `15f3eaed1f1bc3866e2686e7d6043f9e11c799cd`).

## Results

| Domain | Canonical | Reachable | Provably unreachable | Unknown |
| --- | ---: | ---: | ---: | ---: |
| cards | 372 | 134 | 214 | 24 |
| relics | 181 | 147 | 1 | 33 |
| potions | 48 | 34 | 10 | 4 |
| encounters | 128 | 63 | 1 | 64 |
| monsters | 256 | 65 | 1 | 190 |
| statuses | 87 | 22 | 1 | 64 |

The exhaustive ID/name/classification/evidence record is in `census.json`. `UNKNOWN` is intentional for canonical capacity slots without a current enum or a complete supported acquisition proof.

## Important findings

- The current `CardId` enum has 371 values, while `kNumCardIds` is 372. The extra canonical slot is `UNKNOWN`; the combat PVNet consumes the first 371 slots (0..370).
- `kNumRelics` is 181 (IDs 0..180), and `PRISMATIC_SHARD` is enum ID 161 inside that canonical relic model domain. It is retained in the exhaustive census but explicitly excluded from the supported Ironclad closure.
- `kNumPotions` is 48, while the current Potion enum has 44 values. IDs 44..47 are `UNKNOWN`, not silently dead.
- Cards in the non-Ironclad class-pool rows are marked provably unreachable under the Ironclad/no-Prismatic-Shard contract. The source also has two class-pool/cardColors metadata conflicts (`BRUTALITY`, `COMBUST`); the census preserves those conflicts and uses explicit class-pool membership for the reachability decision.
- `PRISMATIC_SHARD` is present at relic ID 161 and in the Ironclad shop pool, but is explicitly excluded from the supported closure and therefore marked provably unreachable. It is never used as an edge to any other entity.

## Model capacity

### Canonical combat state

```json
{
  "cardZoneCount": 4,
  "cardZoneWidth": 371,
  "deadCardColumnPercent": 57.681940700808624,
  "deadCardColumns": 856,
  "deadColumnsKnown": 856,
  "deadModelVisiblePowerColumns": 0,
  "deadRelicColumnPercent": 0.0,
  "deadRelicColumns": 0,
  "featureCount": 1766,
  "knownDeadColumnPercentOfFeatureCount": 48.47112117780294,
  "modelVisiblePowerUnknown": 2
}
```

### Combat PVNet

```json
{
  "cardAggregationMacReductionFourZones": 109568,
  "cardAggregationMacReductionPerZone": 27392,
  "cardDeadEmbeddingPercent": 57.681940700808624,
  "cardDeadParameters": 27392,
  "cardDeadRows": 214,
  "cardEmbeddingParameters": 47488,
  "cardEmbeddingShape": [
    371,
    128
  ],
  "deadParameterPercentOfTotalKnown": 6.1999548069114105,
  "deadParametersKnown": 27712,
  "totalParameters": 446971
}
```

### Whole-combat transition models

```json
{
  "attentionDeadParameterPercent": 12.611886703217783,
  "attentionIdentityDeadParameters": 14400,
  "attentionTotalParameters": 114178,
  "canonicalDomains": {
    "cards": 372,
    "potions": 48,
    "relics": 181
  },
  "computeNote": "Token models do not pay transformer attention cost for absent entity IDs; these are storage/parameter capacities, not equal training-time savings.",
  "deadEmbeddingRows": {
    "cards": 214,
    "potions": 10,
    "relics": 1
  },
  "deepsetsDeadParameterPercent": 11.252829071218564,
  "deepsetsIdentityDeadParameters": 10640,
  "deepsetsTotalParameters": 94554,
  "parameterTotalsEvidence": {
    "deepsetsAndAttention": "tools/combat_transition_model_experiment.py::DeepSetsModel/AttentionModel default constructors",
    "phase2": "tools/combat_transition_surrogate.py::Phase2Net default-shape constructor"
  },
  "phase2AdditionalDeadParameters": {
    "potionOutputRowsIncludingBias": 730,
    "relicTokenEmbedding": 16
  },
  "phase2DeadParameterPercent": 9.68065569310298,
  "phase2DeadParameters": 11386,
  "phase2TotalParameters": 117616
}
```

### OOC V4

```json
{
  "computeNote": "V4 entity embeddings are capacity/storage rows; absent IDs do not create additional token attention work.",
  "deadEmbeddingParameters": {
    "cards": 6848,
    "potions": 80,
    "relics": 16
  },
  "deadEmbeddingParametersTotal": 6944,
  "deadEmbeddingPercent": 45.68421052631579,
  "deadParameterPercentOfTotal": 3.4773899544293654,
  "embeddingParametersTotal": 15200,
  "embeddingShapes": {
    "card": [
      372,
      32
    ],
    "potion": [
      48,
      8
    ],
    "relic": [
      181,
      16
    ]
  },
  "parameterTotalsEvidence": "apps/ooc_strategic_tok_net.h::OocStrategicTokNet float weight arrays; globMean/globInv normalization buffers excluded",
  "totalModelParameters": 199690
}
```

## Reproduction and checks

- Census command: `python3 tools/ironclad_reachable_domain_census.py`
- Focused checks: `python3 -m unittest tools.test_ironclad_reachable_domain_census -v` (5 tests passed).
- JSON syntax check: `python3 -m json.tool docs/experiments/evidence/ironclad_reachable_domain_census_2026-09-20/census.json` (passed).
- No gameplay seeds, corpus regeneration, retraining, binary rebuild, or expensive run was performed.

## Verification boundary

The tool is deterministic and source-derived. It does not regenerate or inspect large gameplay corpora; empirical observed-set comparisons are therefore not claimed. The recommended follow-up is the smallest compaction that removes only the `PROVABLY_UNREACHABLE` rows after independent review, preserving all `UNKNOWN` rows and the existing enum/index contracts.

Knowledge impact: none — this audit records task-scoped evidence; it does not change a maintained runtime interface or supported behavior.
