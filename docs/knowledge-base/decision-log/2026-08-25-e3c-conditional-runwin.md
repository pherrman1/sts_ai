# 2026-08-25 — E3c conditional E2c critic

Date: 2026-08-25  
Task: Isolate the conditional post-combat E2c critic from combat-survival
estimation using the frozen E3a M=16 shadow/reference artifacts.

## Decision

Classify the offline result as **E3C_INCONCLUSIVE**. Do not promote the
conditional E2c critic, any conservative risk summary, CVaR-like statistic, or
distributional model to gameplay. Do not regenerate the frozen data, run M=32,
train a model, or tune a threshold/lambda from this result.

## Rationale

At `survivedCount >= 1`, the conditional critic's root-equal downstream event
accuracy was `0.508568`, versus `0.523472` for `blendedEval`, for a delta of
`-0.014904`. The deterministic 10,000-draw source-seed bootstrap 95% CI was
`[-0.085624, +0.056238]`. Leave-one-source-seed-out estimates ranged from
`-0.036925` to `+0.008089`, changing sign. Higher support restrictions had
positive point deltas (`+0.022183`, `+0.029394`, `+0.014489`) but every 95%
CI still included zero and every leave-one-seed-out range still included zero.

This is **Inference**, not causal proof: the evidence does not establish a
useful conditional critic signal, and the source-seed instability prevents a
stable E3C_CONDITIONAL_SIGNAL label. The predeclared conditional risk
summaries also showed no robust downstream advantage. The current R=4 vectors
mainly probe aleatoric combat/policy RNG conditional on one copied world; they
are not information-set CVaR over hidden worlds, strategic returns, or model
uncertainty.

## Alternatives considered

- **E3C_CONDITIONAL_SIGNAL** — rejected because the conditional mean's CI
  includes zero and its leave-one-seed-out estimates change sign.
- **E3C_RISK_SIGNAL_ONLY** — rejected because none of the predeclared
  conditional min, worst-half, mean-minus-0.5-std, or mean-minus-1.0-std
  summaries has both a positive CI lower bound and all-positive leave-one-seed
  estimates.
- **Gameplay risk/CVaR integration** — rejected because four samples are too
  coarse for reliable population CVaR and the raw Bernoulli tail is often
  degenerate.
- **Immediate distributional-model training** — rejected because current data
  do not separate target mismatch, omitted features, hidden-world mismatch,
  objective weakness, capacity, and absence of signal; richer targets and
  hidden-world particles are an **Open question** for a future confirmatory
  study.

## Evidence

- `tools/analyze_e3c_conditional_runwin.py`: reconstructs `z_r` and surviving
  `c_r`, validates R=4 and same-world CRN identity, computes root-equal/source-
  seed-bootstrap ranking and risk summaries, and contains the required
  self-tests.
- `build/e3c_conditional_runwin_analysis.json` and
  `build/e3c_conditional_runwin_analysis.md`: generated twice with
  `python tools/analyze_e3c_conditional_runwin.py --bootstrap 10000`; repeated
  SHA-256 values are JSON
  `260ffb78119f3539a59a92c2c5a658f81c87947c2be1a2180196488399ad1872` and
  Markdown
  `86c8136477a5d3bc668d58c11aa03f5cb6156f70111bb6d20c48e276cce0dc1b`.
- Frozen shadow CSV SHA-256:
  `0aca56931c24575aca468d21e4da0848ea6b9296a36e724a93a6b8be5abf11ed`;
  frozen direct-reference CSV SHA-256:
  `a6a18d314e0f4d040b03a84b0cd073146375f79babfe7c1994614114fdc68671`;
  producer SHA: `a93b3c68fc4efaaf9e9858d7aca571baac1a68d4`.
- Coverage: 188 complete leaves, 463 sibling pairs, 32 roots, 16 source
  seeds, 1,143 direct outcome-discordant events, 273 combat-driven events,
  and 870 downstream-discordant events before conditional-support filtering.
- Verification: `git diff --check`, `python -m py_compile
  tools/analyze_e3c_conditional_runwin.py`, and
  `python tools/analyze_e3c_conditional_runwin.py --self-test` passed.

## Status and follow-up

Implementation and offline analysis are complete. Raw published artifacts,
`tools/analyze_runwin_rank.py`, `tools/analyze_e3b_paired_discordance.py`,
E2c, gameplay/search code, and model training remain unchanged. The next
scientific step, if independently justified, is a confirmatory offline design
with a richer return target and explicit hidden-world particles while retaining
the same root-equal/source-seed protocol. Do not train or integrate a
distributional evaluator from these R=4 samples alone.
