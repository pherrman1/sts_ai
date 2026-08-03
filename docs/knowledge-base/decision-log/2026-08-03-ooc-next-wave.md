# 2026-08-03 — OOC next-wave: V4 full-gate headline, margin/256-block, mixture, beam negative, Phase-B neutrals

Date: 2026-08-03
Session/task: Execute the next-wave contracts
(`docs/knowledge-base/architecture/ooc-next-wave-contracts.md`): A0/A1
benchmark protocol, A2 label mixture, Phase E shop beam (B1) + C_ψ C++ loader
(B2a) + hidden-info audit (B3), and Phase B encoders (C1 transformer, C4
quantiles, C2 cross-attention).

## Decisions / findings

1. **V4 token net × full 7-gate stack is the strongest deployed config:
   41.4% (+20.3pp @ m1, CI [+10.2,+30.5])** — above the V3 full stack (39.8%,
   §76). §75's weak V4 result was a gate-coverage artifact. Cost: the tok net
   is ~3.5× slower per run (27 vs 8 cpu-sec/run). **V3 remains the default
   (V4 opt-in), but the V4 full-stack config is now the top measured arm.**
2. **Margin 1.0 is the operating point** (sweep 1.5/2.0/3.0 monotone decline:
   37.5/32.8/27.3%; 5.0 dead). **256-seed secondary block confirms the
   headline: +14.1pp (CI [+7.8,+20.7])**.
3. **K=1+K=3 joint labels: +15.6pp, below K=3-only (+18.8pp)** — the mixture
   dilutes the K=3 margin signal; K=3 labels stay the contract. Multi-
   truncation closed.
4. **Shop beam search is a clear negative** (beam-only −9.4pp significant,
   beam+full-stack +5.5pp vs the gate stack's +18.8pp). First version scored
   leaves with the SHOP head regardless of successor screen (fixed to the
   node's actual screen per the V2 convention — both versions benchmarked).
   Root cause: the per-screen VALUE head's successor-state scoring is a weak
   leaf signal (vs the direct Q head the gates use). Beam stays opt-in;
   **the one-ply shop gate remains the shop lever**.
5. **Phase B encoders are neutral on the token state**: deck 2-layer
   transformer (C1: Q MAE 16.62 vs 17.00), quantile value heads (C4: Q top-1
   0.296 best-ever ranking, Q MAE 16.76), candidate–deck cross-attention (C2:
   in progress). Combined with §77/§80, **the token-state Q calibration gap
   is not attention capacity, matchup info, or Q-head shape — it is the
   counted-token state contract itself**. The V4 net's deployed win comes
   from gate ranking, not held-out Q calibration.
6. **C_ψ export bug fixed**: the `combat_cpsi_v1` writer omitted the
   relic/potion/encounter projection weights (artifact could not reproduce
   the model, |ΔP(death)| up to 0.99); writer fixed + re-exported, C++ loader
   (`CombatCpsiNet`, B2a) cross-checks at 2.4e-06.
7. **Hidden-information audit (B3)**: the one-ply gates and Searcher3 fair
   machinery are clean; the strategic datagen counterfactual branches and the
   rich-row future-encounter features (`nextFight0..2`/`nextEliteId`/`bossId`)
   are flagged leaks vs spec §A.14 (the model sees exact future encounters).
   **Open question: whether to scrub the future-encounter features** — they
   are load-bearing in the current training contract; removing them is a
   retraining round with an uncertain deployed trade.
8. **Config-audit lesson**: two verification runs in this wave were initially
   run without `STS_FAIR=1` (known-RNG Searcher2 diverges from the recorded
   fair baseline) and were discarded before analysis — AGENTS.md trap
   re-confirmed; the fair reruns are the recorded numbers.

## Evidence

EXPERIMENTS.md §81 (V4 full gates), §82 (margin + 256 block), §83 (mixture),
§85 (beam), §86 (C1), §87 (C4); artifacts in `build/` (r6_gate_m1.5..3.0,
sec256_*, v4full_gate_*, mix_gate_m1, beam_*), `selfplay/models/`
(ooc_strategic_v3_mix, ooc_strategic_tok_{transformer,quants,cross});
`src/sim/search/CombatCpsiNet.*`, `include/sim/search/CombatCpsiNet.h`;
decision-log 2026-08-02-hidden-info-audit.md, 2026-08-03-b1-shop-beam.md.

## Status and follow-up

A0/A1/A2/§84/§85/§86/§87/§88 recorded. A3 (STRATEGIC_BRANCH_FUTURES=3)
delivered (§84): +13.3pp gate — below futures=1's +18.8pp; the
label-contract space {K1,K3}×{futures1,futures3} is closed, K=3×futures=1
is optimal (better label calibration does not transfer to the gate). Follow-ups: (1) V4 full-stack as the candidate for
a default flip once the 256-block includes it; (2) C_ψ-loaded map route
search (B2) — the loader is ready, the shop-beam lesson says leaf-value
choice matters; (3) future-encounter feature scrub decision (B3 finding);
(4) the Q-contract re-test on the V4 base is exhausted — further token-state
work should target the label contract or deployment, not encoders.
