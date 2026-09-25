# Targeted active Lizard Tail rescue experiment

**Status: cohort and analysis complete; descriptive research only.**
The 32-pair screen in the neighboring `lizard_tail_rescue_pilot_2026-09-23`
packet was too sparse for the rescue decomposition. This follow-up targets
precombat CTM risk without selecting on either paired combat result.

## Hypothesis and baseline

The frozen ordinary survival head may provide enough risk ordering to target
informative no-Tail deaths and Tail consumption. Active Tail may still change
Silver's policy before the relic fires. The initial screen therefore measures
ordinary death, active-Tail win, Tail consumption, and policy divergence
separately, then scores existing conditional postcombat heads on the Tail
outcomes using the paired ordinary precombat input with Lizard removed.

The baseline is the frozen ordinary fair exact-10k Silver teacher
`silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77` plus the
hash-verified CTM survival component loaded by
`tools/combat_transition_composed.py`. The mechanical-reserve comparison is
explicitly a **proxy**: it re-scores that existing survival head after raising
visible starting HP by `floor(maxHP/2)`, capped at maxHP. That does not replay
the lethal hit, discard overkill, or capture policy changes, so it is not an
exact Tail-mechanics simulator.

## Frozen sample and selection

- Fresh source seeds: `4200300..4200427` (128 source seeds maximum).
- Stage 1 uses the dedicated `combattransitionlizardtargetcandidategen` mode
  to record ordinary Silver precombat input and full persistent state for
  every generated combat in those sources. This mode permits a different
  collector executable/repository SHA while continuing to enforce the frozen
  Silver settings, model artifact hashes, and all teacher environment fields
  other than `STS_EXECUTABLE_GIT_SHA`; the actual candidate producer Git and
  executable hashes are recorded in its manifest.
- The selector scores only the precombat predictor input with the frozen
  survival head. Its source code does not read combat outcome, post-state, or
  final HP when selecting a target.
- It selects at most one fight per source. Risk bands are `[0.10,0.20)`,
  `[0.20,0.35)`, `[0.35,0.55)`, and `[0.55,1.0]`, with 32 initial targets
  per band. If a band has fewer than 32 distinct sources, remaining slots are
  redistributed round-robin over available risk bands; `<0.10` is only a final
  fallback and will be reported separately.
- Stage 2 replays the selected source/fight and requires exact equality of the
  risk-scored predictor input and full persistent precombat state before
  creating paired no-Tail and active-Tail arms.
- Seed guard applies to both stages; each stage is capped at 128 source seeds.
  The pair sample may be smaller if the candidate cohort has fewer than 128
  distinct eligible sources, but collection stops below the 100-pair floor.

The intended target is 128 pairs. Desired information thresholds are at least
30 no-Tail deaths and 20 Tail consumptions. If either threshold is missed at
the 128-source cap, report the shortfall and do not extend this cohort.

## Recorded outcomes and decision use

Each pair records both outcomes, active Tail consumption, start/end HP and
maxHP, postcombat potions/relic state, the first committed Silver action bits,
and every committed action bit in each arm. Analysis computes canonical SHA-256
action-trace hashes, first-action/full-trace divergence, and common-prefix
length, with a separate summary for active wins that retained Tail.

The frozen maxHP, HP, potion, and supported non-Lizard relic heads are scored
teacher-forced on active wins, using the paired ordinary input and Tail-stripped
post-state. Consumed and retained Tail wins are reported separately. These are
descriptive screens; they do not by themselves qualify a head or artifact.
For retained-Tail wins where both paired arms win, report source-paired
treatment-minus-control score deltas. Call a shift material for follow-up only
when at least 20 supported pairs are available and a mean NLL increase exceeds
`0.1` nat with a source-bootstrap 95% interval wholly above zero. Falling short
of either condition is inconclusive, not a pass for reuse or evidence of
equivalence.

