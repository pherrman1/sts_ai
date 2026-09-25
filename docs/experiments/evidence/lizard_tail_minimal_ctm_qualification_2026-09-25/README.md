# Active Lizard minimal CTM qualification — 2026-09-25

## Decision

**`ACTIVE_LIZARD_QUALIFICATION_INCONCLUSIVE`**; qualification subclass:
**`LIZARD_QUALIFICATION_INCONCLUSIVE_RARE_EVENT`**.

Baseline Git SHA: `03ae0297ac33fba41c64921d5b0bcc6eabe4be2a`.

The predeclared local cohort completed all 128 paired sources, but produced only
9 `LOSS_CONSUMED` outcomes from 9 sources; the frozen minimum is 20 from 10
sources. The primary three-class NLL interval also crosses zero, and the
frozen q consumption model is worse than B1 on both pooled NLL and Brier point
estimates. The r model and fresh T2 checks are encouraging, but cannot qualify
the complete correction. Stop before ancestral sampling, native integration,
parity, support promotion, or live smoke. No runtime code or production support
predicate changed.

## Frozen candidate and development provenance

`frozen_qr_artifact.json` is the only qualification candidate. It uses the
accepted three-class factorization, with `q = P(Tail consumed)` and
`r = P(win | Tail consumed)`, L2 logistic regression (`L2=1.0`, unpenalized
intercept, standardized inputs), and no post-freeze refit:

- q inputs, in order: `logit(pDeath)`, `pReserveWin - pOrdinaryWin`;
- q raw coefficients, intercept first:
  `[-1.2774117903706843, 0.6218773831139504, 1.8032915200353896]`;
- r input: `pReserveWin`;
- r raw coefficients, intercept first:
  `[-1.6282353146262838, 4.636485097426466]`;
- `WIN_CONSUMED` conditional-head input: `curHp=floor(maxHP/2)`;
- `WIN_RETAINED` conditional heads use ordinary T0.

The fit used all 427 prospective-support development rows from 124 sources
(362 `WIN_RETAINED`, 53 `WIN_CONSUMED`, 12 `LOSS_CONSUMED`); q fit rows=427
and r fit rows=65. It is bound to the frozen exact-10k Silver teacher
`silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77` and these
component hashes:

| CTM component | SHA-256 |
| --- | --- |
| survival | `2447b2daf1a48a619a5f071488908afd6f0fb83bfd855ee9f379c04120efeaef` |
| max_hp | `66ac8f70da69e29bf9b1364243f6f903e4f74dda1ec8a909ef54a7ea97dc6479` |
| hp | `a667a3cfa7d7eca3cb07b46f50321e443c75e8a58f7627becb1fd69bf90f08c9` |
| potion | `8e04bcd5265fb11b8fa91b4553a84690915f437e7b3afee0b93358e312de3ad6` |
| potion_encoder | `2085010f1aeef7a7957cdc45c851b2424d640037fd0fa981eb7ae7274190f6ef` |
| relic | `e07e79d487152ae294f4915ef4aecd0e8bd38b8dec8d0133a57b6b58af92bd71` |

Frozen artifact SHA-256:
`9f8fb965b24fbd8da1f9600fc9ca0f243e5e9069c47067123c88e36e9f5ebcf9`.
The full fit recipe, feature standardization, source IDs, component hashes and
teacher provenance are in [the artifact](frozen_qr_artifact.json).

## Existing-data T2 confirmation

Before fresh collection, the post-selection B1 extension's new consumed-win
rows confirmed the frozen T2 candidate: 33 scoreable rows from 31 sources
(34 new consumed wins; one Fairy boundary; zero other support exclusions or
domain/legality failures).

| T2 minus T0 | Mean delta | Source-bootstrap 95% CI |
| --- | ---: | ---: |
| HP NLL | -1.60054 nat | [-2.57783, -0.66053] |
| HP CRPS | -4.06102 | [-7.70190, -0.39899] |
| Expected-HP MAE | -3.66847 | [-8.02682, 0.67188] |
| maxHP NLL | +0.00570 | [-0.00050, 0.01676] |
| Potion-mask NLL | +0.04713 | [-0.05365, 0.20573] |

Supported relic-group T2-minus-T0 NLL deltas were attacks `-0.02473`
(CI `[-0.12654, 0.07735]`, 7 sources), cards `-0.21783`
(`[-0.33027, -0.00656]`, 3), shuffles `-0.23037`
(`[-0.45760, -0.05467]`, 3), and turns `+0.01141`
(`[-0.05285, 0.07290]`, 6). This passes the frozen extension-confirmation
gate and keeps T2 as a candidate; it is not qualification. Full source-level
details are in [the confirmation JSON](t2_extension_confirmation.json).

## Predeclared fresh cohort and collection

The freshness audit found no overlap with the 160 previously used Lizard
sources. The assignment was written before candidate generation or paired
outcomes:

