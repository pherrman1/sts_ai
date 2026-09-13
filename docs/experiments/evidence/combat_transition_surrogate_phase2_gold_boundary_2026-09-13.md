# Phase-2 stochastic persistent-state combat surrogate — gold boundary and fit

Date: 2026-09-13. This is the final continuation of the bounded Phase-2
surrogate experiment on PR #162. It uses the same frozen corpus, source split,
producer, teacher, and accepted Phase-2 target design. No new seeds or
simulator data were collected.

Knowledge impact: the maintained Phase-2 status now records the source-audited
gold support boundary and the completed DeepSets fit.

## Decision

**Classification: `PHASE2_PARTIAL`.** The support audit covers all observed
gold and `stolenGold` mutations with predictor-visible guards. On supported
rows, both fields are exact copy-through and are excluded from the learned
target. The remaining DeepSets model is not a runtime surrogate: it improves
the stochastic HP distribution and beats copy-through on relic changed slices,
but the potion full-vector result does not beat its copy-through baseline under
the explicit sparse-head rule.

Gold is a v1 support/fallback mechanic, not a learned head. The separate
`combatRng[6]` continuation contract remains a blocker for scientifically
valid multi-fight runtime rollout integration.

## Bounded source audit of combat gold mutation

The audit searched the simulator's persistent-gold writes and the combat card,
relic, potion, encounter, and random-card dispatch paths. The direct in-combat
mutators are:

| Mechanism | Source evidence | Predictor-visible guard |
| --- | --- | --- |
| Looter/Mugger theft | `src/combat/MonsterSpecific.cpp:3350-3355` subtracts `bc.player.gold` and accumulates the stolen amount in monster `miscInfo`; Looter and Mugger MUG/LUNGE calls are at `:918-983` | encounter IDs `LOOTER=7`, `EXORDIUM_THUGS=10`, `TWO_THIEVES=25`; `EXORDIUM_THUGS` can select Looter through `MonsterGroup::createStrongHumanoid` (`src/combat/MonsterGroup.cpp:179-182,492-500`) |
| Hand of Greed | `src/combat/Actions.cpp:1120-1137` calls `Player::gainGold` on the qualifying lethal branch; `Player::gainGold` adds 20/25 at `src/combat/Player.cpp:82-95` unless Ectoplasm suppresses it | deck card ID `HAND_OF_GREED=177`; capability is excluded even when Ectoplasm would suppress one outcome |
| Generated colorless Hand of Greed | `CombatColorlessCardPool` contains Hand of Greed (`include/constants/CardPools.h:189-199`); Jack of All Trades and Transmutation draw that pool (`src/combat/Actions.cpp:584-616`), Toolbox creates status/colorless discovery (`:1005-1012`), and Colorless Potion opens the same route (`src/combat/BattleContext.cpp:2337-2339`) | deck card IDs `JACK_OF_ALL_TRADES=200`, `TRANSMUTATION=343`; relic `TOOLBOX=73`; potion `COLORLESS_POTION=9` |

The remaining random-card routes were checked rather than inferred from the
corpus: Discovery/Codex/Dead Branch/Infernal Blade use the class-bound
Ironclad combat pool on supported rows, and that pool excludes Hand of Greed
(`include/constants/CardPools.h:177-185`; `src/game/Game.cpp:215-243`).
Prismatic Shard changes out-of-combat reward-card selection but does not change
`BattleContext::player.cc` (`src/game/GameContext.cpp:1427-1429,1819-1823`).
No other combat card or relic path writes persistent `player.gold` or
`stolenGold`.

Combat-reward gold is deliberately outside this raw transition boundary:
`GameContext::afterBattle` opens rewards after the raw exit hook
(`src/game/GameContext.cpp:1125-1145`; `apps/one_combat.cpp:4441-4453`), while
normal/elite/boss reward construction is in `:1928-1977`. Golden Idol reward
modification is therefore not an in-combat transition mutation and is not a
support exclusion here.

`BattleContext::exitBattle` copies `player.gold`, resets `g.info.stolenGold`,
and derives current non-escaped Looter/Mugger theft
(`src/combat/BattleContext.cpp:503-536`). Consequently supported rows require
`pre.stolenGold == 0`; both `gold` and `stolenGold` then have exact
copy-through semantics for the raw transition.

## Final support predicate

The runtime/support guard is:

