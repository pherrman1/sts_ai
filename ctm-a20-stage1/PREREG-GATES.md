# §443 Stage 3 gates for the A20 CTM: DRAFT pre-registration (2026-10-12)

Written before Stage 2 trains anything. Philipp or the reviewer can change it until Stage 2 starts. After that it is
frozen, and any change becomes a new ledger entry. The offline gate follows the review notes on #498.

## Data split (by source seed, fixed now)
- TEST: main-corpus seeds 78228000–78231999 (workers 15 and 16, about 80k rows). These rows are never used for
  training, early stopping or model selection.
- VALIDATION: seeds 78226000–78227999 (worker 14).
- TRAIN: all other Stage 1 main seeds and all forced slices.
- Excluded: seeds that stalled native Silver in Stage 1 (listed in the ledger). Partial rows from aborted units are
  dropped. Those units are rerun one seed at a time and replaced (see "Stall handling").

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
The automatic OOC MCTS stack picks the A20 artifact when ascension ≥ 20, behind a flag that is off by default. A test
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