- HARD96: sources `4201000..4201095`; choose one prospective-support combat per
  source maximizing frozen `q*(1-r)`, with ascending fight index for exact ties.
- BROAD32: sources `4201096..4201127`; select by the lexicographically smallest
  SHA-256 of `sourceSeed:fightIdx:fixedSalt`, using salt
  `active-lizard-qr-qualification-broad32-salt-2026-09-25-v1`.

The exact 128 IDs, partition, salt, selection rule and freshness audit are in
[source_assignment.json](source_assignment.json). Candidate generation
completed 128/128 sources with 2,466 captured rows and 1,893 eligible
candidates; selection was outcome-blind. Exact-state pairing completed
128/128 with zero quarantines under the frozen fair Silver 10,000-simulation
teacher and the same Silver search RNG seed within each pair. All 128 pairs
passed the exact support audit after stripping active Tail from pre-state and
predictor input; no Fairy Potion or Mark of the Bloom boundary entered the
learned cohort.

| Evidence | SHA-256 |
| --- | --- |
| Source assignment | `46af3ba0397d523da7017daaa92fa5c37813d496fbf5608a7069ea39398ee992` |
| Candidate JSONL | `c0e0e69269a83d612e66ed6ed57e3faa924cda44b502fb7679489b128bd7342d` |
| Candidate manifest | `e28a6c64a2c35f9edc0125b457c2d24e1848d426464bd05d60b392579e0405c5` |
| Frozen target selection | `a78f4e8ddccc39769a9b01f9f4fc59195b79bdfd5ec427b062ee16a03605905b` |
| Paired JSONL | `ad297c0d189290d1956d9fb9a5f08e417f9861238e4986ba33f2f26c0be34d5b` |
| Pair manifest | `a8a38bb7f19a4e2a5ff6407eeb35c42fe886fa343c69cd841cc3ce6f7e42eb23` |
| Pair provenance | `f4962e20688060892a7d467df396695bc77598ef4344ff0f35540445a5f876c8` |
| T2 extension-confirmation JSON | `e469f8e23c436fc17cdc362a11a1d8d6330a92cc597e981a2fa0734db991463c` |
| Qualification analysis JSON | `059c7c9e838860f1099bcc896af1ce2920faf9b6ebf52a9dd8a76def1458cf0e` |
| Analysis script | `8386b51d32e5b12e607e9c4e506ca9c6a1f51614a17311a3a6db62bbd92a2011` |

The outcome arms recorded 84 win / 44 loss for no-Tail and 119 win / 9 loss
for active Tail. Three-class labels were:

| Cohort | `WIN_RETAINED` | `WIN_CONSUMED` | `LOSS_CONSUMED` | Consumed total |
| --- | ---: | ---: | ---: | ---: |
| HARD96 | 52 | 35 | 9 | 44 |
| BROAD32 | 31 | 1 | 0 | 1 |
| Pooled | 83 | 36 | 9 | 45 |

## Phase 4: fresh q/r qualification

Intervals below are source-bootstrap 95% CIs for candidate-minus-B1. There was
no materially incoherent B1 reserve difference. Two BROAD32 rows had tiny
negative float32 differences, `-3.5762787e-7` and `-1.1920929e-7`; their raw
values are retained, and only scoring used the preregistered `1e-6` numerical
epsilon.

### Primary three-class scores

| Cohort | NLL B1 | NLL q/r | q/r − B1 NLL (95% CI) | Brier B1 | Brier q/r | q/r − B1 Brier (95% CI) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| HARD96 | 7.90390 | 0.69657 | -7.20733 `[-21.60793, 0.03782]` | 0.44871 | 0.41230 | -0.03641 `[-0.08913, 0.01367]` |
| BROAD32 | 0.09432 | 0.06078 | -0.03354 `[-0.10324, 0.00184]` | 0.04444 | 0.03555 | -0.00889 `[-0.02677, 0.00009]` |
| Pooled | 5.95150 | 0.53763 | -5.41388 `[-16.22244, 0.01903]` | 0.34764 | 0.31811 | -0.02953 `[-0.06996, 0.00860]` |

Mean NLL and Brier favor q/r in all three cohorts, but no NLL interval is
strictly below zero. The pooled primary NLL gate therefore fails. Brier meets
the point-estimate and no-clear-degradation rules. BROAD32 shows no clear
primary degradation, but contains only one consumed outcome.

### q consumption and r conditional rescue

| Cohort | q NLL delta (95% CI) | q Brier delta (95% CI) | r consumed rows | r NLL delta (95% CI) | r Brier delta (95% CI) |
| --- | ---: | ---: | ---: | ---: | ---: |
| HARD96 | +0.02938 `[-0.04005, 0.09651]` | +0.00743 `[-0.02140, 0.03408]` | 44 | -0.89798 `[-2.54354, 0.00213]` | -0.07934 `[-0.15591, -0.01282]` |
| BROAD32 | +0.02274 `[0.00010, 0.06677]` | +0.01036 `[-0.00010, 0.03118]` | 1 | -1.80099 `[−1.80099, −1.80099]` | -0.57432 `[-0.57432, -0.57432]` |
| Pooled | +0.02772 `[-0.02440, 0.08042]` | +0.00816 `[-0.01335, 0.02869]` | 45 | -0.91805 `[-2.52707, -0.02577]` | -0.09034 `[-0.16639, -0.01888]` |

