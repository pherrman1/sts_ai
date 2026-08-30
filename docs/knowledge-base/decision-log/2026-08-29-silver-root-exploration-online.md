# Silver root-only exploration online follow-up

Date: 2026-08-29

## Decision

Record `ROOT_EXPLORATION_GAMEPLAY_INCONCLUSIVE`. Keep ordinary Silver root
exploration c=25.0 as the production behavior. Do not promote a lower-root
candidate or restore Sequential Halving/root-pruning machinery.

## Evidence and reasoning

The earlier offline control (§193) rejected all lower candidates under its
25k-A selection rule before the independent 25k-B gate. Because offline
decision quality does not establish online gameplay quality, a separate,
explicitly exploratory GCP follow-up was run with no reuse of the historical
931000–931063 block. A broad screen used eight fresh paired seeds per arm on
932010–932017 over c={0, 5, 9.9, 12.5, 18.5, 25, 35, 50}; c=0 failed semantic
action resolution after six rows, c=5 and c=9.9 were strongly negative on the
small screen, c=35 was slower than the intended envelope, and c=18.5 was the
most promising lower value in that screen.

The follow-up narrow screen used fresh paired seeds 932100–932131, 32 per arm,
at c={12.5, 15, 18.5, 21, 25-control}. Relative to control, point win deltas
were -6.2pp, -6.2pp, +6.2pp, and +6.2pp. The paired 95% intervals for the two
positive point estimates were [-9.4,+21.9]pp and [-9.4,+25.0]pp, so both
include zero. All complete arms had exact seed sets and root-budget multiples,
zero recorded search failure counters, and no leaf-VNet calls. The official
canary helper was omitted because it does not accept the required
`reuse-cap=none`; equivalent manual checks are documented.

This is an online inconclusive result, not evidence that the offline gate was
wrong and not evidence that Sequential Halving is useful. A future promotion
would require a new preregistered confirmation, with ordinary c=25, the frozen
root-only candidate, and a reimplemented Sequential Halving arm.

## Artifacts

- [Online GCP evidence packet](../../experiments/evidence/silver-root-exploration-online-gcp-2026-08-29.json)
- [Offline §193 decision](2026-08-29-silver-root-exploration.md)
- Ledger-06 §194

Implementation SHA: `1a96164ed7f6bb3d5ceb66e087d16f3845bc40e4`.
Baseline full `origin/main` SHA: `034830df6510f1ab37ad4f053c07333fca0970c7`.
