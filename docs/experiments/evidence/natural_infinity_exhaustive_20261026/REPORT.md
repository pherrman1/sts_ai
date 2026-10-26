# Natural trajectory exhaustive infinity study

**TARGET_COMBAT_INCONCLUSIVE**

Baseline: `8cce22b4d5d54733330e323b3065ca687fbcbfc5`. Historical #844 is read-only at `1322e0d97721d9ffe9e2e41dbc69d8a5acc07a01`; #863 is unchanged. This is one deterministic counterfactual trajectory, not a prevalence or gameplay-quality study.

|Combat|Act/floor|Entry HP|Permanent cards|Cycle burden|Min active|Ordinary roots|Vulnerable|Dropkick in hand|Bash in hand|Pommel in hand|Candidate / certified roots|Cap / unsupported worlds|
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---:|---|---|
|11 SHELL_PARASITE|2/18|64|14|8|9|21|6|12|6|5|0 / 0|0 / 0|
|12 CHOSEN|2/22|66|21|12|19|18|7|7|1|5|0 / 0|0 / 0|
|13 SLAVERS|2/24|72|22|13|22|27|11|5|1|7|0 / 0|4 / 0|

Stage A: all 21 ordinary Shell Parasite roots were frozen before oracle execution; 84 supported worlds, 1,954 nodes, maximum depth 6, no candidates, certifications or caps. Its clean-NONE gate alone authorized Stage B.

Unchanged oracle/adapter executable SHA256: `28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9`. K4 / depth24 / nodes2000 / candidates16 / periods128 / actions1024 / total replay4096. All commands, sampled world seeds/orders, nodes, depths, cap flags, raw sidecars and custody receipts are retained. A NONE row is never a training negative.

Pinned #844 adapter source (`apps/combat_infinity_oracle.cpp`) SHA256: `f10c7dc5f4d7f4d53ae6129c291ff915db5fa338a94184522b43a1514d27b700`. The public adapter is retained from that historical branch; it is not silently substituted by the baseline main executable.

Full matrices: [Shell Parasite](MATRIX.md), [Chosen](combat12/MATRIX.md), [third combat](combat13/MATRIX.md). RESULT.json in each folder includes hand/draw identities and physical IDs, Dropkick/Bash/Pommel locations, fractions, reach depth and witnesses. Freeze files retain every root before annotation.

Inventory changes between combat entries:

```json
[
  {
    "added_cards": {
      "Clothesline+": 1,
      "Feel No Pain+": 1,
      "Infernal Blade": 1,
      "Panic Button": 1,
      "Shrug It Off": 1,
      "Spot Weakness": 2
    },
    "added_relics": [
      "ODDLY_SMOOTH_STONE",
      "ORRERY"
    ],
    "from_fight": 11,
    "removed_cards": {},
    "removed_relics": [],
    "to_fight": 12,
    "upgrades": []
  },
  {
    "added_cards": {
      "Pommel Strike": 1
    },
    "added_relics": [],
    "from_fight": 12,
    "removed_cards": {},
    "removed_relics": [],
    "to_fight": 13,
    "upgrades": [
      {
        "after": "Berserk+",
        "before": "Berserk",
        "count": 1
      }
    ]
  }
]
```

Exact #844 source artifact identities (SHA256):

|Artifact|Compressed|Decompressed|
|---|---|---|
|public.jsonl|`240e83ceb23b48cdc83360c8bec1135910fa900d71366356765dac506018a8d4`|`5728283e755b872eec5b801759dee309e22c13a786a6e2c951b0f6481e1af4cf`|
|states.jsonl|`9996e32cfc4698f091759d953a3c890daadf17316413148cc8fafb049bfdb469`|`4bc3909f82fa84c73adbc3e21c904badc5b5f2c836c01c0245753468dc67130f`|
|trace.jsonl|`b97cf46e2ed4421658052e324dc9ce3d9a98a7abb7cfdbd362a24f4e9af73344`|`6f0ee0c1389f42c0ade34d6fc701c286b7b72da298060b4573b5952f6e3eed47`|