The q model fails its gate: pooled NLL and Brier point estimates are both
worse than the mechanical B1 `q_B1=1-pOrdinaryWin`. Calibration-in-the-large
for pooled q was `-0.09229` for frozen q (mean prediction `0.25927`, observed
consumption `0.35156`) versus `+0.00469` for B1 (mean prediction `0.35625`).
The pooled r comparison passes its score requirements on all 45 B1-scoreable
consumed rows: NLL improvement CI is strictly below zero and Brier improves.
However, r alone cannot override the rare-event minimum; HARD96's r NLL CI also
crosses zero, and BROAD32 has just one consumed row. Pooled r calibration in the
large was `-0.04012` (mean prediction `0.75988`, observed rescue `0.80000`),
versus `-0.22812` for B1 (mean prediction `0.57188`).

The rare-event gate is **not reached**: 9 `LOSS_CONSUMED` from 9 sources,
against the required 20 from 10; 45 total consumed rows are enough for the
count component but not the loss-source floor. This triggers the required
`LIZARD_QUALIFICATION_INCONCLUSIVE_RARE_EVENT` stop.

## Phase 5: fresh T2 and retained-win checks

T2 was scored on 36 fresh supported `WIN_CONSUMED` rows. Every row scored
under both T0 and T2, with zero domain/legality or downstream head failures.
T2 minus T0 was:

| Metric | Delta | Source-bootstrap 95% CI |
| --- | ---: | ---: |
| HP NLL | -1.34633 nat | [-2.18779, -0.60768] |
| HP CRPS | -3.72108 | [-6.61319, -1.01197] |
| Expected-HP MAE | -3.46591 | [-6.81904, -0.27249] |
| maxHP NLL | +0.00031 | [-0.00025, 0.00102] |
| Potion-mask NLL | -0.08020 | [-0.17018, -0.01748] |

No supported relic group showed clear T2 degradation: attacks `+0.01803`
(CI `[-0.10010, 0.17551]`, 9 sources), cards `-0.05939`
(`[-0.21040, 0.07492]`, 4), shuffles `-0.13865`
(`[-0.38745, 0.08847]`, 6), turns `-0.00919`
(`[-0.09790, 0.09866]`, 3). The numerical fresh-T2 gate passes, but the overall
qualification remains stopped at Phase 4.

On retained wins, ordinary T0 heads were compared with paired no-Tail
both-win rows: 83 retained wins, 84 both-win controls, and 79 common scored
sources. The supported cards relic-constraint NLL delta was `+0.12641` with CI
`[0.02769, 0.24579]` on six sources; this is a sparse subgroup shift to
monitor, not a qualification result. HP NLL delta was `-0.02550`
(`[-0.19394, 0.14276]`), CRPS `-0.91351` (`[-1.74039, -0.12082]`), expected-HP
MAE `-1.74070` (`[-2.97427, -0.54305]`), and potion-mask NLL `+0.09685`
(`[-0.00036, 0.19510]`).

## Stop boundary and verification

The exact prospective data predicate for this experiment was:

1. remove active Lizard from the pre-state and predictor input;
2. require `composed.full_support_reasons(stripped_pre, stripped_predictor,
   frozen_models) == []`;
3. exclude Fairy Potion from learned-Lizard rows; keep Mark of the Bloom on its
   existing exact path.

All 128 collected pairs passed that predicate. Production support remains
unchanged: active Lizard still fails closed as `active_unqualified_lizard`
when its legal post-state is nondeterministic. Fairy Potion plus active Tail
remains unqualified, Mark of the Bloom retains its existing exact handling,
and spent Tail continues through ordinary CTM support when otherwise eligible.

Not run because the frozen stop condition fired: Phase 6 ancestral exposure
and hard-validity draws, native q/r integration, Python/native parity, support
promotion, and live seed `13027029`. Their outcomes are **not established**.
Recommend any additional frozen qualification data use the repository's
designated GCP/large-research procedure, retaining this artifact, feature
recipe, cohort rules, and gates without local seed expansion or tuning.

Focused Python verification passed: 19 tests across the q/r artifact and
minimal-correction suites; analyzer `py_compile`; pair/target/candidate hash
validation during analysis; two analysis runs produced byte-identical JSON
SHA-256 `059c7c9e838860f1099bcc896af1ce2920faf9b6ebf52a9dd8a76def1458cf0e`;
`git diff --check`. The Release `one_combat` build for the collector was
completed before pairing. Repository CI, native parity, and live gameplay
verification were not run.

**Knowledge impact:** current research status and experiment evidence updated;
runtime behavior, interfaces, and support remain unchanged.
