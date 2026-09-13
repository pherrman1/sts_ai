# Phase-2 stochastic persistent-state combat surrogate — corrected support audit

Date: 2026-09-13. This is the corrected continuation of the bounded Phase-2
preparation attempt recorded in the 2026-09-12 report. The same frozen corpus,
source split, producer, teacher, and Phase-2 target design were reused. No new
seeds or simulator data were collected.

Knowledge impact: the eligibility boundary is now explicit and the target
support stop is recorded; current research and the experiment ledger are
updated in the same change.

## Decision

**Classification: `TARGET_OR_SUPPORT_PROBLEM`.** The corrected eligibility
support audit passes, but the frozen TRAIN-derived joint gold target has nine
legitimate VALIDATION classes that are not observed in TRAIN. The accepted
target design requires exact classes from TRAIN and requires stopping when
VALIDATION contains an unseen value. The target schema was not broadened and
the fixed TEST split was not used to alter it. No Phase-2 or point-control fit
was run.

## Corrected eligibility boundary

The runtime/support predicate is:

```text
globals.characterClass == IRONCLAD
and globals.encounter != WRITHING_MASS
and no deck card RITUAL_DAGGER
and no active potion (SMOKE_BOMB or ENTROPIC_BREW)
and pre.smokeBombUsed == false
```

The learned input remains `combat_predictor_input_v1`. `pre.smokeBombUsed` is
an adapter/support-gate field only; it is not a learned feature and is not
encoded in the model input. This boundary explains the Entropic Brew path
without adding a `combat_predictor_input_v2` schema.

## Frozen inputs and protocol

- Corrected implementation commit before this evidence-only documentation:
  `da6dad3` (`Fix Phase-2 support and structured metrics`).
- Baseline/main SHA before the implementation:
  `58250bdb2e93c2c69b6556f408eb54ef5230639c`.
- Corpus: 510,030 rows from 24,999 completed requested seeds, one quarantined
  source (`4102275`, `process_exit_134`), source range `4100016..4125015`.
- Corpus SHA256:
  `74c08aa0a3c30342d86cd45355fe17ffa9046963ad7c8cf71b1938f9cdc1cfde`.
- Frozen source-group split SHA256:
  `e9043bcceb9d95027711e6ff33afbfe1cae3cf9528f820c0ff68bddbb419db32`.
- Canonical domains remain 372 cards, 181 relics, and 48 potions. The
  `combatRng[6]` streams remain absent from model inputs and outputs.

Preparation reused:

```text
python3 tools/combat_transition_surrogate.py prepare \
  --corpus-manifest /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl.manifest.json \
  --output-dir /tmp/sts-phase2-surrogate
```

The command completed with `status: PASS`, wrote 485,166 supported rows, and
reported 24,864 fallbacks. The prepared manifest records the frozen corpus
SHA256, support-audit hash, target-spec hash, and the adapter-only
`pre.smokeBombUsed` declaration.

## Support coverage

| Slice | Total | Supported | Fallback | Support rate |
| --- | ---: | ---: | ---: | ---: |
| Overall | 510,030 | 485,166 | 24,864 | 95.1250% |
| Act 1 | 238,946 | 235,667 | 3,279 | 98.6277% |
| Act 2 | 171,452 | 161,917 | 9,535 | 94.4387% |
| Act 3 | 99,632 | 87,582 | 12,050 | 87.9055% |
| Deaths | 18,133 | 16,620 | 1,513 | 91.6561% |

| Room | Total | Supported | Fallback | Support rate |
| --- | ---: | ---: | ---: | ---: |
| EVENT (2) | 7,826 | 7,423 | 403 | 94.8505% |
| ELITE (3) | 118,335 | 112,975 | 5,360 | 95.4705% |
| MONSTER (4) | 329,935 | 313,654 | 16,281 | 95.0654% |
| BOSS (6) | 53,934 | 51,114 | 2,820 | 94.7714% |

Fallback reason counts overlap: `ENTROPIC_BREW` 3,208,
`pre.smokeBombUsed` 26, `RITUAL_DAGGER` 13,926, `SMOKE_BOMB` 3,765, and
`WRITHING_MASS` 4,477. No non-Ironclad rows occurred in this Ironclad corpus.

## Omitted-mutation and copy-through proof

| Omitted mutation | Full corpus rows | Supported rows |
| --- | ---: | ---: |
| Deck structure | 1,151 | 0 |
| Card misc | 109 | 0 |
| `smokeBombUsed: false -> true` | 3,001 | 0 |

The supported-row mutation set is `{}` and the copy-through audit is exact:

```text
supportedRowsWithMutation = {}
supportedWinningRowsWithViolation = {}
smokeBombUsedDirections = {}
allCovered = true
allExact = true
```

The full corpus still contains 78 transitions where a resulting Smoke Bomb is
not visible in the predictor pre-state; all 78 contain visible `ENTROPIC_BREW`
and all 78 are now excluded. The bounded source mechanism is
`BattleContext::drinkPotion(Potion::ENTROPIC_BREW)` drawing a random potion and
calling `obtainPotion`. This is the covered mechanism that motivated the
eligibility correction, not an unresolved supported-row mutation.

## Target-support stop

TRAIN-supported wins produce 11 max-HP delta classes, 193 joint
`(deltaGold, post.stolenGold)` classes, and the same bounded mutable-relic
support as the original target design. Max-HP and relic target support have
no unseen VALIDATION or TEST values. The TRAIN-derived gold class set does:

- VALIDATION unseen classes: `(-83,83)`, `(-74,44)`, `(-73,73)`, `(-66,0)`,
  `(-56,15)`, `(-55,55)`, `(-41,15)`, `(-36,21)`, `(-33,18)`;
- TEST unseen classes: `(-74,74)`, `(-69,39)`, `(-36,21)`, `(-33,18)`.

The attempted fit stopped before training while validating these frozen target
labels with:

```text
python3 tools/combat_transition_surrogate.py fit \
  --prepared-dir /tmp/sts-phase2-surrogate \
  --output-dir /tmp/sts-phase2-fit-corrected-20260913 \
  --device cpu --threads 8 --nn-batch 2048 --nn-epochs 12 --nn-patience 3
```

No weights were updated and no TEST metric was produced. Adding an `OTHER`
class, deriving classes from TEST, or silently dropping these rows would change
the accepted target design, so none was done.

## Requested regressions and remaining evidence

The focused Python and CTest regressions pass. They cover:

- round-half-up HP sampling with post max HP 80 and sampled bin 50 producing
  exactly 40 HP;
- structured row-wise exact matching, where one differing potion slot makes a
  five-slot vector incorrect and one correct `(HP,maxHP)` component does not
  count as an exact pair;
- all six eligibility exclusions and fail-closed adapter state handling.

Because the target-support gate stopped the fit, Phase-2/point-control
validation and TEST metrics, sparse-head changed-slice metrics, sampled-state
validity, model sizes, and latency are **not run**. Runtime inference, Silver
replacement, OOC rollouts, RNG prediction/continuation, and new data
collection remain out of scope. A later runtime adapter still requires the
separate stochastic `combatRng[6]` continuation contract.
