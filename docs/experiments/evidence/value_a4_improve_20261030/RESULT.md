# Improve V_A4: result (2026-10-30)

## Correction to §720: GC uses post-entry information
GC's CTM feature is the CTM at the **S&S elite row**, i.e. after the Act-4 rest site and shop: the S&S deck differs
from the entry deck in 79% of run-1 entries (shop buys/removes, smith). GC is therefore not a function of the entry
record and cannot be a drop-in V_A4. The CTM evaluated **on the entry record** (`core.ctm_entry_feats`) works as well
(CV: GCe −0.021 [−0.033, −0.010] vs G; leaked GCss −0.023 [−0.035, −0.011]). §720's PASS stands with G alone
(TEST 0.529 vs CTM_recal 0.589); stage 5 uses G.

## Main result (CV on the dev pool, [`logs/cmp_g.log`](logs/cmp_g.log))
| dev core (5-fold × 3, by seed) | BCE | R² all | R² run-1 entries | vs G (BCE) |
|---|---|---|---|---|
| G (§720 record-only GBM) | 0.541 | 0.197 | 0.169 | — |
| GBM + entry-CTM + deck aggregates, core data | 0.516 | 0.242 | 0.216 | −0.026 [−0.038, −0.014] |
| ensemble GBM + L2-LR, core data | 0.503 | 0.264 | 0.242 | −0.038 [−0.049, −0.026] |
| GBM, all data | 0.502 | 0.264 | 0.237 | −0.040 [−0.053, −0.026] |
| **ensemble GBM + L2-LR, all data (ENS_all)** | **0.491** | **0.283** | **0.260** | **−0.050 [−0.064, −0.037]** |

Ceiling (true p, from the within-entry variance of the 5 run-1 outcomes) on the 406 dev run-1 entries: R² 0.43.
ENS_all reaches 0.26 (61%), G 0.17 (40%). OOF deciles are calibrated within a few pp (one decile 0.43 vs 0.51,
[`logs/oldtest_check.log`](logs/oldtest_check.log)).

## What helps, what does not (paired CV)
- **More data**: learning curve on core data, GBM 25/50/75/100% of seeds 0.538 / 0.528 / 0.523 / 0.516
  ([`exp3`](logs/exp3.log)); adding the 4,480 older (not Act-4-strong) entries with a source flag: GBM −0.013
  [−0.020, −0.006], ensemble −0.012 [−0.018, −0.005] ([`exp5`](logs/exp5.log), [`exp6`](logs/exp6.log)).
- **Ensemble GBM + LR**: −0.011 to −0.012 vs either member, at every data size.
- **No effect** (all within ±0.005, CIs include 0 or hurt): depth 1-4, eta, colsample, min_child_weight, lambda,
  monotone constraints on HP/CTM ([`exp1`](logs/exp1.log), [`exp2`](logs/exp2.log)); campaign one-hot; relic-counter
  phases (Incense Burner, Pen Nib, Nunchaku, Ink Bottle, Happy Flower, Sundial) + Ritual Dagger / Searing Blow state
  −0.0001 [−0.0019, +0.0017] ([`exp8`](logs/exp8_counters.log)); kept in the model anyway (no cost, needed for future
  decisions); down-weighting stage-2 data or training on run 1 only (worse).
- **Worse**: sklearn MLPs +0.014 and more ([`exp4`](logs/exp4.log)); heart1-like typed tokens
  (`tools/heart_record_encoder.py`) + transformer + attention pooling, from scratch: +0.011 vs GBM, +0.022 vs
  ENS_all, neutral as a third ensemble member ([`exp7`](logs/exp7_attn.log)); augmenting with later Act-4 states of
  the same games: +0.002 / +0.006 ([`exp6`](logs/exp6.log)).

## Old TEST (already read; secondary, [`logs/oldtest_check.log`](logs/oldtest_check.log))
Trained on the whole dev pool (early stop on seed % 4 == 2), 130 run-1 TEST entries / 650 games: ENS_all (with
counters) BCE 0.519, R² 0.27; GBM core 0.531; §720 G 0.529, GC 0.532. ENS_all − GBM core −0.012 [−0.035, +0.011]:
same direction as CV, TEST too small to show it alone.

