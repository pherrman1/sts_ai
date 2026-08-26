# 2026-08-26 — Silver sticky decision-quality probe

Date: 2026-08-26
Session/task: Implement the post-PR #59 state-targeted decision-quality experiment; do not run its formal gameplay study.

## Decision

Use a default-off, in-process diagnostic at ordinary ACTIVE sticky-cap states.
The executed ACTIVE action is fixed before three newly constructed private
Silver searches evaluate the same `BattleStateWire` at 3,700, 25,000, and
50,000 simulations. Sequential `GAMBLE` and `EXHAUST_MANY` private
subdecisions are counted as excluded rather than evaluated.

## Rationale

`BattleStateWire` is already the isolated value-only state boundary, so a
general serializer is unnecessary. `BattleSearcher::getBestAction()` selects
the maximum-root-edge-visits action; its existing UCB edge statistic is the
child `evaluationSum / simulationCount`, which the CSV records verbatim for
reference-root actions and retains Silver's root-Q values as descriptive
diagnostics only.  Because final action selection is by root-edge visits, Q
gaps are not treated as regret and do not enter the scientific decision gate.

**Open question:** the formal 16-seed collection and independent review must
decide whether inherited visits improve decisions; this implementation makes no
promotion claim.

## Alternatives considered

- General live-state serializer — rejected because the current wire protocol
  already materializes independent Silver roots without live pointers or RNG.
- Shadowing transaction subdecisions — rejected as out of scope and low value
  for the first measurement.
- A synthetic new root Q convention — rejected; only the searcher's existing
  root visit rank and UCB child statistic are emitted.

## Evidence

- `third_party/silver_lightspeed/bridge/SilverLiveBackend.cpp` — sampling,
  isolated shadow execution, row/summary output, and hard configuration gate.
- `third_party/silver_lightspeed/bridge/SilverStateBridge.cpp` — canonical
  semantic fingerprints and root action summaries at the private bridge.
- `tools/analyze_silver_sticky_quality.py` — strict schema validation,
  seed-level bootstrap, stratification, and preregistered decision rule.
- `apps/silver_bridge_test.cpp`; `apps/silver_integration_test.cpp` — focused
  fresh-root, fingerprint, isolation, and deterministic-sampler fixtures.

## Status and follow-up

- Implementation pending focused build/test verification and independent PR
  review. Do not launch the formal 16-seed study until the reviewed SHA is
  frozen.