Compare ordinary-head risk, the HP-shift reserve proxy, active win, consumption,
and action divergence by the predeclared risk bands. If conditional heads remain
well-behaved, the next research candidate is two small survival/consumption
heads. A specialist becomes justified only if postcombat distributions also
show a material Tail-specific shift, particularly among retained-Tail wins.
No training, runtime integration, support expansion, or default change is
authorized by this cohort.

## Observed results

Candidate generation completed all 128 source seeds and recorded 2,700
ordinary combat rows with zero quarantines. The selector then chose 128 unique
sources. Since risk-band availability overlaps by source, the final selected
counts were 40 in `[0.10,0.20)`, 32 in `[0.20,0.35)`, 20 in `[0.35,0.55)`,
17 in `[0.55,1.0]`, and 19 fallback targets below `0.10`. Paired collection
completed all 128 targets with zero quarantines and exact precombat input and
persistent-state matches.

The no-Tail arm died in 27/128 pairs (21.1%); the active-Tail arm won 123/128
(96.1%) and consumed Tail in 32/128 (25.0%). Among the 27 no-Tail deaths, the
active arm won 22 (81.5%): Tail was consumed in 14 and retained in 8. This
confirms both effects in the proposed decomposition: mechanical rescues and a
policy effect that can produce a win without consuming Tail. Across all pairs,
Silver's first action changed in 59/128 (46.1%) and its complete committed
action trace changed in 122/128 (95.3%). Among active wins with Tail retained
(96 pairs), the corresponding rates were 43/96 (44.8%) and 90/96 (93.8%).

The cohort mean ordinary CTM death probability was 27.4% against 21.1% observed
no-Tail deaths (Brier 0.1254). By band, observed no-Tail death rates were
10.0%, 18.8%, 20.0%, and 76.5% for the four risk bands; the 19 low-risk
fallback pairs had no deaths. These risk-stratified figures are descriptive,
not a recalibration result. The HP-shift mechanical proxy predicted 90.3% mean
win probability against 96.1% active-Tail wins (Brier 0.0470); it is still not
an exact lethal-crossing replay and does not capture the frequent policy
changes.

For 71 pairs where both arms won and active Tail was retained, treatment-minus-
control head-score changes did not meet the preregistered material-shift rule.
HP NLL changed by `+0.034` nat (source-bootstrap 95% CI `[-0.121,+0.182]`),
potion-mask NLL by `+0.060` nat (`[-0.043,+0.173]`), and maxHP NLL by zero.
Supported relic-group paired counts were 12 attacks, 8 cards, 5 shuffles, and
8 turns; all intervals crossed zero. This does not establish equivalence: the
analysis is teacher-forced and unsupported mutation rows are excluded. On
active wins with consumed Tail, existing postcombat heads scored 22/27 rows;
five rows were outside current support. No head was trained or qualified.

The results favor testing a small active-Tail survival/consumption correction
on top of the ordinary CTM before a full specialist. The high first-action and
trace divergence means the correction must account for policy adaptation; the
mechanical reserve proxy alone is inadequate as a complete treatment model.
The retained-Tail post-head comparison did not demonstrate a material shift,
but remains descriptive and cannot certify reuse. Production
`active_unqualified_lizard` remains unchanged; no model, runtime, default,
native/Python parity, or gameplay qualification changed.

## Integrity and provenance

- Candidate JSONL SHA-256: `8b5b2d349208075e4de0f40580ce223807c6acbf7c004944858b5370657d2468`.
- Candidate manifest SHA-256: `9620b38e6bcd006f5bcfe504d0b388964c90970f1d1e26045fd872da24b4d9f1`.
- Target-selection JSON SHA-256: `36f444009306c2df140512fa17cadfdf28ee5845117af9a1a7d66299ac35d89c`.
- Paired JSONL SHA-256: `1bfe609be0c32b0a504e5a97622ea385269ca3c5d1693a49c079421fcbae7d0e`.
- Paired manifest SHA-256: `122bd32fdf834dccd1003d3f490ff63fba47c17152655c0a200e81c6d0c40ab4`.
- Analysis JSON SHA-256: `0958e0ed15c53216eda2b29ead8d01d19257f94cce9dde2b6c88a753e004b4dd`.
- Candidate and paired producer Git SHA: `8fa9f5ca0b22cf69417146dfbb5ac4fc1edf31c3`;
  executable SHA-256: `250d26bfa21a15b2859931822f0b3185cbd4050199772218f51262dfe6bcc5d2`.
