# §443 Stage 3a: run notes for the frozen pre-registration (2026-10-13)

`PREREG-GATES.md` in this folder is the amended, frozen pre-registration (sha256
4134ef359003d5d640be782f75c7bab7d519f2323f0038ba93a995c96038a824), copied byte for byte from the project share.
Its data-split section (#418 source-seed hash split, 80/10/10) replaces the withdrawn seed-range split of the
2026-10-12 draft.

Settled for the run (no change to the gate itself):
- Candidate: the escape-capable pathb-a20 pair (candidate-pathb-a20-escape.json, 7274c5c3…), which Philipp chose
  ("Override the smoke bomb.", 2026-10-13 12:07Z). The no-escape pair (3f17aad2…) is not gated.
- Production arm: today's default production stack. "Ascension clamped to 0" means scoring a copy of the A20 TEST
  rows with predictorInput.globals.ascension set to 0 and labels unchanged, exactly as Stage 0 did
  (docs/experiments/evidence/ctm_a20_stage0_20261012/README.md). Record that copy's sha256. The candidate arm
  scores the unmodified rows.
- Bootstrap: source-seed bootstrap, 2000 reps, seed 443, 95% percentile CI. Death bias and win-HP bias are
  reported overall and per room class (NORMAL, ELITE, BOSS).
- Support (criterion 5): report refusals per reason for both arms (Lizard, Ritual + Writhing, hp_envelope, and
  escape/Smoke Bomb, so any difference is visible).
- Outcome words: PASS or NOT_QUALIFIED, as in the pre-registration.