```text
globals.characterClass == IRONCLAD
and globals.encounter != WRITHING_MASS
and globals.encounter not in (LOOTER, TWO_THIEVES, EXORDIUM_THUGS)
and no deck card in (RITUAL_DAGGER, HAND_OF_GREED, JACK_OF_ALL_TRADES, TRANSMUTATION)
and no relic TOOLBOX
and no active potion (SMOKE_BOMB, ENTROPIC_BREW, or COLORLESS_POTION)
and pre.smokeBombUsed == false
and pre.stolenGold == 0
```

The learned model input remains exactly `combat_predictor_input_v1`. The
pre-combat fields `pre.smokeBombUsed` and `pre.stolenGold` are adapter/support
gate fields only; they are not learned features and are not encoded in the
model input. No `combat_predictor_input_v2` was introduced.

## Frozen corpus and support coverage

- Reviewed continuation baseline: `7df806db911ae68cf4ab491db93c6591d555b050`.
- Corpus: 510,030 rows from 24,999 completed requested seeds, one quarantined
  source (`4102275`, `process_exit_134`), source range `4100016..4125015`.
- Corpus SHA256:
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- Frozen source-group split SHA256:
  `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`.
- Producer Git SHA: `f0bbd7721e7cc1453976ebb91ee11ebe6127a2bf`.
- Canonical domains remain 372 cards, 181 relics, and 48 potions.
- `combatRng[6]` is absent from model inputs and outputs.

The complete prepare audit passed on the unchanged corpus:

| Slice | Total | Supported | Fallback | Support rate |
| --- | ---: | ---: | ---: | ---: |
| Overall | 510,030 | 413,799 | 96,231 | 81.1323% |
| Act 1 | 238,946 | 197,156 | 41,790 | 82.5107% |
| Act 2 | 171,452 | 136,142 | 35,310 | 79.4053% |
| Act 3 | 99,632 | 80,501 | 19,131 | 80.7983% |
| Deaths | 18,133 | 15,384 | 2,749 | 84.8398% |

| Room | Total | Supported | Fallback | Support rate |
| --- | ---: | ---: | ---: | ---: |
| EVENT (2) | 7,826 | 6,567 | 1,259 | 83.9126% |
| ELITE (3) | 118,335 | 99,505 | 18,830 | 84.0875% |
| MONSTER (4) | 329,935 | 262,549 | 67,386 | 79.5760% |
| BOSS (6) | 53,934 | 45,178 | 8,756 | 83.7653% |

Relative to the immediately preceding corrected boundary in §230, support
decreased from 485,166/510,030 (95.1250%) to 413,799/510,030 (81.1323%):
71,367 rows, 13.9927 percentage points, or 14.7098% relative support loss.
The final fallback reason counts are:
`gold_mutating_encounter` 27,664, `gold_mutating_potion` 21,698,
`pre_stolen_gold_nonzero` 19,048, `gold_mutating_relic` 6,824,
`gold_mutating_card` 2,640, `ritual_dagger` 13,926, `smoke_bomb` 3,765,
`entropic_brew` 3,208, `writhing_mass` 4,477, and
`pre_smoke_bomb_used` 26.

## Mutation and copy-through gates

The full-corpus gold audit found 21,781 rows with `gold` changed and 37,894
with `stolenGold` changed. Both mutation mechanisms are fully covered by the
visible boundary:

```text
goldMutationSourceAudit.guardCoverage.allCovered = true
goldMutationSourceAudit.guardCoverage.supportedRowsWithMutation = {}
```

The required prior gates also remain zero on supported rows:

| Mutation | Full corpus rows | Supported rows |
| --- | ---: | ---: |
| `gold` | 21,781 | 0 |
| `stolenGold` | 37,894 | 0 |
| Deck structure | 1,151 | 0 |
| Card misc | 109 | 0 |
| `smokeBombUsed: false -> true` | 3,001 | 0 |

The complete copy-through audit reports:

```text
supportedRowsWithMutation = {}
supportedWinningRowsWithViolation = {}
smokeBombUsedDirections = {}
allCovered = true
allExact = true
```

The 78 corpus rows where Entropic Brew generated a Smoke Bomb not visible in
the pre-state are all excluded by the visible Entropic Brew guard; zero remain
supported. The same source audit therefore covers the previously invisible
smoke-bomb mechanism without changing the learned schema.

Gold and `stolenGold` are not target classes, are not included in the Phase-2
loss, and are not included in the modeled whole-transition exact-match metric.
They are exact copy-through fields on supported rows and native fallback
outside support.

## Fit protocol

The accepted remaining target was fit after the support audit passed:

- survival;
- max-HP delta;
- conditional stochastic 101-bin post-combat HP fraction;
- five potion slots;
- per-owned mutable relic-counter deltas.