- Frozen teacher: `silver-ordinary-fair-exact10k-combat-transition-runtime16-f0bbd77`.
  The dedicated candidate mode permits producer SHA drift while checking the
  frozen Silver settings, teacher environment except its producer SHA field,
  and model artifact hashes; the actual producer identities are recorded.
- Frozen ordinary CTM model hashes are recorded in `targets.json` and
  `analysis.json`.

## Minimal three-state correction diagnostic

The follow-up used the same 128 pairs and frozen ordinary CTM heads. It did not
collect more fights or change production behavior. Source JSONL, pair manifest,
and target-selection hashes are repeated in
`minimal-correction-analysis.json`; the SHA-256 of that analysis artifact is
`0255a9c6b90c8ce305d99f4bc68b0d56dea5e892ae4979ff2b938c31312b5459`. The
analysis implementation is `364e0cc9d8e22ac880bee5feace2829dfe2ecf3a` on top
of the previously pushed cohort branch head `3186d3e505f55c82b008798edfacfd56a4a047bd`.

### Phase A: fixed conditional HP input treatments

The 27 `WIN_CONSUMED` rows were rescored, with 22 rows supported by existing
conditional heads and five still excluded by current hard support rules. No
transformed target left the frozen HP domain. `T0` uses ordinary starting HP;
`T1` adds `floor(maxHP/2)` capped at maxHP; `T2` starts the conditional heads
at `floor(maxHP/2)`. Metrics below are means over the 22 scoreable rows.

| Treatment | HP NLL | HP CRPS | Expected HP MAE | maxHP NLL | Potion-mask NLL |
| --- | ---: | ---: | ---: | ---: | ---: |
| T0 ordinary | 5.121 | 11.892 | 15.917 | 0.01037 | 0.874 |
| T1 reserve | 4.036 | 7.818 | 10.424 | 0.00994 | 0.809 |
| T2 revive | 4.037 | 9.938 | 14.127 | 0.01042 | 0.769 |

Supported relic-constraint mean NLLs (counts are sparse):

| Treatment | Attacks (n=5) | Cards (n=4) | Shuffles (n=2) | Turns (n=4) |
| --- | ---: | ---: | ---: | ---: |
| T0 ordinary | 2.086 | 2.428 | 0.798 | 1.281 |
| T1 reserve | 2.357 | 2.327 | 0.875 | 1.572 |
| T2 revive | 2.145 | 2.213 | 1.043 | 1.367 |

Paired source-bootstrap T1-minus-T0 HP NLL was `-1.085` (95% CI
`[-2.161,-0.320]`), CRPS `-4.074` (`[-8.515,-0.134]`), and expected HP MAE
`-5.493` (`[-10.718,-0.683]`). T1 had clear score degradation in supported
relic constraints for attacks (+0.271, 5 pairs, CI `[+0.022,+0.509]`),
shuffles (+0.077, 2 pairs, `[+0.019,+0.135]`), and turns (+0.291, 4 pairs,
`[+0.231,+0.350]`), so it was not retained.

T2-minus-T0 HP NLL was `-1.084` (95% CI `[-2.165,-0.331]`), HP CRPS `-1.954`
(`[-5.769,+1.689]`), and expected HP MAE `-1.790` (`[-6.170,+2.468]`).
maxHP NLL delta was `+0.000043` (`[-0.000128,+0.000237]`), potion-mask NLL
delta `-0.105` (`[-0.222,-0.015]`). No supported relic-group interval showed a
clear degradation; group counts were only 2–5. **T2 is retained as a
development candidate**, because HP NLL improved with its interval below zero,
CRPS improved in point estimate, MAE did not worsen in point estimate, and no
domain or clear downstream issue was found. Its CRPS interval crosses zero, so
this is not a qualification result.