The exact decision-critical ambiguity is retained below. No candidate was observed, but a capped search cannot establish clean absence. Do not assign COMPRESSION_WITHOUT_INFINITY_SIGNAL, use these rows as training negatives, or increase bounds automatically.

```json
[
  {
    "active_pool": 26,
    "cap_worlds": 4,
    "decision": 11,
    "enemy_hp": [
      41,
      60
    ],
    "enemy_vulnerable": [
      1,
      0
    ],
    "fight": 13,
    "hand": [
      {
        "name": "BARRICADE",
        "physical_id": 8,
        "upgraded": false
      },
      {
        "name": "POMMEL_STRIKE",
        "physical_id": 21,
        "upgraded": false
      },
      {
        "name": "FIRE_BREATHING",
        "physical_id": 2,
        "upgraded": false
      },
      {
        "name": "POMMEL_STRIKE",
        "physical_id": 3,
        "upgraded": false
      },
      {
        "name": "SHRUG_IT_OFF",
        "physical_id": 20,
        "upgraded": false
      }
    ],
    "ingredient_locations": {
      "BASH": {
        "discardPile": [
          {
            "name": "BASH",
            "physical_id": 1,
            "upgraded": false
          }
        ],
        "drawPile": [],
        "exhaustPile": [],
        "hand": [],
        "limbo": []
      },
      "DROPKICK": {
        "discardPile": [
          {
            "name": "DROPKICK",
            "physical_id": 7,
            "upgraded": false
          }
        ],
        "drawPile": [
          {
            "name": "DROPKICK",
            "physical_id": 10,
            "upgraded": false
          }
        ],
        "exhaustPile": [],
        "hand": [],
        "limbo": []
      },
      "POMMEL_STRIKE": {
        "discardPile": [],
        "drawPile": [],
        "exhaustPile": [],
        "hand": [
          {
            "name": "POMMEL_STRIKE",
            "physical_id": 21,
            "upgraded": false
          },
          {
            "name": "POMMEL_STRIKE",
            "physical_id": 3,
            "upgraded": false
          }
        ],
        "limbo": []
      }
    },
    "max_depth": [
      5,
      6,
      5,
      6
    ],
    "nodes": [
      2000,
      2000,
      2000,
      2000
    ],
    "turn": 2,
    "unsupported_worlds": 0
  }
]
```

Slavers decision 11 has enemy Vulnerable, both Pommels and Shrug It Off in hand, one Dropkick in the draw bag and the other in discard. Seven Wounds are already in discard. Its 2,000-node cap in all four worlds can hide a relevant continuation; the shallow NONE explanation from the four original minimum-active roots does not discharge this ambiguity. Ingredient/reachability model work remains unauthorized by this result.

The retained gameplay binary is `2b317b0533d0c834da268ddff03d087b271b9a950b26dde303437df7cc10cba9`, from historical d8fd2a105a8d2a481b7639e26c683f75e382e3d4 plus the previously qualified five-skip patch. It is byte-identical to #844's research runtime, with eight hash-matched historical models, including Student-C `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`. No production/runtime rebuild was needed. Stage-B launch/receipt files bind source/model custody and complete replay-prefix equality.

The binary accepts one capture floor per launch. A bounded discovery replay identifies the next entry; targeted replays recapture that unchanged trajectory. These passes are not independent experimental trajectories. The monitor terminates the exact process group at the observation boundary; a SIGTERM return is intentional. No fourth combat is part of the study.

Stop-monitor deviation: before the polling wrapper terminated capture13, the simulator emitted two ordinary floor-24 reward-screen actions after the Slavers battle record (five trace records including boundaries). No fourth combat was entered or completed. Those reward actions are retained in raw evidence but do not affect combat-entry inventories, root selection, annotation, or interpretation.

Reporting metadata: STAGE_A_GATE_AT_FIRST_LAUNCH.json retains the original hash-bound gate report. The later RESULT.json adds zero-valued cap-root and unsupported-root totals; labels/raw evidence did not change.

Knowledge impact: experiment ledger and maintained current-research status. No training, beam, planner, model, threshold, oracle-bound or production-default change. Full-run outcomes and current-policy prevalence are unobserved.
