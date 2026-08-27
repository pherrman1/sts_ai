# OOC survival × continuation-value diagnostic

Date: 2026-08-27

## Decision

Reject the proposed OOC action ranking on the observed all-surviving
discordant set:
`P(alive at K=3) * E[V_win at K=3 | alive]`. Do not train an NN/GBM and do not
change production OOC behavior.

## Rationale

On 21 discordant OOC decisions, matched full-run adjudication favored the
existing dense ranking 14 times, the factorized ranking 6 times, with 1 tie.
The factorized ranker's mean two-choice comparative regret was higher
(`6.8929` versus `3.9792`). It therefore failed both preregistered promotion
conditions. The adjudicator compared the two rankers' chosen actions rather
than establishing the best value across every legal action.

All compared choices had `p_survive=1` in the 16-replicate K=3 producer.
Accordingly, this sample does not establish how the factorization behaves in a
rare decision where sibling actions have observably different K=3 survival;
it does establish that the resulting ranking is not a useful replacement on
the observed discordant set.

## Evidence

- `apps/one_combat.cpp::strategicMargGen`, `oocFactorEvaluate`
- `tools/analyze_ooc_factor.py`
- `docs/experiments/ledger-06.md` OOC survival × continuation-value entry
- Raw artifacts under `build/ooc_factor_e4/`

## Status and follow-up

`REJECT`. The diagnostic code is offline-only. No learned model, production
gate, expanded screen support, combat-leaf E3c repeat, or gameplay benchmark
is authorized by this result.