### Phase B: coherent three-class outcome model

The observed legal class counts across all pairs were 96 `WIN_RETAINED`, 27
`WIN_CONSUMED`, and five `LOSS_CONSUMED`; no `LOSS_RETAINED` is representable.
Six Fairy Potion rows were excluded from q/r fitting and remain an exact
precedence boundary. The modeled set therefore had 122 rows: 92 retained wins,
25 consumed wins, and five consumed losses. Mark of the Bloom remains an exact
boundary and was absent from this cohort.

The fixed B0 source-grouped train-frequency baseline scored three-class NLL
`0.6868`, multiclass Brier `0.3927`, and mode accuracy `75.4%`. B1's mechanical
reserve probabilities were coherent on all 122 rows; its NLL was `0.5774`,
Brier `0.3279`, and mode accuracy `78.7%`. The five-fold, source-grouped L2
factorized correction used only `logit(pDeath)` and reserve uplift for q, and
`pReserveWin` for r. Out-of-fold NLL was `0.5641`, Brier `0.3181`, and mode
accuracy `80.3%`. The correction-minus-B1 paired bootstrap intervals included
zero for both NLL (`-0.0134`, CI `[-0.0917,+0.0628]`) and Brier (`-0.0098`,
`[-0.0311,+0.0144]`), so it has no clear signal over the mechanical baseline.

Consumption q scored Brier `0.1417` / NLL `0.4378` on 122 rows. Conditional
rescue r scored Brier `0.1575` / NLL `0.5136` on 30 consumed rows, including
the five losses. Held-out fold r Brier ranged from `0.047` to `0.396`; raw
calibration coefficient ranges were q intercept `[-1.117,-0.692]`, q logit-risk
`[+0.458,+0.586]`, q reserve-uplift `[+0.988,+2.329]`, r intercept
`[-0.466,+0.749]`, and r reserve-proxy coefficient `[+1.327,+2.223]`. Observed
versus mean predicted class probabilities were B1: retained `0.754/0.723`,
consumed-win `0.205/0.178`, consumed-loss `0.041/0.099`; correction:
`0.754/0.754`, `0.205/0.205`, and `0.041/0.040` respectively.

| Fold | Train consumed losses | q Brier / NLL | r rows, Brier / NLL | B0 / correction 3-class NLL |
| ---: | ---: | ---: | ---: | ---: |
| 0 | 5 | 0.156 / 0.476 | 7, 0.059 / 0.265 | 0.666 / 0.550 |
| 1 | 4 | 0.107 / 0.359 | 6, 0.133 / 0.431 | 0.659 / 0.463 |
| 2 | 3 | 0.144 / 0.432 | 6, 0.267 / 0.790 | 0.758 / 0.630 |
| 3 | 5 | 0.188 / 0.549 | 7, 0.047 / 0.241 | 0.684 / 0.620 |
| 4 | 3 | 0.115 / 0.374 | 4, 0.396 / 1.135 | 0.668 / 0.563 |

Per-fold raw coefficients are in the JSON artifact. The 5 losses remain
too few to establish rescue prediction. A useful next reassessment target is
**20 additional `LOSS_CONSUMED` examples (25 total)**; this is a sample-size
target for evidence, not a qualification guarantee.

### Phase C: offline ancestral validity

The prototype sampled 32 draws on each of 98 supported source states (3,136
class draws); 30 states used fallback, including all six Fairy Potion rows and
the existing unsupported mutation cases. It used out-of-fold factorized class
probabilities and T2 for consumed wins. There were 2,363 retained wins, 656
consumed wins, and 117 consumed losses. `LOSS_RETAINED` draws and
spent-to-active transitions were both zero. All 3,136 class transitions agreed
with Tail state; all 3,019 sampled victory states had legal HP, potion count,
and persistent relic bits, and all 117 terminal loss snapshots passed the
state-shape validation. No conditional-head fallback occurred after support
admission. The fixed-seed sample digest was
`b37f2957a36a7ff411b568218158796eac36b6cfe56a76beacc8c97d2a23d346` and
matched a repeat run.

