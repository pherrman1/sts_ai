# Targeted active Lizard Tail rescue experiment

**Status: pre-registered implementation; data collection has not started.**
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
- Stage 1 records ordinary Silver precombat input and full persistent state
  for every generated combat in those sources.
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
