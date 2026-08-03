# 2026-08-02 — Phase 5 round 5: token-based run state (V4) delivered; deployed gate weaker than V3

Date: 2026-08-02
Session/task: Phase-A continuation (plan A1–A4): replace the flat 1017-vector
state of the OOC strategic net with a token-based run state, evaluate with a
held-out ablation ladder, then a paired 128-seed gate benchmark.

## Decision

Built and recorded the V4 token-state pipeline (contract
`docs/knowledge-base/architecture/ooc-strategic-v4.md`): 50 globals (44 rich
scalars + 6 derived thresholds hpFrac/missingHp/freePotionSlot/goldGeRemoval/
canTakeEliteKey/bossNear), counted deck tokens `(cardId, upgraded, count)`
through a 1-layer single-head self-attention, relic `(id, counter)` and potion
`(id, count)` mean-pooled token encoders, and a candidate entity embedding
(sharing the card/relic/potion tables) in the action encoder. **No new datagen**
— everything derives from the existing §73 `strategic_tierb.csv`. New files:
`train_strategic_tok.py` (rung-masked trainer), `export_strategic_tok.py`
(`OOC_STRAT_V4`), `strategic_tok_net.py` (shared module), `apps/ooc_strategic_tok_net.h`
(native forward), plus `apps/one_combat.cpp` wiring (`STS_OOC_STRATEGIC_TOK_NN`;
the four §74 gates prefer the token net; parity hook `STS_OOC_STRATEGIC_TOK_CHECK`).

Deployment decision: **V3 stays the default; the V4 net is opt-in.** The paired
gate (fair, 128 seeds, 1,000 sims) reached +3.1pp wins at margin 5.0 (24.2%,
CIs span zero) and floor/HP gains at every margin, but did not beat V3's +7.0pp
@ m1 (§74) on the same block. Rung ladder held-out metrics are better than V3
(pol top-1 0.793 vs 0.784, val CE 0.486) with the deck tokens carrying the
held-out gain — but absolute Q/value calibration stays worse (Q MAE 16.2 vs
14.3, value MAE 10.2 vs 5.45).

## Rationale

- **Inference:** the full token pipeline (datagen-free) was the cheapest way to
  test the spec's token-state hypothesis A1–A4 on the existing Tier-B dataset;
  the ablation ladder attributes the held-out gains to deck tokens (value MAE
  25.8→13.0, Q MAE 27.1→17.4, logit margin 5.5→10.1), confirming the encoder
  works.
- **Inference:** the deployed-gate shortfall vs V3 plus the opposite margin-curve
  shape (V4 improves with margin, V3 peaked at 0.5–1.0) suggests the Q head
  calibration (not the state representation) is the deployment bottleneck — Q
  MAE 16.2 vs V3's 14.3. Follow-up isolates this by training a V4-architecture
  Q head on the V3 state.
- **Inference:** consistent with §61/§62 history — better encoders improved
  held-out prediction without a transferred deployed gain.
- **Verified:** export parity (numpy-vs-PyTorch logit 1.05e-05), native
  cross-check (numpy-vs-C++ max |q| 2.41e-05), deployed globals bit-identical
  to `richRow` (TOK_CHECK 0 mismatches over 8 runs).

## Alternatives considered

- Adding threshold/event-cost columns via new strategicgen2 datagen — rejected:
  derivable in-trainer from existing columns; event option costs are NOT in the
  data (documented limitation, §2.1).
- Full 2–4-layer transformer deck encoder — deferred to Phase B (plan A.15
  split); the single-head attention kept native C++ simple and matched the
  contract.
- Reusing V3's normalized state.bin — rejected: thresholds need raw values;
  the tok trainer writes its own 482-col raw float16 file.
- Deploying the V4 net as the new default despite better held-out ranking —
  rejected: the paired gate is the decision metric and it did not beat V3.

## Evidence

- EXPERIMENTS.md §75 (ladder table, paired gate table, verdict); contract
  `docs/knowledge-base/architecture/ooc-strategic-v4.md`; artifacts
  `selfplay/models/ooc_strategic_tok_final.native` (sha256 `05178ec8…9e1ea`),
  `build/tok_gate_{m1,m05,m5}.csv`.

## Status and follow-up

Implemented and recorded. V3 stays deployed. Follow-ups: (1) V4-architecture Q
head on the V3 state to isolate Q calibration vs state representation;
(2) re-test tokens once Phase-C combat-outcome probes exist; (3) keep the
proven token pipeline as the Phase-B base (deck-set transformer, map DAG);
(4) the plan's Phase-A checklist items A1–A4 are delivered; item A5 (PPO/GAE)
remains open.
