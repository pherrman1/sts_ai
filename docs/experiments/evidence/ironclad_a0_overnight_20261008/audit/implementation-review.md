# Independent implementation and canary review

Review date: 2026-10-08 Europe/Berlin. Source baseline a4b3df35; review is of
the campaign working diff before the coordinator's first implementation
freeze. Exact reviewed commit/binary hashes must be added to the launch
manifest after commit and build.

## Reviewer separation

The integrity specialist reviewed the strategy specialist's public native
OOC scorer and shop feature correction, the coordinator's glue/provenance
changes, and the learning specialist's GEN=2 protocol. The strategy
specialist separately reviewed integrity's final-boss binary-objective
implementation. Authors did not approve their own changes. The coordinator
serialized builds and test execution.

## Source review

**Public scorer: PASS.** Planner sampling excludes actual seed, RNG states,
and future encounter identities from its stable state hash. Only a copied
monster RNG and encounter suffix are changed. Native weak/strong/first-
strong and no-repeat generation remains conditional on the observed prefix.
Every candidate in one fallback decision receives the same sampled hidden
fields; prediction probabilities, rather than logistic margins, are averaged.
Unsupported acts and malformed counts fail closed. Source state/RNG are
preserved. No claim of an exact joint posterior is made.

**Native shop deck-size correction: PASS, pending repaired fixture.** The
opt-in changes exactly the defective bookkeeping: relics no longer count
as added cards and requested removal reduces the final candidate deckSize.
Other approximation choices remain as before. The baseline regression
fixture failed with `relic purchase incorrectly adds a card`, preserved in
`build/overnight-shop-baseline-fail.log`. This establishes the feature
contract defect; gameplay strength remains unknown.

**Coordinator glue: PASS.** Native floor/win fallback wrappers use the
public scorer, flags are validated at startup, scorer-use accounting is
thread-local and subtracted per run, and positive research settings enter
effectiveOocPolicySpecification. Exact teacher-policy equality therefore
binds fairness/repair settings; default-off JSON stays unchanged. The
existing stop_after_act parameter already binds the horizon. CMake wraps
the two fixed-fixture test executables through seed_guard.

**Final-boss binary objective: independently reviewed by strategy, PASS.**
Only A0 Act-3 boss with a verified Act-3 cutoff can receive victory=100 and
other endpoints=0. Requires exact-root budgets and no adaptive/learned-stop/
stop-trace mode. Non-flat per-combat budget override is rejected. Earlier
fights and unset-flag behavior retain the original evaluator. Removing loss
gradients can worsen search; this is the explicit mechanism under test.

Residual scope: STS_CARD_WIN's nativeWinCardPick and ACT_FIGHT_PROBE's raw
winNetPredict still consume raw rich features. They are disabled by the
controlled campaign profile and must not be enabled without additional
information-boundary work. Raw vStateWinNativeFeatures remains intentional
for sampled MCTS contexts; live MCTS is disabled in these arms.

## Executed evidence inspected

The coordinator ran the following; the reviewer read their raw log files:

- `build/overnight-terminal-test.log`: silver_searcher battles=24,
  searchWins=12, greedyWins=4, decisions=687, reroots=605;
  `silver_searcher PASS`, including the new final-boss terminal fixtures.
- `build/overnight-public-futures-test.log`: `PASS public native OOC futures`
  covering a hidden-sensitive legacy action sentinel, unset/zero equivalence,
  all four hidden fields across acts 1–3, actual seed and fourteen RNG state/
  counter perturbations, card/removal/heal/upgrade/shop decisions, logistic
  mixture calculation, empty suffixes, source fingerprints and invalid flags.

Original diagnostic canary receipts all completed with exit 0. Bprod's 300
tree rows contained only {0,250,500,1000,2000,4000,8000,10000} completed steps,
17 singleton skips, and no errors. Bflat's 348 tree rows each contained
exactly 10,000 completed steps, no singleton skips and no errors. Correct V4,
floor/win and backend load banners appeared. This is old-source diagnostic
mode evidence, not fair playing-strength qualification.

Before expensive waves: repaired shop fixture must pass; freeze reviewed
commit plus immutable binary/model/seed/config artifacts; run default-off
parity and enabled fair-scorer canaries; check scorer receipt >0 where
fallback scoring is expected; demonstrate final-boss startup rejection for
incompatible learned-stop/horizon settings. The repaired Bprod/Bflat wave
profiles must set STS_OOC_PUBLIC_FUTURES=8 explicitly.

## GEN=2 protocol review

**PASS for a contract/cost canary only**, four source seeds
610084000..610084003, two states per source at most, K=4, at most 192 branch
continuations plus four source runs, and 30 minutes wall per source process.
This is conditional on the reviewed fair source/binary/model/teacher freeze.
No 32-source expansion, training or confirmation run is approved by this
review.

GEN=2 redraws before the forced action and verifies the published screen
and all non-hidden rich features remain unchanged. Sibling future seeds
match. Require every source trajectoryValid=1 and zero source quarantines/
fatal counts; retain and reject incomplete/invalid/no-map branch outputs.
Save and hash decisions selected using k0/1 before reporting k2/3 outcome
comparisons. The chosen reference is the actual captured policy choice,
which need not be V4-owned. Four sources yield descriptive evidence only;
repeated futures remain clustered by source. Option-cap completeness is
only retained-set completeness, not all-legal-action coverage.

Knowledge impact: the feature defect and fair-information boundary belong
in maintained OOC/RNG documentation; experiment outcomes belong in the
ledger and current-research. No production-default change is qualified.
