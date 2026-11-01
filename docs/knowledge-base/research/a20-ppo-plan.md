# Our own A20 PPO run policy (heart1 recipe, improved): plan

Last verified: 2026-11-01 against main `53d591b` and `daniel-ziegler/sts_lightspeed` at `84ab3ea` (README,
`EXPERIMENT_LOG.md`, `run_heart1_supervised.sh` read, nothing executed). Research and design only: no gameplay
seeds were run for this page. Labels: **Measured** (cited ledger entry or artifact), **Inference** (reasoning here),
**External** (stated in the original repository, not reproduced by us unless noted).

## Purpose / research question

Philipp asked (2026-11-01) what it takes to train our own heart1-style PPO run policy, what we already have, what
is missing, and what should let it beat the original. This page refines roadmap phase 3 and experiment X2
([one-year roadmap](one-year-roadmap.md)).

## Current conclusion

1. **Train in our engine, not theirs.** X1 (§739) measured flat Silver 1,000 at 19.5 core-s per game with
   student_sel alone and found it VALID for ranking OOC policy changes. The original trained at Silver 1,000 too
   and cost ~12-35 core-s per game in its own engine (External). The 2026-10-25 pilot P0 in silverbot's engine
   (roadmap X2) is therefore superseded: it would measure in the wrong engine and still need a re-distillation.
2. **Compute is not the constraint.** A heart1-size policy adds ~70 calls × 30 ms ≈ 2 s per game (Inference), so
   1M A20 games cost ~6k core-h, about 2.5 days on 200 cores at 50% use. The original's whole run was ~1.1M games
   (Inference from its schedule: 2,575 iterations of 256, later 512 games).
3. **Missing pieces are plumbing:** sampled play with log-probs, a trajectory export, a PPO trainer for our record
   format, and an iteration loop. Two implementation PRs before a pilot.
4. **Cheapest decision gate:** a PC pilot (60 A20 iterations × 512 games from student_sel, ~31k games,
   ~170 core-h, ~14 h) and a 2,048-pair Silver-1,000 gate of policy alone (~23 core-h).

## Decision net (Philipp, 2026-11-01)

Constraints set by Philipp: **one net makes every OOC decision, no OOC MCTS for now, and every decision and every
public input must be covered.** This replaces the earlier "start from student_sel" choice below.

- **Architecture:** heart1-size (d256, 4 layers) extended with the student inputs (`x_act`, `x_deck_misc`,
  `x_relic_counter`) and the #941 v2 inputs through zero-initialised embeddings, so the extended net reproduces heart1
  exactly at the start (the original added ascension the same way). Without OOC MCTS the 30 ms forward costs ~2 s per
  game, so student_sel's speed no longer matters; d256 gives capacity and a trained value head. Learner on the PC GPU.
- **Start weights by a cheap pre-check G0:** heart1 alone vs student_sel alone in our engine, Silver 1,000, 2,048
  paired A20 seeds (~25 core-h). Not worse → start from heart1; clearly worse → distil student_sel into the d256
  architecture and start there.
- **Decisions the net does not make today** (`realOocChainStepBody`, `STS_OOC_MCTS=0`): keys (`heartKeyAction`
  runs before the net), potion discard (no token), Match and Keep, unmapped event options and unsupported screens
  (old chain), reward relics and gold (auto-taken), chest/relic rules after a declined step. Plan: tokens for all of
  them; gold stays automatic (no choice); keys pending Philipp's call.
- **Shared trunk (CTM thread, 2026-11-01):** CTM and value heads go on this d256 trunk as auxiliary heads; a separately
  trained fast CTM (DeepSets retrain on 378k real fights) stays for simulator use where speed matters (rollout3 calls it
  thousands of times per decision). The #941 x2_* embeddings are zero-initialised at any width.