## Drop-in model ([`tools/va4_model.py`](tools/va4_model.py), [`model/`](model/))
`va4_model.load().predict(states)` on Act-4 entry state rows (`{'act', 'floor', 'record'}`), public record only.
Mean of the GBM (1,285 rounds) and the LR (C = 0.003), trained by `fit_va4.py` on all 5,484 entries with
seed % 4 != 3 (7,108 games); stage 5's TEST seeds stay out. Source flags are set to today's default (run1 = 1,
strong = 1). Selftest: predictions from raw records equal the training matrix (max |Δ| 6e-17). sha256 va4_gbm.ubj
4c346c1b…, va4_lr.json 06276b52….

## Not settled
- Gains are CV on the dev pool; no fresh holdout exists. A fresh check needs new Act-4 games.
- A pretrained encoder (heart1.pt) as features: probe requested on the PC (follow-up).

## heart1.pt encoder probe (Philipp 14:26Z; [`exp9`](logs/exp9_heart1_probe.log), [`exp9b`](logs/exp9b_combos.log))
The frozen heart1.pt (sha256 deaba59d…, silverbot 84ab3ea, dim 256, 4 layers, 8 heads) encoded the 7,353 entry
records on the PC (`tools/heart1_embed.py`, run via Remote Control; output `heart1_embed.npz` sha256 22a9bb4f… on the
data branch `claude/va4-heart1-probe-data` @ 46ab578f). Same CV; the probe arms were chosen after seeing CV (3 C values,
4 combinations), so their CV numbers are mildly optimistic.
- Decodability (ridge, seed-grouped CV): deck size R² 0.93, CTM survival logit 0.84, gold 0.81, HP fraction 0.52.
- **Linear probe on the 256-d pooled embedding alone** (LR, C = 0.01): BCE 0.490, R² 0.286, the same as ENS_rc (0.491;
  −0.001 [−0.013, +0.012]). heart1's own value head alone: 0.604 (poor at the Act-4 entry).
- Adding the embedding: ENS_rc + probe (1:1) −0.010 [−0.016, −0.004] vs ENS_rc, BCE 0.481, R² 0.302 (run-1 entries
  0.276 of 0.43); embedding as extra columns in GBM/LR −0.007 [−0.013, −0.000].
- Interpretation: heart1's encoder carries most of what V_A4 can learn from 7k entries; the gain from combining is
  small and needs torch + heart1.pt at scoring time (PC). Not in the drop-in model.

## heart1.pt fine-tune (Philipp 15:06Z; [`exp10`](logs/exp10_finetune_eval.log))
`tools/heart1_finetune.py` on the PC GPU (Remote Control; data branch `claude/va4-heart1-probe-data` @ 4a5475a; one
fix during the smoke, 45f7eec: top2 had also trained the input embeddings). Same folds (reps 0-2), new head on
[pooled, source flags], per-game BCE, early stop on the inner fold; frozen 14 min, top2 19 min, full 28 min.
| OOF, dev core | BCE | R² | vs linear probe (LR on frozen embedding) | ENS_rc + this (1:1) vs ENS_rc |
|---|---|---|---|---|
| frozen encoder, MLP head | 0.508 | 0.254 | +0.018 [+0.011, +0.026] | −0.004 [−0.011, +0.003] |
| top2 layers trained | 0.505 | 0.261 | +0.015 [+0.007, +0.022] | −0.006 [−0.013, +0.000] |
| full encoder trained | 0.499 | 0.272 | +0.009 [+0.001, +0.016] | −0.008 [−0.014, −0.002] |
| (linear probe, exp9) | 0.490 | 0.286 | — | −0.010 [−0.016, −0.004] |
Fine-tuning does not beat the plain linear probe on the frozen embedding at ~5.5k training entries; the best
combination stays ENS_rc + linear probe (BCE 0.481, R² 0.302).
