# 2026-08-25 — E3b paired-discordant-future leaf ranking

Date: 2026-08-25  
Task: Exploratory paired-discordant-future analysis of E2c leaf ranking on the frozen E3a M=16 artifacts.

## Decision

Classify the result as **E3B_SURVIVAL_ONLY**. Do not promote E2c, change
gameplay/search code, reinterpret the failed E3a reference gate, or spend more
compute automatically. If this line is revisited, the independently motivated
follow-up should test a simpler survival-aware leaf value or a new
preregistered target.

## Rationale

The primary root-equal informative-event delta was `runwin_mean - blendedEval`
`+0.010050` overall, with source-seed bootstrap 95% CI
`[-0.048640, +0.074638]`. The positive point direction was concentrated in
combat-driven discordance (`+0.040679`) and disappeared in the
downstream-discordant stratum: `runwin_mean - blendedEval` was `-0.018730`,
while `runwin_mean - diagnostic_survival_rate` was `-0.029889`.

This is **Inference**, not causal proof: the result is consistent with the
run-win score adding mostly current-combat survival information, not an
incremental post-combat strategic critic signal. The downstream bootstrap CIs
include zero, so the result is not a confirmatory effect estimate.

The estimand remains target-mismatched by construction. `V_direct` is a
same-world conditional outcome under a copied latent `GameContext` future;
E2c, blendedEval, and VNet do not observe that exact downstream future. The
analysis therefore asks which static score predicts the winner of a paired
realized-world continuation when the siblings differ, not which score perfectly
estimates information-set expected run value.

## Alternatives considered

- **E3B_STRONG_SIGNAL** — rejected because the downstream treatment did not
  beat either blendedEval or the survival ablation, and neither downstream
  bootstrap CI was above zero.
- **Gameplay promotion of E2c** — rejected because this is post-hoc exploratory
  evidence and the primary downstream comparison is negative at the point
  estimate.
- **Automatic larger sweep or M=32 extension** — rejected because the
  prespecified guidance says not to spend more compute after a survival-only
  result without an independently motivated target.

## Evidence

- `tools/analyze_e3b_paired_discordance.py` validates the exact frozen
  `LEAF_IDENTITY`/`ROOT_IDENTITY`, R=4 shadow collapse, complete M=16 futures,
  valid reference rows, and sibling CRN seed equality; its self-test passed.
- `build/e3b_paired_discordance_analysis.json` and
  `build/e3b_paired_discordance_analysis.md` were generated twice with:
  `python tools/analyze_e3b_paired_discordance.py --bootstrap 10000`.
- Coverage: 16 source seeds, 32 roots, 463 sibling pairs, 7,408 pair/future
  slots, 1,143 informative events, 273 combat-driven events, 870 downstream
  events, 22 roots with informative events, and 10 zero-information roots.
- Frozen input SHA-256: shadow CSV
  `0aca56931c24575aca468d21e4da0848ea6b9296a36e724a93a6b8be5abf11ed`;
  reference CSV
  `a6a18d314e0f4d040b03a84b0cd073146375f79babfe7c1994614114fdc68671`;
  published M=16 bundle
  `2ed208e0abfc39bf3686742c7c3ec140e33c58cf5204406f65ed834ae8ff4e1f`.
- Repeated-output SHA-256: JSON
  `9b35d13c7bcd8f13d5925a6402b282c9d9700ccd098fe006c0b3665bcf71f98f`;
  Markdown
  `2945d81114a9fd23a977171dc9e32a59ce553a000f7c8b14739fe9f3be40950b`.
- Verification: `python -m py_compile` passed, `--self-test` passed, and
  `git diff --check` passed. Independent implementation review found no
  blocking correctness or scope issue.

## Status and follow-up

Implementation and exploratory analysis complete. Raw published artifacts,
`runwinrank`, `analyze_runwin_rank.py`, E2c, gameplay/search code, and E3a
thresholds remain unchanged. No confirmatory experiment is authorized by this
record.