DeepSets and the point-control DeepSets were trained with the frozen source
split, validation-only epoch selection, and from-scratch equal TRAIN+VALIDATION
refits. Phase-2 selected 9 epochs; point control selected 12 epochs. The fixed
TEST split was evaluated only after those refits. No attention/XGBoost rerun,
architecture sweep, new corpus, runtime inference, Silver replacement, or
OOC rollout was performed.

The completed refit wrote both checkpoints and passed the sampled-state gate.
The first evidence serialization attempt failed only after the refit and
sampling stages because validation prediction arrays were still present in
the JSON object. The serialization filter was corrected; the final evidence
packet was recovered from those exact saved checkpoints and the frozen
prepared arrays. No weights or TEST inputs changed during that recovery.

Validation selection scores were 0.174524 for Phase-2 at 9 epochs and 0.170810
for point control at 12 epochs. The final fixed-TEST results are:

| Model | Survival AUC | Brier | Log loss | Winning HP fraction MAE | Joint alive HP fraction MAE |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase-2 DeepSets | 0.972049 | 0.020880 | 0.070470 | 0.071845 | 0.079171 |
| Point-control DeepSets | 0.978047 | 0.018936 | 0.063656 | 0.072503 | 0.078933 |

### HP distribution

| Model | Categorical NLL | Discrete CRPS | 50% coverage / width | 80% coverage / width | 95% coverage / width |
| --- | ---: | ---: | ---: | ---: | ---: |
| Phase-2 | 2.744642 | 0.048484 | 0.6725 / 11.94 bins | 0.8821 / 22.74 bins | 0.9739 / 34.90 bins |
| Point-control degenerate | 17.536081 | 0.071822 | 0.0480 / 0 bins | 0.0480 / 0 bins | 0.0480 / 0 bins |

The Phase-2 HP distribution strictly improves discrete CRPS over the
point-control degenerate distribution.

### Sparse heads and structured exact match

All exact metrics are rowwise structured matches: a multi-dimensional field is
first reduced to one boolean per row using `np.all(actual == predicted,
axis=1)`, then averaged. Thus a single differing potion slot makes the full
vector incorrect, and one incorrect component makes the `(HP,maxHP)` pair
incorrect.

| Field | Model exact / accuracy | Copy-through exact / accuracy | Changed slice |
| --- | ---: | ---: | ---: |
| `(HP,maxHP)` exact pair | 0.323305 | 0.287357 | — |
| Potion full vector exact | 0.460983 | 0.728150 | 10,852 rows: 0.390527 vs 0.000000 |
| Relic full counter vector exact | 0.773967 | 0.764348 | 11,180 tokens: 0.097227 vs 0.000000 |

Additional component metrics are Phase-2 vs copy-through: max-HP accuracy
0.969087 vs 0.960821; HP accuracy 0.324457 vs 0.288509; potion count accuracy
0.680578 vs 0.728150; relic changed-counter MAE 2.155098 vs 3.199106; and
relic mutable-token accuracy 0.822208. The modeled whole-transition exact
match, excluding gold/stolenGold because they are support-gated copy-through,
is 0.169894 vs a 0.210151 copy-through baseline.

The sparse qualification rule requires both full-vector and changed-slice
accuracy to strictly beat copy-through for each sparse head. Relics satisfy
that rule; potions improve the changed slice but not the full-vector baseline,
so the aggregate sparse-head gate is false. Gold is not part of this pass
criterion.

## Validity, artifacts, and blockers

- Sampled-state validity: 16/16 sampled states valid, 0 invalid states.
- Phase-2 checkpoint: 493,271 bytes,
  SHA256 `ed5197b5ee7d273c6857f068755176e6a24743159ebaa1e0b5e978d6d8e1e789`.
- Point-control checkpoint: 388,562 bytes,
  SHA256 `bde376f64208f812071ed882679e3ef22f3ef56c4f3db90f16dead736b4588e5`.
- Batch-1 CPU latency on the fit device with 8 PyTorch threads: Phase-2
  0.3916 ms; point control 0.2989 ms.
- CI must pass the authoritative GitHub Actions `Linux GCC` check before the
  PR is considered ready for merge.

Runtime inference remains unimplemented. In particular, `combatRng[6]` is
still outside the surrogate, so the model cannot yet support scientifically
valid multi-fight stochastic rollout integration.

Machine-readable evidence is preserved externally at
`/tmp/sts-phase2-fit-gold-final-20260913-retry/phase2_evidence.json`; the
frozen prepared audit is at
`/tmp/sts-phase2-surrogate-gold-boundary-final-20260913/support_audit.json`.
