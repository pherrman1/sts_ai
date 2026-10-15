# Issue #507: one-seed observational collector pilot

Frozen before launch, 2026-10-13. Producer source and complete environments,
commands, binary and selected artifact hashes are in `manifest.json`.

Hypothesis: enabling bounded leaf capture preserves the existing search and
records genuine input/target observations with correct provenance and validity.
Alternative explanations for discrepancies include observer mutation, incorrect
effective configuration, trace omissions, unsupported inputs, or stale artifacts.

Existing evidence inventory: the preserved §458 summaries have run outcomes and
support aggregates but no internal leaf pairs; its original remote raw archive
is not available locally. The §445 corpus has decision-root short-branch labels,
not this evaluator's internal leaves. CTM gate/transition corpora answer other
questions. Existing synthetic collector parity and startup tests establish
mechanism correctness, not execution with the selected A20 CTM. No holdout data
is opened, and no discovery pool is recollected for validation.

Run exactly one capture-off and one capture-on arm, sequentially, on historical
seed 87000000, ascension 20, bestbench 10,000 actual Silver simulations, one
worker, fair-play mode. Both use the reviewed Release binary and §458 CTM;
4096 OOC simulations, widening K=4/alpha=.75, three CTM combats, V4 prior and
continuation, public X2-B bootstrap, eight public futures, active Lizard enabled.
The CTM remains NOT_QUALIFIED. Reused historical seed is diagnostic, not holdout.

Pin shop deck-size fix=0, rollout shop=planner, and Silver loop guard=0 to retain
the named historical settings despite newer defaults. This is current-source
collector parity using the §458 CTM, not exact historical reproduction.
Both arms have the same profiling and decision/MCTS tracing. Only leaf capture
is added in the on arm; output paths necessarily differ. Every game command
runs through tools/seed_guard.sh. Limits: 900 CPU seconds and 1200 wall seconds
per arm, one worker, at most 1800 CPU seconds total; stop on failure or limit.
No seed substitution, automatic retry, extension, training, or deployment.

PASS requires both runs to complete successfully, expected runtime provenance
and backend metadata, and exact deterministic results and traces: results CSV,
MCTS CSV, action/support traces, decision traces and root profiles. Exclude only
CSV sec/mctsWallSec/mctsCpuSec and the six explicitly enumerated top-level
profile timing fields. Root actions, priors, visits, Q, work counts and search
checkpoints remain compared. Run the existing benchmark canary validator too.

Capture requires exact binary/source/CTM identity; at most 64 roots and eight
leaves/root at ordinals 1+k*512; consistent counts; finite [0,1] targets; binary
terminal targets; null failed targets; all aborted-root samples invalid; no
observer errors; at least one structurally valid sample. Report all input and
evaluation errors, aborts, actual horizons, acts, screens, boundary types,
terminal coverage, file sizes and descriptive timing overhead. Missing slices
do not imply a collector failure. The bounded prefix is not representative.

The analyzer is frozen alongside this protocol before launch. A failure is
preserved and diagnosed; it is not relabeled by relaxing the decision rule.
No inference about learnability, noise/stability, CTM quality, win-rate change,
public-input completeness or replayability follows from a collector PASS.
Next scientific prerequisite is one-family input completeness and exact
initial-state/RNG replay, before independent-future repeats or student fitting.
