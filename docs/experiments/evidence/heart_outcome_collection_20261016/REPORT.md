# Observed Heart-outcome collector qualification

Status: local canary running; cloud collection not dispatched. No model fitting,
TEST opening, native value-head integration, gameplay comparison or promotion.

Frozen producer source `7527b5d5d07467688101212660461995665512b9`, base
`9129e5b850ba45114820956522cbc92c238c2afe`. Later evidence/documentation commits
must not be substituted silently for the frozen producer. Original Arm C native
SHA256 `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`.
Local binary `178e7076934097987e473ab04c2dc80eec5368f9dcb12b274a631bad62f43e4e`;
plan `f52f7548d3d814293f666e789eeb29ddb8c83c393551c6fa723f298264618a7f`;
bundle manifest `47dbc4b849b2f98e1ed948c8542e416a7de68ba330307ba89e851eca3b98cbd0`.

## Checks and independent review

GCC13.3 Release and Debug `one_combat` builds passed; Debug `unit-test` and
`run_goal_test` targets built. Focused Debug CTest5/5 passed in1.31s: run goal,
native writer, Python collection checks, training integrity and MCTS adapter.
The15 Python cases passed; existing seed-guard5/5 also passed in0.166s.
Repository health and diff checks passed. Full core/smoke suite and GitHub
Linux GCC CI have not been run for this draft; these focused checks do not
claim a full CI-equivalent pass. An initial Release invocation of
`training_integrity` was Not Run because that target had not been built; the
required Debug targets were then built and the focused suite passed.

Independent `heart_review` source/design PASS at the exact frozen source:
Python15/15 in0.058s, Release writer1/1 in0.12s, clean source and diff check.
Four initial findings were fixed before freezing: approval verification at
worker launch, persistent semantic-failure receipts/archives, established Arm C
load/scoring contract, and full supported-record schema checks. Canary acceptance
is separate from this implementation/design PASS.

[Pre-canary verification snapshot](receipt.json) (its zero launched units refers
to that snapshot, before the three guarded canary units), [source review](source-reviewed.json),
[protocol](PROTOCOL.md), [Claude coordinator handoff](CLAUDE_HANDOFF.md).
Raw build/check logs, immutable model/producer bundle, plan and all canary files
are retained at local run root:
`/home/philippherrmann/Documents/sts/sts_lightspeed/build/heart-outcome-collection-20261016-v1`.

## Interpretation and next boundary

This collector writes observed Heart outcomes only after a healthy whole run
finishes, for public states actually visited by the driver. It does not assign
the played outcome to MCTS alternatives. Inputs retain the existing unqualified
public-record parity status, and observation coverage is sampled driver
boundaries rather than every primitive action. Data collected under this fixed
teacher estimates its behavior-conditioned return, not optimal play strength.

Prepared capacity is1,800 unique sources, TRAIN1080/VALIDATION360/TEST360,
45workers×4single-threaded producers. Requested/prepared capacity is not observed
launch or completion. Cloud rebuild/canary review and a verified≥256MiB native
artifact export roundtrip must pass before the single six-hour activation.
All workers receive the same bundle and approved activation identity. Missing,
invalid, crashed or timed-out runs remain censored failures; no replacements.
TEST leaves workers only as separately sealed archives with custody receipts.

After delivery, independently audit import/sealing and TRAIN/VALIDATION class
coverage before proposing a frozen training protocol. Source-balanced outcome
learning can then target the value head; old rollout targets can remain warm
start/auxiliary data. No value accuracy, speed, gameplay or RL-loop verdict is
claimed here. Prior §491–496 verdicts remain unchanged.