**Classification: `LIZARD_MINIMAL_CORRECTION_DATA_LIMITED`.** T2 looks useful
for consumed-win HP conditioning. The offline prototype reuses ordinary
conditional postcombat heads with T0 on retained wins and T2 on consumed wins;
this is promising development reuse, not runtime qualification. The factorized
correction is coherent, but the five consumed losses do not establish r and
the correction did not clearly beat B1. Fairy Potion and Mark of the Bloom
boundaries, all current support exclusions, and production
`active_unqualified_lizard` remain unchanged. Only fold-local logistic
calibrators were fitted in memory for this diagnostic; no CTM head was
retrained, and no calibration weights were persisted or exported. No
native/Python parity, live gameplay, or runtime qualification was run.

Raw command after freezing implementation SHA `364e0cc9d8e22ac880bee5feace2829dfe2ecf3a`:

```text
python3 -m tools.combat_transition_lizard_minimal --manifest docs/experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/paired.jsonl.manifest.json --output docs/experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/minimal-correction-analysis.json --draws 32
```

## B1-ranked candidate-pool extension

This extension reused the frozen 2,700-row ordinary precombat pool and ranked
each supported, coherent, unused fight by the fixed B1 mechanical
`P(LOSS_CONSUMED) = 1 - pReserveWin`. No new source trajectories were
generated. Each selected arm was replayed under the same frozen exact-10k
Silver teacher and exact-state pairing contract. The selector was outcome
blind. Collection was split into bounded calls; after the first selection
overlapped 35 source/fight keys in the original cohort, all later target files
excluded previously paired keys. Multiple fights per source were retained,
and the combined q/r folds and bootstrap resampled whole source seeds.

| New collection slice | Pairs | Unique fights added | `WIN_RETAINED` | `WIN_CONSUMED` | `LOSS_CONSUMED` | First action changed |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| B1 batch 1, less 35 original-cohort overlaps | 128 | 93 | 65 | 20 | 8 | 46/93 |
| B1 batch 2 | 127 | 127 | 121 | 6 | 0 | 46/127 |
| B1 batch 3 top 32 | 32 | 32 | 31 | 1 | 0 | 12/32 |
| B1 batch 3 next 95 | 95 | 95 | 88 | 7 | 0 | 32/95 |
| **New unique total** | **382 raw** | **347** | **305** | **34** | **8** | **136/347** |

The original 128-pair cohort's five losses plus these eight new losses give 13
distinct `LOSS_CONSUMED` fights, below the target of about 25 total (20 new).
Across the 347 new fights, the no-Tail arm died 40 times; active Tail won 33
of those. Active Tail also lost once when the no-Tail arm won, so the
three-state label is defined from active-Tail outcome and postcombat Tail
state, not from control death. Tail was consumed in 42/347 fights. The first
Silver action changed in 136/347 (39.2%), showing a substantial policy effect
within this extension.

The combined comparison de-duplicates by `(sourceSeed, fightIdx)`, keeping the
original cohort's earlier observation when a later batch repeats that key.
The 35 overlap pairs are exactly reproducible in their combat observations:
all no-Tail and active-Tail transition states, outcomes, Tail states, and full
Silver action traces match. Only `pair.targetRiskBand` differs, because the
later selector labels rows `B1_LOSS_CONSUMED`; the comparator ignores this
selection-only metadata. The duplicate rows are still excluded rather than
treated as independent examples.

The broad descriptive analysis has 475 unique paired fights; after excluding
24 Fairy/Bloom exact-boundary rows, it contains 451 rows from 124 sources.
Five-fold CV and the paired bootstrap group by source; there are 1–4 modeled
rows per source (median 4). `T2` remains fixed as selected in Phase A; it was
not retuned or used as an input to this outcome comparison.

