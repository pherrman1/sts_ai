# Silver terminal/value audit — bounded development result

This packet tests whether changing only terminal scoring can improve the
ranking of fixed 32-replicate SimpleAgent continuation trajectories against
the existing Silver Teacher A/B labels. Teacher A/B are treated as Silver
search objectives, not as an independent claim about the true game utility.

## Scope and provenance

The implementation base is `43ef6a6d` (current `main` after PR #260). The
replay used the preserved 20-source, 247-leaf corpus from
`silver_rollout_variance_20260920`, with 32 deterministic paired continuations
per leaf: 7,904/7,904 accepted rows. The native binary was rebuilt from this
checkout; the stored leaf corpus retains its original capture provenance.

The former #260 40-source expansion and 40-source locked artifacts contain
prefix feature rows but not replayable leaf wires. They are therefore not
silently promoted into this audit's 100-source development corpus, and no
fresh 40-source holdout was opened. This packet is a bounded development
result, not external validation.

## Native parity

For every accepted rollout, the raw leaf-root feature reconstruction matched
the production `BattleSearcher::evaluateEndState()` value within `1e-8`.
The original-root teacher value retains the existing separate victory
baseline-correction contract; the analyzer models that correction explicitly
when fitting.

## Result

| arm | Teacher-A regret | pairwise concordance | top-leaf agreement |
| --- | ---: | ---: | ---: |
| `DEFAULT_CURRENT` | 1.51332 | 0.74241 | 0.56250 |
| cross-fitted `REWEIGHT_COMPAT_V1` | 1.71113 | 0.74292 | 0.53125 |
| cross-fitted untied diagnostic | 1.61666 | 0.74346 | 0.53125 |

The compatible fit failed the preregistered 15% development improvement gate;
its source-clustered baseline-minus-candidate bootstrap interval was
`[-0.46891, 0.00000]`. Teacher B also worsened (`1.47290 -> 1.82242` for the
compatible arm), so this is classified:

```text
TERMINAL_REWEIGHT_HEADROOM_INSUFFICIENT
```

The untied diagnostic now uses nested source-grouped lambda selection inside
each training partition, as required by the preregistered contract. Its fold
lambdas were `[1.0, 0.1, 0.01, 0.01, 0.01]`; the full development fit selected
`1.0`. It did not provide positive headroom either, so the
`TERMINAL_FORM_TOO_RESTRICTIVE` branch is not supported by this corpus.

The source-clustered bootstrap now clones each sampled source occurrence with
unique group and leaf identities before recomputing metrics. This preserves
duplicate source draws as duplicate bootstrap weight rather than collapsing
them back into one sibling group.

Using zero sibling regret as an optimistic ceiling, the cross-fitted compatible
arm recovered `-13.07%` of the available baseline gap: its regret increased
from `1.51332` to `1.71113`. The fitted development-only weights also retain
ordinary-loss/victory overlap (48 of 75 loss leaves at or above the minimum
victory value), so this fit is not a deployment candidate. The preserved
corpus omits act, HP-band, and source-rollout-length metadata; those subgroup
diagnostics are recorded as unavailable rather than inferred.

## Interpretation and boundary

On this preserved development corpus, reweighting the current terminal
components while keeping every SimpleAgent trajectory fixed did not recover
the rollout-vs-deep-Silver sibling gap. The bounded conclusion is that
terminal scoring is not the leading explanation in this sample; the next
research target should be continuation trajectory/policy quality.

This does not qualify a production default, does not validate a fresh holdout,
does not run hard64 replay, and does not establish a true game-objective
interpretation of Teacher A/B.

## Files and hashes

- `dev-terminal-features.jsonl.gz` — 7,904 per-continuation raw feature rows.
- `dev-analysis.json` — deterministic component audit (including Teacher-B
  residual correlations), ablations with source-clustered bootstrap intervals,
  grouped fit, cross-fit metrics, gap-recovery calculation, and cross-outcome
  ordering sanity check.
- `terminal-feature-schema.json` — raw feature and reroot semantics.
- `preregistered-seeds.json` — source, split, regularization, and bootstrap
  contract.

```text
dev-terminal-features.jsonl.gz  sha256=2a1899cab6a3708504ec408486e9fd10b23938ef07ea6534230fd2527cd4bd3f
dev-analysis.json               sha256=62d882765ddbaf01070fdbf74e819aab7f4d363959af606fdc3dd6667d0fe55c
```

Knowledge impact: durable bounded negative terminal-scoring result and the
raw-feature diagnostic contract are recorded in
`docs/knowledge-base/evaluation/current-research.md`; this packet is the
compact evidence artifact.