- **Inputs the net does not see today:** shop prices, removal price and count, fought encounters (#941 v2), Wing
  Boots charges (#638); original heart1 also lacks act, deck misc and relic counters. Private state stays out.
- **S0 acceptance adds:** every decision logged with its source (net / rule / chain / automatic) and its full v2
  record; in smoke games the net makes 100% of real choices except gold, and every exception is listed with a reason.

## The original (External)

| Item | heart1 |
| --- | --- |
| Source | [`daniel-ziegler/sts_lightspeed`](https://github.com/daniel-ziegler/sts_lightspeed), `silverbot/rl_train.py`; `heart1.pt` = iteration 2575 (release download) |
| Net | pre-norm token transformer, dim 256, 4 layers, 8 heads, RMSNorm; per-choice logits, value head on the pooled trunk, auxiliary destination-room head |
| Algorithm | PPO + GAE (λ 0.97, γ 1, clip 0.2, 2 epochs), entropy and LR annealing; GRPO tested and dropped |
| Lineage | fair-play "honest1" from scratch (~2026-06-04), ascension mixture widened 0-5 → 0-15 → 0-20 uniform (`seed % 21`) |
| Reward | v4 (2026-06-08): floor/190 (cap 0.3) + 0.2 act-3 clear + 0.1/key + 0.3 Heart; later floor/190 + 0.05/key + 0.6 Heart with potential-based shaping on deck quality |
| Combat | Silver MCTS, 1,000 sims in training, 10k at eval |
| Hardware | 30 worker processes + one A10, collection pipelined with the update |
| Result | A20 18.6% ± 2.4% Heart kills (n = 1,000, 10k sims); our reproduction 21.5% [16.4, 27.7] (n = 200, project memory 2026-10-15) |
| Own diagnosis | plateau from credit assignment: card choice is a near-fixed identity ranking (identity alone predicts 55-64% of picks, duplicate aversion ~0), ascension moves card choice by TV 0.067 while the value head reads it strongly; the trunk encodes the deck (probe R² 0.8-0.97) but the critic does not use it |

So only ~1/21 of its games were A20, its reward is not P(Heart kill), and its engine lacks our parity fixes.

## What we have

- Engine with the parity fixes, flexible keys, Act-4 strong; Silver with learned stop; cheap-combat licence (§739).
- Native heart1 and student_sel forward passes (`apps/one_combat/heart1_policy.*`), the torch student model,
  distillation and export (`tools/heart1/`), capture hooks; record v2 inputs in #941 (open).
- Map MCTS, the M0-calibrated rollout3 leaf (ADR-0057), AZ-gen Gumbel targets, outcome and perturb corpora.
- SPRT gate standard (ADR-0064), paired SD ≈ 0.42 per pair (§740).

## What is missing

1. Sampling at temperature 1 with log-prob and value per decision (`heart1::policyStep` is greedy only).
2. Trajectory export: record, chosen index, log-prob, value per decision; outcome per game; compact (share quota
   10 GB / 50,000 files).
3. Fallback accounting: screens without a heart1 encoding stay on the chain and are excluded from the gradient;
   the potion-discard output is still missing.
4. PPO trainer for our record format: GAE, clipping, value warm-up (student_sel's value head is untrained), KL anchor
   to the start net, checkpoint/resume, `.bin` export.
5. Iteration loop (one machine for the pilot; resumable cloud actors/learner later) and a reserved training seed block.

## Improvements over the original (Inference, one variable per gate)

| # | Change | Rationale |
| --- | --- | --- |
| V1 | A20 only | original saw ~5% A20 and barely adapts card choice to ascension |
| V2 | our engine | train where we play; no engine gap, no re-distillation for a d64 run |
| V3 | reward 1{Heart} + potential-based shaping with Φ = M0-calibrated leaf value | the objective becomes the Heart rate (shaping telescopes at γ = 1) with lower variance |
| V4 | forked common-random-number advantages at a fraction of card choices (VinePPO-style) | targets the original's diagnosed credit problem; our engine can copy states. §685: single outcomes rank siblings poorly, so use only as advantage estimates inside PPO |
| V5 | record v2 inputs (#941) for policy and critic | public run state heart1 never saw; PPO self-play produces v2 records for free |
| V6 | asymmetric critic with hidden information, training only | lower-variance baseline, unbiased gradient; needs Philipp's call against ADR-0002 |
| V7 | combat curriculum: Silver 1,000, then a few iterations at production combat | reduces the train/deploy combat gap |
| V8 | per-game coordinated exploration (card bias or temperature drawn per game) | the original found per-decision entropy cannot discover multi-pick builds |
| V9 | KL to map-MCTS policy as auxiliary | low priority: AZ generations had little to teach (§621, §643) |

The PPO value head is also the run value wanted for the run-aware Silver leaf (roadmap phase 4) and for #941's
shared-encoder heads.

**One trunk, one checkpoint lineage (agreed with the CTM shared-encoder thread, 2026-11-01).** The shared encoder
is the student_sel trunk itself with extra heads (CTM survival/HP/potions through an encounter query token that only
the CTM head sees, plus value and prior). PPO fine-tunes that same trunk; the two efforts share one checkpoint
lineage instead of building two nets. PPO self-play records in v2 format (`obs.v2.run_counters`, `obs.v2.fought`,
`offer_prices`, #941) are the intended training data for the extra heads.

## Staged plan

| Stage | Content | Cost | Decision |
| --- | --- | --- | --- |
| S0 | PR 1 sampler + trajectory export; PR 2 PPO trainer + export. Checks: temperature 0 byte-identical to today's greedy choices, native vs torch log-prob < 1e-5, one-iteration smoke | 1-2 thread-days, smoke seeds | review PASS per PR |
| S1 | PC pilot: decision net (see above; originally student_sel), A20, Silver 1,000, reward V3, 512 games per iteration, 3 value-only warm-up iterations, 60 PPO iterations | ~31k games, ~170 core-h, ~14 h on 12 threads | G1 |
| G1 | final vs student_sel, policy alone (`STS_OOC_MCTS=0`), Silver 1,000, 2,048 fresh paired A20 seeds, SPRT standard | ~23 core-h | GO if ΔHeart 95% CI > 0; one more 60-iteration block if point > 0, CI includes 0 and the in-sample A20 curve rises; STOP if ΔHeart ≤ 0 with a flat curve |
| S2 | production confirmation: new net as map-MCTS prior vs the default, AZ matched-CPU rule | 1,024-4,096 pairs, ~470-1,900 core-h | default change is Philipp's call |
| S3 | cloud actor/learner, 0.5-1M A20 games, Silver-1,000 checkpoint gates every ~200k games, production A/B every ~1M; d256 on the GPU if d64 saturates | ~6k core-h per 1M games + sync engineering | after G1 GO |
| S4 | V3-V8 one at a time | ~25-100 core-h per gate + training | each gated |

Every run needs a pre-registration, the seed-run guard, frozen provenance and Philipp's typed go.

## Known limitations and open questions

- 31k pilot games are few against the original's ~1.1M; the pilot tests direction, not ceiling.
- X1 validated cheap combat on one key effect; card effects whose value depends on fight skill are untested.
- Is d64 enough capacity, or is d256 on the GPU needed?
- Can an asynchronous cloud loop stay close enough to on-policy across container resets?

## Relevant sources

- External: `README.md`, `EXPERIMENT_LOG.md` (2026-05-31 to 2026-07-05), `run_heart1_supervised.sh` at `84ab3ea`.
- [One-year roadmap](one-year-roadmap.md), [cheap-combat proxy result](../../experiments/evidence/cheap_combat_proxy_20261031/RESULT.md) (§739),
  ADR-0047, ADR-0057, ADR-0064, `THIRD_PARTY_NOTICES.md`, PR #941.
