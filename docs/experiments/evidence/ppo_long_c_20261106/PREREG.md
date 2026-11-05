# LONG_C: LONG_B continued for 200 more updates (pre-registration, 2026-11-06)

Philipp, 2026-11-06 00:30 CET: "können wir weitere iterationen vorbereiten? maybe nochmal 200 iterationen mit dem
gleichen plan wie vorher?" Sources: LONG_B (§756, [RESULT](../ppo_long_b_20261104/RESULT.md)): net-0220 vs heart1
+6.69 pp [+4.54, +8.79], GO; the checkpoints rose +1.4 / +3.6 / +5.5 / +6.7 pp at 50/100/150/200 PPO updates with no
plateau. This is a preparation: nothing is frozen in a store and nothing plays before Philipp's typed go.

**Question.** Does the same run, continued unchanged from LONG_B's update 220 to update 420, produce a net that plays
A20 better than net-0220?

## Design
One conceptual change against LONG_B: more updates. Everything else is LONG_B's.
- **Start:** LONG_B's learner state after update 220 on the PC (`~/ppo-longb/LONG_B/state.pt`: net-0220 `408b2982…`,
  critic, Adam moments, iteration 220), frozen by `ppo_cloud.py init --fork-dir ~/ppo-longb/LONG_B --fork-at 220
  --continue` ([make_arms.sh](make_arms.sh)). `--continue` is new in this PR: the fork path of the architecture screen
  without reused games, for a source that finished after exactly N updates. It checks that the state and loop.json are
  at 220, that net-0220 is loop.json's last `next_sha256`, that no architecture flag is set, and that games, parts,
  seed base, sims, asc, pipeline and the actor env equal LONG_B's config.
  - `tests/test_heart1_ppo.py::test_cloud_continue`: an arm frozen with 2 iterations and continued to 4 produces nets
    bit-identical to an arm frozen with 4 iterations from the start, on the same games.
- **What continues exactly:** seeds (`seed_base` 111540000, iteration i plays 111540000 + 520·i …), salts (= iteration),
  pipeline 1 (iteration 220 is played by net-0219, as LONG_B would have), recipe (`ppo_train.py` defaults, `--seed 0`,
  λ 0.97, clip 0.2, 2 epochs, minibatch 192, lr 1e-5, entropy 0.002), `--micro-batch 192`, combat B
  ([actors_frozen.env](actors_frozen.env), byte-identical to LONG_B's), binary `78849fcf` (LONG_B's after its rebin;
  code_commit bc33e470, [screen.manifest](screen.manifest)), 520 games per update in 40 parts of 13.
- **What does not continue exactly:** the learner's torch RNG is reseeded at serve start, as at each of LONG_B's
  restarts; the minibatch order of update 221 therefore differs from an uninterrupted LONG_B. No effect on the
  question is expected.
- **Iterations 220-419 are PPO** (the value warm-up ended at 20). Checkpoints: net-0270, net-0320, net-0370 (`serve
  --keep-state 270 320 370`) and net-0420 (final state.pt).
- **Seeds:** 111654400-111758399 (200 × 520, new: no use on main, in the ledger, in any PREREG or in the project's seed
  notes, checked 2026-11-06). No smoke seeds: the continuation is covered by the unit test, and init refuses any
  mismatch with LONG_B.
- **Stalls:** LONG_B's rules (`aborted_game_lines`, max 1 stall per part of 13; a stall counts as a loss).
- **Store:** `ppo-xfer/longc` (new). LONG_B's local directory on the PC is the source and is not modified.

## Monitoring (pre-registered pause rule, no verdict)
The run monitor reports per 10 updates the in-sample Heart rate and the outcome decomposition (from the PC's
`games-NNNN.csv`). The author pauses the learner and asks Philipp when either holds:
- the in-sample Heart rate over the last 20 updates is below 17.0% (LONG_B's last 20: 19.69% ± 0.39), or
- Act 2 reached over a 10-update block is below 75.0% (LONG_B's blocks after update 120: 77.9-80.6%).

## Evaluation (primary)
LONG_B's evaluation runner and analysis (`../ppo_long_b_20261104/eval/`), copied with the arms replaced. It is
committed and delta-reviewed before it plays:
- PPO mode at temperature 0, combat B, binary 78849fcf, G1's seeds 111520000-111522047.
- **Control = L220 (LONG_B's net-0220), reused** from LONG_B's evaluation (`../ppo_long_b_20261104/eval/games.csv`),
  same seeds, binary, flags and net. A sentinel of 32 L220 seeds (111520000-111520031) is replayed first and must
  reproduce LONG_B's L220 games exactly (Heart kill, final floor, `decisions=`), else L220 is replayed in full.
- **Arm = net-0420**, played fresh. d = Heart kill net-0420 − L220 per seed.
- Gate `sprt_gate.py` gainer (d1 = +2 pp), look 64, cap 2,048, then the fixed-sample fallback; failed-game, abort and
  drop rules as in LONG_B's evaluation.

**Secondary (descriptive, no gate):** net-0270, net-0320, net-0370 vs L220; every checkpoint vs heart1 (GH, G1);
Act-1 deaths, Act-3 deaths, share of floor-51 runs that kill the Heart; in-sample curves as in LONG_B.

**Decision.**
- **GO:** net-0420 becomes the next PPO baseline. A production use needs a separate production A/B and Philipp's call.
- **Any other verdict:** the result goes to the ledger, and the next step is decided with Philipp.
- No default change in either case.

## Cost
- Actors: 104,000 games × ~27 s ≈ 780 core-h on 40 workers.
- Wall: ~3:07 per iteration in LONG_B's last 10 updates → ~10.5 h. The PC's GPU is busy all that time (no other GPU
  jobs: the learner needs ~6.9 of 8 GB).
- Evaluation: 4 × 2,048 + 32 games × ~27 s ≈ 62 core-h.

## Launch (after Philipp's typed go incl. the worker count)
1. PC (repo checkout at the run commit): `bash docs/experiments/evidence/ppo_long_c_20261106/make_arms.sh
   git:https://github.com/pherrman1/sts_ai#ppo-xfer/longc ~/ppo-longb/LONG_B ~/ppo-longb`
2. PC: `python3 tools/heart1/ppo_cloud.py serve --micro-batch 192 git:https://github.com/pherrman1/sts_ai#ppo-xfer/longc
   ~/ppo-longb LONG_C --keep-state 270 320 370`
3. Workers W = 1..40: `bash tools/heart1/ppo_cloud_worker.sh setup|start|wait docs/experiments/evidence/ppo_long_c_20261106 W`
   (two first, the rest after their first part).
4. End: copy net-0270/0320/0370/0420 for the evaluation, then `ppo_cloud.py cleanup` of the store refs on the PC.
