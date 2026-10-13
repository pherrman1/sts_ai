# §443 Stage 3 gates for the A20 CTM: DRAFT pre-registration (2026-10-12)

Written before Stage 2 trains anything. Philipp or the reviewer can change it until Stage 2 starts. After that it is
frozen, and any change becomes a new ledger entry. The offline gate follows the review notes on #498.

## Data split (by source seed, fixed now)
- Amended 2026-10-12 before any training: the split is the existing #418 source-seed hash split
  (`split_for_seed`, 80/10/10 TRAIN/VALIDATION/TEST), applied to every Stage 1 row. The tools already use it, so no
  split code changes. A source seed's rows are never split across sets.
- TEST rows are never used for training, early stopping or model selection.
- Excluded: the 5 stalled seeds (78217905, 78218250, 78220424, 78220620, 78225246) and the partial rows of the 5
  aborted units. The per-seed reruns replace those units.

## Training recipe (fixed now)
- Warm start as in #418 (amended again, before training): components the #418 chain refits from A0 production
  start from those A0 weights. Their ascension normalization (A0: mean 0, inverse std 1e6, a constant feature) is
  re-centred to mean 20, so A20 rows present ascension exactly as A0 rows did (input 0). From-scratch steps (s07,
  nf14 HPO, gold decoder, s18 encoder) compute normalization from A20 TRAIN. The flag is opt-in, so A0 runs are
  byte-identical. The artifact is valid only at ascension 20 and is selected only there (exactly 20, not ≥ 20).
- Every A20 training row must have ascension exactly 20; the training scripts check this and stop otherwise (with
  inverse std 1e6, any other value blows up the input).
- Training runs from the reviewed #504 head 2cb43780 (review PASS 2026-10-12).
- Lizard: the first A20 candidate declares no `lizardFairy`/`lizardBrew`. The A0 mechanical-q Lizard correction
  was fit at ascension 0 and does not transfer. Active-Lizard states are refused as before (V4 fallback). Refitting
  Lizard at A20 is a later step.
- The s09 max-HP-gain set is taken from A20 TRAIN wins; its counts are reported before the candidate is frozen.
- The HP domain is A0's [24, 220]. The corpus has no pre-fight max HP below 24 (minimum 41); 203 forced high_maxhp
  rows above 220 are dropped, as at A0.
- New candidate id `pathb-a20`. Capabilities (escape, Lizard Fairy/Brew, Writhing + Ritual) are refit from the A20
  forced slices and kept only if they pass the same exposure and qualification rules as #418/§435.

## Offline gate (Stage 3a): the candidate A20 artifact vs production with ascension clamped to 0, on TEST
Each row is scored by `ctmscorerows` with each model. The 95% CI is a source-seed bootstrap with 2000 reps and seed 443.
PASS needs all of the following:
1. Survival NLL difference (candidate − production): upper CI < 0.
2. Death bias (predicted − observed): |bias| ≤ 0.01 overall, and separately for normal, elite and boss rows.
3. Win-HP bias: within ±3 HP overall, and separately for normal, elite and boss rows.
4. HP NLL difference: upper CI < 0.
5. Support: refusals on TEST ≤ production's (Lizard, Ritual + Writhing, `hp_envelope`). Rows with max HP < 24 are
   scored by the candidate.
If PASS fails, the result is NOT_QUALIFIED; it is recorded in the ledger and there is no live gate.

## Runtime switch (Stage 2 code): byte-identity test
The automatic OOC MCTS stack picks the A20 artifact when ascension is exactly 20, behind a flag that is off by default. A test
must show that with ascension < 20, and with the flag off at any ascension, the selected artifacts and the rollout3
play on two fixed seeds are byte-identical to main.

## Live gate (Stage 3b): only after 3a passes
- Harness: as in §426, rollout3 OOC MCTS at A20 on the verified gold decisions (§425/§426 set, gold2 regret labels
  from §432). Arm A: the A20 stack with the flag on. Arm B: today's default stack (production CTM, ascension as
  given). Pairing is per decision, with the same search seed in both arms.
- Search seeds: 78500000 + decision index.
- Primary metric: mean regret in floors against gold2. The difference A − B gets a decision-level bootstrap 95% CI.
- Decision rule:
  - BETTER if the upper CI < 0.
  - WORSE if the lower CI > 0.
  - NOT_SHOWN otherwise.
  - A difference of 0.3 floors is the smallest effect of interest (Inference: §426 found −0.40 [−0.96, +0.16] for the
    Lizard CTM, so n ≈ 400 decisions resolves about 0.5 floors).
- No default play changes either way, because OOC MCTS stays off by default (ADR-0027). BETTER makes the flag the
  recommended A20 stack for later A20 OOC MCTS work.

## Stall handling (Stage 1)
Units that aborted on a native Silver stall or depth error (rc 134) are rerun here one seed at a time, with the frozen
binary and teacher. Seeds that abort again are excluded and listed. Per the reviewer's check of #498, rows do not depend
on how seeds are batched.
