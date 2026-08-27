# OOC survival × continuation-value diagnostic

Date: 2026-08-27

## Decision

Reject pure K=3 QWin as a drop-in replacement for the dense K=3 score on the
observed discordant selected-action pairs. The explicit survival-vs-strength hypothesis
is **INCONCLUSIVE**, not rejected. Do not promote a policy or train a model from
this result; production OOC behavior remains unchanged.

## Rationale

Because dead branches already have `labelWon=0`, the exact identity
`P(S) * E[V_win | S] = E[V_win]` means this factorization is QWin, not a new
objective. On the 21 adjudicated disagreements both chosen actions had
`p_survive=1`, so the proposed score collapsed empirically to pure QWin and
never expressed a risk-strength tradeoff between those choices. Four of the 21
decision contexts did contain another legal action with `p_survive<1`; the
all-surviving statement applies only to the two rankers' selected pair.

The original 14/6/1 result and mean regrets `3.9792/6.8929` used the shaped
full-run utility `10*won + final HP`. Reanalysis of the same paired raw rows
using terminal win alone gives current/factor/tie `3/3/15`, mean win-probability
regret `0.03571/0.03274`, and median regret `0/0`. Thus the dense-utility result
rejects QWin under that shaped utility, while terminal-win adjudication is
small and inconclusive. The adjudicator compared only the two rankers' choices,
not every legal action.

The fixed regime nevertheless contains 46/367 actions with `p_survive<1`, 15/64
decisions with some sibling survival spread, and 3 opposing-order
safety-strength tradeoffs. The encounter-marginalized regime contains 88/367,
25/64, and 15 respectively. Only 2 of its 22 dense-vs-QWin ranking
disagreements have different survival probabilities for the selected actions,
too few for the requested 16--32-decision adjudication. The existing corpus
therefore shows that targeted survival-sensitive sampling is feasible and
needed; uniform expansion is not justified.

## Evidence

- `apps/one_combat.cpp::strategicMargGen`, `oocFactorEvaluate`
- `tools/analyze_ooc_factor.py`
- `docs/experiments/ledger-06.md` OOC survival × continuation-value entry
- Raw artifacts under `build/ooc_factor_e4/`

## Status and follow-up

**REJECT pure K=3 QWin on the observed discordant selected-action pairs;
INCONCLUSIVE on explicit survival-vs-strength modeling.** The diagnostic code
is offline-only. No learned model, production gate, combat-leaf E3c repeat, or
gameplay benchmark is authorized by this result. A later decomposition test
would test a statistical-learning hypothesis with auxiliary targets/heads,
not a distinct factorized value objective; it should retain the V4 model family
so architecture family is not an additional experimental variable.

Follow-up workflow correction: the analyzer now requires a measurable
`p_survive` contrast by default before emitting an adjudication manifest
(one replicate, `1/R`), while `--min-survival-delta 0` is an explicit escape
for a continuation-only audit. `oocfactoreval` resolves every manifest state
and both action bits before opening its output or running a full continuation,
so replay drift fails atomically instead of producing a partial expensive
artifact.

Zero-simulation correction artifacts are
`build/ooc_factor_e4/corrected_fixed/summary.json`,
`corrected_fixed/survival_coverage.csv`, and the corresponding files under
`corrected_marg/`.