| Three-class metric | Fixed B1 | Source-grouped q/r | q/r minus B1, source-bootstrap 95% CI |
| --- | ---: | ---: | ---: |
| NLL | 1.9122 | 0.3544 | -1.5578 `[-4.6800, -0.0090]` |
| Multiclass Brier | 0.2158 | 0.1994 | -0.0164 `[-0.0303, -0.0024]` |

Observed / mean predicted class rates were `WIN_RETAINED` `0.843/0.786` and
`WIN_CONSUMED` `0.129/0.122` for B1, and `0.843/0.842` and `0.129/0.131`
for q/r. For `LOSS_CONSUMED`, B1 predicted `0.092` against `0.029` observed;
q/r predicted `0.027`. This explains why the fixed B1 tail risk was not a
reliable empirical event-rate estimate in the lower-ranked candidate slices.

The grouped q consumption head scored Brier `0.0897` / NLL `0.2918` on 451
rows (observed rate `0.1574`, mean prediction `0.1581`). The grouped r
conditional rescue head scored Brier `0.1249` / NLL `0.3980` on 71 consumed
rows (observed rate `0.8169`, mean prediction `0.8172`). All five fold fits
converged. These are development diagnostics; 13 loss cases remain too few for
qualification, and the score improvement does not establish a stable rescue
head.

### Prospective runtime-support-domain correction

The broad result above is descriptive. A prospective-domain rerun reapplies
`composed.full_support_reasons()` to each pair's no-Tail predictor input and
active-Tail pre-state after removing Lizard Tail from both. It also excludes
the existing Fairy Potion and Mark of the Bloom native boundaries. This drops
24 additional unsupported rows from the 451-row broad comparison; the reasons
are recorded in the analysis JSON (some rows have more than one reason).
The resulting support-domain cohort has 427 fights from 124 source groups:
362 `WIN_RETAINED`, 53 `WIN_CONSUMED`, and 12 `LOSS_CONSUMED`.

| Three-class metric, support-domain rows | Fixed B1 | Source-grouped q/r | q/r minus B1, source-bootstrap 95% CI |
| --- | ---: | ---: | ---: |
| NLL | 1.9890 | 0.3427 | -1.6463 `[-4.9543, -0.0132]` |
| Multiclass Brier | 0.2096 | 0.1932 | -0.0164 `[-0.0310, -0.0011]` |

The q/r correction still scores better on the prospective runtime domain in
this development cohort. The intervals are narrow at their upper ends and
the cohort contains only 12 supported `LOSS_CONSUMED` outcomes, so the result
remains promising but data-limited and does not qualify a rescue model.
The 34 newly observed `WIN_CONSUMED` examples are confirmation data for the
already frozen T2 treatment; a future T0-versus-T2 scoring check can use them
without retuning T2.

After excluding all 475 paired fight keys, B1 scored 1,611 remaining
supported/coherent candidate fights with summed `P(LOSS_CONSUMED)` of only
`1.4045` (mean `0.000872`). This is a model-based screening estimate, not an
empirical guarantee. Combined with zero losses in the 254 unique pairs from
batches 2 and 3, it indicates that the frozen candidate pool cannot plausibly
provide the 12 additional losses needed for the target. Collection therefore
stopped without generating new trajectories. The targeted cohort also shows
that B1 risk is overconfident in these lower-ranked slices: batch 2 had mean
predicted loss mass `6.05` but no observed losses, while batch 3's 127 targets
had predicted mass about `2.35` and no observed losses.

No specialist CTM, head retraining, runtime integration, model export,
qualification, or production support change followed. The production
`active_unqualified_lizard` guard remains fail-closed.

### Extension artifacts and provenance

