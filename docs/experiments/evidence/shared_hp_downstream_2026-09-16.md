# Shared maxHP+HP representation for native downstream consumers

**Decision: `SHARED_HP_DOWNSTREAM_FAIL`.** The already-qualified PR #197
shared maxHP+HP representation was substituted only at downstream consumers
that currently receive the dedicated HP representation. The survival, potion,
all downstream heads, support predicates, trace construction, legality masks,
and targets remained frozen.

## Result

The actual current `main` was `27c8f7a0918b6ac684a3913436e30c54c0f5ff6c`, a
descendant of the handoff's expected `c371f3c2`. The exact PR #197 epoch-37
checkpoint was verified at SHA256
`daf50b5ec0847fe7a44cde0efd5d592a1939a25e6978f6757dd2b0157a105267`; its
receipt SHA256 is `4149c038a2abe9ab181b03c714763e74fb7b37f534020179004696fd465577c7`
and its recorded decision is `SHARED_TRANSITION_ENCODER_GO`.

The existing `tools/combat_transition_near_full_downstream.py::losses`
evaluator was used on the eligible source-grouped VALIDATION cohort: 17,950
rows (the underlying final-union source population has 48,590 winning
VALIDATION rows from 2,496 sources). No TEST rows were inferred.

| Consumer | Reference NLL | Candidate NLL | Candidate minus reference | Relevant accuracy change |
| --- | ---: | ---: | ---: | ---: |
| turns | 1.234442 | 1.253996 | +1.5841% | exact-label −2.6428 pp |
| attacks | 2.181673 | 2.247821 | +3.0320% | exact-label −1.3663 pp |
| cards | 2.312144 | 2.320320 | +0.3536% | exact-label +0.6309 pp |
| shuffles | 0.875158 | 0.975965 | **+11.5188%** | **exact-label −6.0533 pp** |
| Writhing | 0.584366 | 0.578046 | −1.0815% | — |
| Ritual | 0.070339 | 0.084861 | **+20.6457%** | — |
| gold | 0.586938 | 0.731526 | **+24.6343%** | — |
| joint downstream | 1.364212 | 1.448260 | **+6.1609%** | — |

All outputs were finite and legal, but the joint principal NLL exceeds the
2% limit. Turns, attacks, and shuffles also exceed the −0.5 percentage-point
accuracy limit, while shuffles, Ritual, and gold exceed the +5% important-slice
NLL limit.

## Stop decision

Stage A clearly fails, so the native 3-encoder path was not implemented or
timed. The current four-encoder runtime, artifact, downstream models, and
defaults remain unchanged. There was no TEST inference, C++ change, runtime
correctness comparison, preparation benchmark, OOC timing profile, gameplay
evaluation, or promotion. This rejects this exact frozen shared-representation
substitution for downstream consumers; it does not establish that every
possible jointly trained shared representation is impossible.

Knowledge impact: current research status and experiment evidence only;
qualified components and executable defaults are unchanged.

[Machine-readable receipt](shared_hp_downstream_2026-09-16.json).
