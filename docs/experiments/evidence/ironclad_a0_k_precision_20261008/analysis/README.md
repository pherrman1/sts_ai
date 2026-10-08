# Fixed K4/K16 analysis

This directory implements the separate selection and evaluation stages in
[`../PROTOCOL.md`](../PROTOCOL.md). It never launches games or trains models.
The coordinator freezes the analysis source, imported helpers, actual Python
and NumPy runtime, and protocol before collection. These tools do not inspect
the prior RemoveLow confirmation or historical TEST data.

`analyze_k_precision.py runtime` prints the exact runtime identity for the
coordinator's freeze. Selection accepts `--freeze`, `--freeze-sha`,
`--contract`, `--contract-sha` and an exclusive `--output` path. Evaluation
accepts the independently recorded `--choices`, `--choices-sha` and a distinct
exclusive `--output`. Output paths must stay inside this analysis directory.

The contract must pass for all 32 allocated sources and all retained branches.
The analyzer rehashes all 256 producer/invocation artifacts and checks the exact
source, binary, teacher, policy, model, verifier, health-helper and analysis
bindings. Canonical valid no-state sources remain in the allocation. Missing,
invalid, duplicate, changed or unallocated data block inference.

The CSV reader necessarily tokenizes each row to locate `k`, but interprets
efficacy fields only for its stage. Selection uses k0..15, scoring K4 on k0..3
and K16 on k0..15. It writes both choices, every selection score, state
identities and input hashes. The contract validator may check all label
domains and validity without ranking or reporting future win counts.
Evaluation first checks the expected choice hash and every frozen input, then
interprets k16..31. It does not rank options or revisit either selector.
Synthetic poison values in the other stage establish this semantic boundary;
this is not a claim that the other bytes were never hashed or CSV-tokenized.

An exact selection maximum tie favors the captured source-policy choice;
remaining ties use semantic-key lexicographic order. Each exposed source has
one retained `BOSS_RELIC` state at most. Its paired evaluation mean is the
average of sixteen K16-choice minus K4-choice final-win differences. A valid
no-state source contributes zero. The primary mean and percentile interval use
all 32 source clusters, 10,000 whole-source bootstrap replicates and NumPy RNG
20261008 through the unchanged repository helper. No-state sources are not
treated as sixteen artificial successes or failures.

The sole primary classification uses the strict sign of that interval. A
positive lower bound supports local K16 selection gain; a negative upper bound
supports local harm; otherwise the result is inconclusive. There is no
population two-percentage-point threshold. Both comparisons with the actual
source-policy choice are descriptive, and cannot create another decision rule.
Same choices and a zero empirical interval do not establish equivalence.

The result remains conditional on these retained states, this teacher and this
sampler. The sampler retains latent counters and pool membership and is not an
exact posterior over player-visible histories. Sibling futures share a source;
thousands of branches are not thousands of independent sources. Tree-profile
membership and strict health do not provide individual branch-ID coverage.

Focused synthetic checks are in `test_k_precision.py`: nested/disjoint splits,
baseline/semantic ties, differing selectors followed by an independently
reversed evaluation, poison-stage isolation, missing/duplicate/invalid rows,
future/MAP joins, all-source and canonical no-state coverage, deterministic
whole-source bootstrap, strict zero-bound classification, and hash failures
that precede efficacy readers. They use only temporary synthetic tables in
this directory; no game or collection output is opened.