- Batch 1 pair JSONL / manifest SHA-256: `0d4f5276c7e3e0636afc9c6355620de4fcea9d482ec0bb93f22853ebfdf8e1ea` / `e84f3a00af1c05ecda760b862b6278650f078165f39437ef6178f7aa897da7b9`.
- Batch 1 target selection SHA-256: `c9398b22125d379033202c8055a705ac3e5141e2e2a84ac6e3b8d42a668fe4f4`.
- Batch 2 pair JSONL / manifest SHA-256: `033435e10413e64add99ef4f260d2ce95cccba6b82e3241b58b62743591f942b` / `9aa206070d582b5d4c351d7fe6c70c5c13f0ebcf1656db2640b5ed7a77cc84be`.
- Batch 2 target selection SHA-256: `1325eca2c7134c15d7b175074ca1987268f241524a2c55296cd6583f40f38902`.
- Batch 3 top-32 pair JSONL / manifest SHA-256: `ced4ed9457de646c5241060c9365ab2fcc83b3401b61690623d8f64eb5ff8248` / `2349b4daa1c9b3b52e7c9628076494af903a85676b7004693fe933f5390cfcb7`.
- Batch 3 top-32 target selection SHA-256: `6036e7adfae0bfba5ae5597b9b911300da4030c277a4f8200a0c48034bb6a3dd`.
- Batch 3 next-95 pair JSONL / manifest SHA-256: `095737b22022bb010b0be8fdb9e2a90f8c2b039724f4bec2086ebcb22be29b7b` / `3d923737d0a51c19767c1ec01b17ec14353b5d19183224188a9fcb09c911f63d`.
- Batch 3 next-95 target selection SHA-256: `2aed6e3c597b5bc8a3d4e8254e3526eab14c0106a0d0ab7c504425ae600508ef`.
- Broad descriptive analysis: `b1-qr-combined-analysis.json`, SHA-256 `df32919f47d947f474398adbbb72a38cc424b6d654ca1d8a2890d42948c8234e`.
- Prospective runtime-support analysis: `b1-qr-runtime-support-analysis.json`, SHA-256 `64c4b4db49f7aaaada8345e8dbb2205b3cfc466d0bcaff6d43471fa958502c7f`.
- Remaining-pool selection/risk summary: `b1-targets-batch-04.json`, SHA-256 `3892c2f2e993f39651736c96d26896d0b64671bfcde168840a4091a09bd6a7c7`.
- Every pair manifest binds to the same frozen exact-10k teacher, Silver settings,
  source trajectory, model artifact hashes, and candidate pool SHA recorded above.

All pair generations used the following seed-guarded command with `N` and the
paired JSONL/target-selection paths from each manifest (128, 127, 32, and 95
respectively); the teacher, baseline SHA, and producer SHA were identical:

```text
env STS_EXECUTABLE_GIT_SHA=f0bbd7721e7cc1453976ebb91ee11ebe6127a2bf STS_FAIR=1 STS_NATIVE_OOC=1 STS_SEARCHER3=0 STS_SILVER_ADAPTIVE=0 STS_SILVER_EXACT_ROOT_BUDGETS=1 STS_SILVER_REUSE_CAP_MODE=allocated STS_SILVER_SEARCH=1 STS_SILVER_TELEMETRY=1 STS_SILVER_VNET_LEAF_DIRECT=0 ./tools/seed_guard.sh build/linux-gcc-debug/one_combat combattransitionlizardtargetpairgen N 10000 0 PAIRED_JSONL TARGET_SELECTION /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/teacher.json 79b3be84b21f9314392478a78b2a5b3eed94fb77 8fa9f5ca0b22cf69417146dfbb5ac4fc1edf31c3
```

The combined analysis command was:

```text
python3 -m tools.combat_transition_lizard_b1_rescue analyze --manifest docs/experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/paired.jsonl.manifest.json --manifest docs/experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/paired-b1-batch-01.jsonl.manifest.json --manifest docs/experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/paired-b1-batch-02.jsonl.manifest.json --manifest docs/experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/paired-b1-batch-03.jsonl.manifest.json --manifest docs/experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/paired-b1-batch-03-next95.jsonl.manifest.json --output docs/experiments/evidence/lizard_tail_targeted_rescue_2026-09-23/b1-qr-combined-analysis.json
```

The same command with `--support-domain` and output path
`b1-qr-runtime-support-analysis.json` produces the prospective-domain result.
