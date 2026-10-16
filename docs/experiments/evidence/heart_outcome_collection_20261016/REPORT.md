# Observed Heart-outcome collector qualification

Status: **local collector qualification PASS**, including independent source/design
and completion-anchored canary review. Cloud collection is prepared, not dispatched. No model fitting,
TEST opening, native value-head integration, gameplay comparison or promotion.

Frozen producer source `7527b5d5d07467688101212660461995665512b9`, base
`9129e5b850ba45114820956522cbc92c238c2afe`. Later evidence/documentation commits
must not be substituted silently for the frozen producer. Original Arm C native
SHA256 `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509`.
Local binary `178e7076934097987e473ab04c2dc80eec5368f9dcb12b274a631bad62f43e4e`;
plan `f52f7548d3d814293f666e789eeb29ddb8c83c393551c6fa723f298264618a7f`;
bundle manifest `47dbc4b849b2f98e1ed948c8542e416a7de68ba330307ba89e851eca3b98cbd0`.

## Checks and independent review

GCC 13.3 Release and Debug `one_combat` builds passed; Debug `unit-test` and
`run_goal_test` targets built. Focused Debug CTest 5/5 passed in 1.31 s: run goal,
native writer, Python collection checks, training integrity and MCTS adapter.
The 15 Python cases passed; existing seed-guard 5/5 also passed in 0.166 s.
The documented native synthetic `heart1score` command also passed on one
public fixture with finite scores; no game seed was used by that check.
Repository health and diff checks passed. Full core/smoke suite and GitHub
Linux GCC CI have not been run for this draft; these focused checks do not
claim a full CI-equivalent pass. An initial Release invocation of
`training_integrity` was Not Run because that target had not been built; the
required Debug targets were then built and the focused suite passed.

Independent `heart_review` source/design PASS at the exact frozen source:
Python 15/15 in 0.058 s, Release writer 1/1 in 0.12 s, clean source and diff check.
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

## Local canary results

The frozen runner completed once, return code 0, without retries. Independent
completion review **PASS** reverified all 24 original completion-anchored files,
all three receipts, the complete bundle/runtime, and tool bytes against source.

| Source | Capture | Wall seconds | Supported / observed states | Result |
| --- | --- | ---: | ---: | --- |
|110179994|OFF|435.421|0 / 0|healthy full-run loss at Heart, Act4/floor56|
|110179994|ON|426.028|219 / 219|same outcome and exact trace/action parity|
|110179995|ON|394.086|215 / 215|healthy full-run loss at Heart, Act4/floor56|

All 434 captured public records pass the existing schema and ordered actual-trace
alignment checks. The first source uses 19,826 scored Arm C priors and 345,471
rollout scores; the second uses 19,605 and 273,336. Each has 100% scoring coverage,
zero fallbacks and zero legacy prior leaves. Real trace parity SHA256 is
`4f872cc12249d39adaf8b064b780a5011b1dfb5fc476b0d4d9a70b19d9bc0b9d`;
MCTS action parity SHA256 is
`ad986024ccd3229b7dc5a62c507c199be4c122e2d77068cdee88abb3b6168750`.

Original [canary manifest](canary.json) SHA256:
`10b3ebacf49866f5cef1aa2791eca4f058fdfabcf7aa627a0a2dd04ae5f308aa`.
Separate [independent local review](canary-reviewed.json) SHA256:
`94409181283676a3cc9435bf077f5dc7f6d136d74de56083bbb79b8f8c92f684`.
Original completion hashes were not regenerated. The review is local-only and
cannot activate the cloud cohort. Both unique seeds were losses; no
Match-and-Keep event occurred. These canaries prove collection/parity on their
observed support, not Heart-win quality, full public/native parity, or a speed
improvement. Their wall times are descriptive only. Canaries remain excluded
from training.

## Interpretation and next boundary

This collector writes observed Heart outcomes only after a healthy whole run
finishes, for public states actually visited by the driver. It does not assign
the played outcome to MCTS alternatives. Inputs retain the existing unqualified
public-record parity status, and observation coverage is sampled driver
boundaries rather than every primitive action. Data collected under this fixed
teacher estimates its behavior-conditioned return, not optimal play strength.

Prepared capacity is 1,800 unique sources, TRAIN 1,080/VALIDATION 360/TEST 360,
45 workers × 4 single-threaded producers. Requested/prepared capacity is not observed
launch or completion. Cloud rebuild/canary review and a verified ≥256 MiB native
artifact export roundtrip must pass before the single six-hour activation.
All workers receive the same bundle and approved activation identity. Missing,
invalid, crashed or timed-out runs remain censored failures; no replacements.
TEST leaves workers only as separately sealed archives with custody receipts.

After delivery, independently audit import/sealing and TRAIN/VALIDATION class
coverage before proposing a frozen training protocol. Source-balanced outcome
learning can then target the value head; old rollout targets can remain warm
start/auxiliary data. No value accuracy, speed, gameplay or RL-loop verdict is
claimed here. Prior §491–496 verdicts remain unchanged.
