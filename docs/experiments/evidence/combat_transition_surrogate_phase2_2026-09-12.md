# Phase-2 stochastic persistent-state combat surrogate — support audit

Date: 2026-09-12. This records the bounded Phase-2 preparation attempt on the
frozen whole-combat corpus. The DeepSets tool and sampler were implemented, but
training was deliberately not started because the predictor-visible support
predicate failed its required omitted-mutation audit.

Knowledge impact: durable Phase-2 support-boundary finding and RNG limitation;
the current research page and experiment ledger are updated in the same change.

## Decision

**Classification: `TARGET_OR_SUPPORT_PROBLEM`.** The requested predicate does
not cover every omitted persistent mutation. In particular, 77 rows that the
predicate would train on have `smokeBombUsed: false -> true` even though the
predictor-visible pre-state contains no `SMOKE_BOMB`. There are 78 such rows in
the full corpus; one also contains `RITUAL_DAGGER` and is already excluded by
the predicate. All 78 contain the predictor-visible `ENTROPIC_BREW` potion.

This is not resolved by adding Entropic Brew to the predicate: the task
explicitly requires stopping rather than broadening the support rule ad hoc.
The source path is `BattleContext::drinkPotion(Potion::ENTROPIC_BREW)`, which
draws random potions and calls `obtainPotion`; the draw can produce a Smoke
Bomb that was not present in the predictor input. No Phase-2 or Phase-1
control fit, test evaluation, model export, runtime adapter, or new seed
collection was run after this gate.

## Frozen inputs and protocol

- Baseline/main SHA before the implementation: `58250bdb2e93c2c69b6556f408eb54ef5230639c`.
- Corpus: 510,030 rows from 24,999 completed requested seeds, one quarantined
  source (`4102275`, `process_exit_134`), source range `4100016..4125015`.
- Corpus SHA256:
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- Frozen source-group split SHA256:
  `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`.
  The split is reused from `combat_transition_model_experiment.py` and groups
  by `sourceSeed`; no random row split was introduced.
- Input domains are the canonical 372 cards, 181 relics, and 48 potions.
  The implementation uses the corrected PR #161 DeepSets encoder: categorical
  globals, typed card/relic/potion encoders, masked pooling, width 64, and a
  small shared trunk. No attention rerun was attempted.
- Intended fit protocol remains validation early stopping, frozen epoch count,
  TRAIN+VALIDATION refit from scratch, and one fixed TEST evaluation. The
  point control is the same DeepSets representation with survival and expected
  winning HP heads.
- `combatRng[6]` is intentionally neither copied nor modeled. A later runtime
  adapter still requires a separate RNG-continuation contract before
  multi-fight stochastic rollouts can be considered valid.

Preparation command:

```text
python3 tools/combat_transition_surrogate.py prepare \
  --corpus-manifest /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl.manifest.json \
  --output-dir /tmp/sts-phase2-surrogate
```

The command validates the manifest and complete JSONL hash before the audit.
It exits non-zero with `support predicate leaves intentionally omitted
mutation rows supported: {"smoke_bomb": 77}` and writes the machine-readable
audit to `/tmp/sts-phase2-surrogate/support_audit.json`.

## Support coverage

| Slice | Total | Supported | Fallback | Support rate |
| --- | ---: | ---: | ---: | ---: |
| Overall | 510,030 | 488,283 | 21,747 | 95.7361% |
| Act 1 | 238,946 | 237,124 | 1,822 | 99.2375% |
| Act 2 | 171,452 | 162,987 | 8,465 | 95.0628% |
| Act 3 | 99,632 | 88,172 | 11,460 | 88.4977% |
| Deaths | 18,133 | 16,699 | 1,434 | 92.0918% |

The room-class values are the repository enum values (`2=EVENT`, `3=ELITE`,
`4=MONSTER`, `6=BOSS`):

| Room | Total | Supported | Fallback | Support rate |
| --- | ---: | ---: | ---: | ---: |
| EVENT (2) | 7,826 | 7,467 | 359 | 95.4127% |
| ELITE (3) | 118,335 | 113,725 | 4,610 | 96.1043% |
| MONSTER (4) | 329,935 | 315,622 | 14,313 | 95.6619% |
| BOSS (6) | 53,934 | 51,469 | 2,465 | 95.4296% |

Fallback reason counts can overlap: `WRITHING_MASS` 4,477, `RITUAL_DAGGER`
13,926, and visible pre-state `SMOKE_BOMB` 3,765.

Per-encounter coverage (numeric canonical `MonsterEncounter` IDs) is:

| ID | Total | Supported | Fallback | Rate | ID | Total | Supported | Fallback | Rate |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 18,631 | 18,531 | 100 | 99.4633% | 30 | 12,189 | 11,581 | 608 | 95.0119% |
| 2 | 18,817 | 18,712 | 105 | 99.4420% | 31 | 6,954 | 6,593 | 361 | 94.8087% |
| 3 | 18,827 | 18,714 | 113 | 99.3998% | 32 | 7,019 | 6,655 | 364 | 94.8141% |
| 4 | 18,679 | 18,565 | 114 | 99.3897% | 33 | 6,968 | 6,616 | 352 | 94.9483% |
| 5 | 10,455 | 10,343 | 112 | 98.9287% | 34 | 13,471 | 12,703 | 768 | 94.2989% |
| 6 | 5,845 | 5,791 | 54 | 99.0761% | 35 | 13,597 | 12,794 | 803 | 94.0943% |
| 7 | 10,361 | 10,277 | 84 | 99.1893% | 36 | 13,617 | 12,788 | 829 | 93.9120% |
| 8 | 9,784 | 9,703 | 81 | 99.1721% | 37 | 6,381 | 5,854 | 527 | 91.7411% |
| 9 | 5,355 | 5,310 | 45 | 99.1597% | 38 | 6,179 | 5,666 | 513 | 91.6977% |
| 10 | 8,294 | 8,221 | 73 | 99.1198% | 39 | 6,208 | 5,713 | 495 | 92.0264% |
| 11 | 8,384 | 8,311 | 73 | 99.1293% | 40 | 12,780 | 11,803 | 977 | 92.3552% |
| 12 | 5,814 | 5,773 | 41 | 99.2948% | 41 | 8,607 | 7,942 | 665 | 92.2737% |
| 13 | 9,824 | 9,749 | 75 | 99.2366% | 42 | 8,772 | 8,065 | 707 | 91.9403% |
| 14 | 10,556 | 10,462 | 94 | 99.1095% | 43 | 4,595 | 4,292 | 303 | 93.4059% |
| 15 | 18,046 | 17,879 | 167 | 99.0746% | 44 | 4,442 | 4,094 | 348 | 92.1657% |
| 16 | 17,864 | 17,723 | 141 | 99.2107% | 45 | 4,409 | 4,105 | 304 | 93.1050% |
| 17 | 17,849 | 17,695 | 154 | 99.1372% | 46 | 4,601 | 4,246 | 355 | 92.2843% |
| 18 | 8,533 | 8,447 | 86 | 98.9921% | 47 | 4,477 | 4,164 | 313 | 93.0087% |
| 19 | 8,669 | 8,570 | 99 | 98.8580% | 48 | 4,523 | 4,219 | 304 | 93.2788% |
| 20 | 8,583 | 8,493 | 90 | 98.9514% | 49 | 4,477 | 0 | 4,477 | 0.0000% |
| 21 | 9,003 | 8,775 | 228 | 97.4675% | 50 | 8,157 | 7,527 | 630 | 92.2766% |
| 22 | 8,967 | 8,780 | 187 | 97.9146% | 51 | 8,086 | 7,492 | 594 | 92.6540% |
| 23 | 8,970 | 8,749 | 221 | 97.5362% | 52 | 7,962 | 7,438 | 524 | 93.4187% |
| 24 | 8,826 | 8,600 | 226 | 97.4394% | 53 | 3,576 | 3,324 | 252 | 92.9530% |
| 25 | 9,009 | 8,799 | 210 | 97.6690% | 54 | 3,456 | 3,219 | 237 | 93.1424% |
| 26 | 4,837 | 4,591 | 246 | 94.9142% | 55 | 3,606 | 3,353 | 253 | 92.9839% |
| 27 | 4,864 | 4,617 | 247 | 94.9219% | 58 | 156 | 155 | 1 | 99.3590% |
| 28 | 12,137 | 11,483 | 654 | 94.6115% | 61 | 3,373 | 3,239 | 134 | 96.0273% |
| 29 | 8,883 | 8,391 | 492 | 94.4613% | 62 | 877 | 870 | 7 | 99.2018% |
|  |  |  |  |  | 63 | 1,849 | 1,719 | 130 | 92.9692% |

## Mutation and copy-through audit

| Omitted mutation | Full corpus rows | Supported rows |
| --- | ---: | ---: |
| Deck structure | 1,151 | 0 |
| Card misc (`RITUAL_DAGGER`) | 109 | 0 |
| `smokeBombUsed: false -> true` | 3,001 | 77 |

The supported winning rows also expose a separate copy-through violation:
`smokeBombUsed` differs in 103 rows, with directions `false -> true: 77` and
`true -> false: 26`. Because that field is not part of the predictor-visible
pre-state, the implementation cannot add a safe support guard for the latter
case either. The declared copy-through audit therefore fails (`allExact=false`).

## Target support preview

These are TRAIN-supported-win observations only; they are not fit results.

- Winning `maxHp` delta classes: `{0, 3, 4, 5, 6, 7, 8, 9, 10, 11, 12}`.
- Joint `(deltaGold, post.stolenGold)` classes: 193, below the hard 512-class
  stop threshold.
- Bounded code audit found mutable relic IDs:
  `26, 30, 31, 32, 35, 44, 46, 52, 68, 85, 86, 87, 116`.
  TRAIN-observed delta supports were `HAPPY_FLOWER -2..2`,
  `INCENSE_BURNER -5..5`, `INK_BOTTLE -9..9`, `NUNCHAKU -9..9`,
  `PEN_NIB -9..9`, `SUNDIAL -2..2`, `NEOWS_LAMENT {-1,0}`, and
  `{0}` for `LIZARD_TAIL`, `OMAMORI`, `BLACK_BLOOD`, `BURNING_BLOOD`, and
  `MEAT_ON_THE_BONE`. `INSERTER` was source-audited but had no TRAIN token
  occurrence; its fallback target support remains `{0}`.
- The sampler derives potion count from real potion IDs (`>=2`), retains the
  canonical empty-slot ID 1, masks `INVALID` ID 0, copies unavailable slots,
  copies relic identity/order and all declared deck metadata, and rejects any
  attempted RNG state output.

## Not run / remaining blocker

No training or evaluation metrics exist for this attempt: survival Brier/AUC,
expected-HP MAE, HP NLL/CRPS/coverage, sparse-head accuracy versus
copy-through, deterministic exact match, sampled-transition validity, model
size, and batch-1 latency are all **not run**. The next authorized step would
require a reviewed change to the support/target contract that explains the
Entropic Brew-generated Smoke Bomb and the pre-existing `smokeBombUsed` state;
this report does not make that change.
