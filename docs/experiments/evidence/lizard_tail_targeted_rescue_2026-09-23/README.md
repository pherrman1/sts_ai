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
