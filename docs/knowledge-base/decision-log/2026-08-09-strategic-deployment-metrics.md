# 2026-08-09 — Deployment-aligned strategic metrics

Date: 2026-08-09
Session/task: Implement Wave 0D descriptive metrics before another strategic
training dataset.

## Decision

Add `strategic_metrics.py` as a training-independent metrics library and
`tools/analyze_strategic_metrics.py` as a strict consumer of prediction CSVs.
The input carries one row per decision with screen, gate margin/fire status,
model/fallback/best indices, and pipe-delimited predicted and labeled Q values.
The library reports gate-fire curves, override quality, fallback-relative
advantage, sign/correlation diagnostics, and model/fallback regret globally and
per screen.

## Rationale

**Inference:** policy CE, top-1, and Q regression errors are insufficiently
validated gameplay proxies. These metrics mirror the deployed fallback-gated
decision and can be run on existing checkpoint/dataset prediction outputs
without retraining.

## Evidence

- `strategic_metrics.py::analyze_decisions` and
  `tools/analyze_strategic_metrics.py::selftest` pass on synthetic decisions.
- `python3 tools/analyze_strategic_metrics.py --self-test` passed.
- Existing trace analysis remains separate because the runtime trace does not
  contain counterfactual labels and therefore cannot claim beneficial/harmful
  override rates.

## Status

Implemented. A future checkpoint evaluator must emit the documented prediction
CSV to connect these metrics to real labeled decisions.
