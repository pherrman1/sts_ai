# §443 Stage 4: A20 Lizard refit and a re-gate on fresh A20 seeds (pre-registration, approved 2026-10-13 15:00Z)

Philipp chose "Plan Lizard + regate" on 2026-10-13 14:40Z after Stage 3a came out NOT_QUALIFIED (ledger §443,
merged in #518 as 8fa12aea). This is a draft. It changes until Philipp approves it; once the fresh corpus starts,
it is frozen and every later change is a new ledger entry. Nothing runs before his approval.

## Baseline
- Candidate from Stage 2: the escape pair `pathb-a20` (standard `b489e537…`, fast `34870815…`, manifest
  `candidate-pathb-a20-escape.json` `7274c5c3…`), on Philipp's machine in `build/ctm-a20/run/`.
- Stage 3a on the old TEST split (63,648 rows): criteria 1, 3 and 4 passed. Criterion 2 failed on boss rows only
  (+0.0153 [+0.008, +0.023] against |bias| ≤ 0.01). Criterion 5 failed because 1,440 rows (2.3%) were refused, all
  `active_unqualified_lizard`, while production refuses none.
- The old TEST split has now been looked at, so it cannot settle a second gate. The re-gate needs fresh seeds.

## Hypothesis
With Lizard Fairy/Brew support refit at A20, the candidate passes all five Stage 3a criteria, unchanged, on a fresh
A20 corpus that played no part in training, model choice or this plan.

## Step 1: Lizard refit (no new network, no C++ change)
The method is the one §423/§435 used at A0 (`tools/ctm_lizard.py`, module docstring):
1. Run `one_combat ctmlizardfeatures` with the escape pair over the A20 forced slices already on
   `claude/ctm-a20-data` (lizard_fairy from 78300000, lizard_brew from 78301000), plus the active-Lizard rows of the
   main Stage 1 corpus.
2. Run `python tools/ctm_lizard.py fit` on those features. The tool chooses L2 on VALIDATION (#418 hash split) and
   never trains on TEST rows.
3. Run `python tools/ctm_lizard.py extend --artifact FAST1-escape --fit … --fast-r --brew --fairy`. The fast r is
   refit too, because the A0 r was fit at ascension 0 and does not carry over (Stage 2 pre-registration). This gives
   the new fast artifact and its manifest entries, as candidate `pathb-a20` with escape plus `lizardFairy` and
   `lizardBrew`. The standard artifact is unchanged.
4. Keep rule (my proposal, fixed before the fit): the Lizard capability is kept only if
   - on VALIDATION, r NLL is at or below the TRAIN base-rate NLL for each child, and
   - composed survival on Tail-fired VALIDATION rows is within 0.01 of the observed rate, for fairy and for brew
     separately.
   If either check fails, stop and report NOT_QUALIFIED with no re-gate, because criterion 5 cannot pass without
   Lizard support.
5. Where it runs: Philipp's machine, CPU only. The fit is minutes; the feature pass scores the Lizard part of the
   40,221 forced rows and the main corpus's active-Lizard rows.

## Step 2: fresh A20 gate corpus (cloud)
- Same frozen generator as Stage 1: run commit `90f6df64`, `one_combat` sha256 `12e881be…`, the same teacher
  (`teacher.json` `01e96a9f…`), `combattransitiongen`, ascension 20, and the same `run_unit.sh` and `worker.sh`.
  The only change is the seed ranges.
- Main seeds: 78600000–78603999 (4,000 seeds, about 76k rows at Stage 1's 19 rows per seed; the old TEST split had
  63,648 rows from 3,314 seeds).
- Lizard diagnostic slices (not part of the five criteria): lizard_fairy 78610000–78610199 and lizard_brew
  78611000–78611199.
- Smoke: 78009060–78009063 (one main and one Lizard unit), run in this thread before any worker starts.
- Workers: 8 (Philipp, 2026-10-13 15:00Z: "Approve 8 workers"). Each runs 500 main seeds plus 50 Lizard seeds,
  about 45 min at Stage 1's rate of 2,000 seeds in about 2.5 h per worker. Scripts: `ctm-a20/stage4/` (`worker.sh`
  with the Stage 4 seed map; `run_unit.sh` and `teacher.json` byte-identical to Stage 1).
- Stall handling as in Stage 1: units that abort with rc 134 are rerun one seed at a time; seeds that abort again
  are excluded and listed. The excluded seeds are fixed before scoring.
- Rows go to `claude/ctm-a20-data` under `ctm-a20-stage4/` (data only, never merged).

## Step 3: re-gate (Stage 3a again, same bars)
- Script: the frozen `gate3a.py` (`25f7dc00…`), with the same bootstrap (source seed, 2000 reps, seed 443, 95%
  percentile CI) and the same five criteria and bars as `ctm-a20-stage3/PREREG-GATES.md` (`4134ef35…`).
- Rows: every row of the fresh main seeds is a gate row; no split filtering. **Unverified:** whether `gate3a.py`
  keeps only hash-split TEST rows. `gate3a.py` lives only on Philipp's machine, so this is checked there before any fresh row is scored.
  If it does filter, the only change allowed is a flag that scores all rows (no other line changes), reviewed before
  scoring.
- Arms:
  - Candidate: the Step 1 artifact pair, scoring the unmodified rows.
  - Production: today's default stack (fast `c6d56bbc…`, standard `b9188de0…`), scoring a copy of the rows with
    ascension set to 0, as in Stage 0 and Stage 3a. The copy's sha256 is recorded.
- Report:
  - death bias and win-HP bias overall and per room class;
  - refusals per reason for both arms (Lizard, Ritual + Writhing, hp_envelope, escape);
  - rows scored by both arms;
  - as a diagnostic only: composed survival against observed survival on Tail-fired rows of the fresh Lizard slices.
- Result: PASS or NOT_QUALIFIED, exactly as in Stage 3a. On PASS, the runtime switch and the live gate (3b) follow the
  Stage 3 pre-registration unchanged (search seeds 78500000 + decision index); each still needs Philipp's go.

## Risk stated now
**Inference:** the boss bias may fail again. Its Stage 3a point estimate (+0.0153) is above the bar, and the Lizard
refit does not touch boss calibration. The fresh gate shows whether that was noise. No recalibration is added after
seeing fresh results; a boss calibrator would be a new pre-registered step with a runtime change.

## Non-goals
- No new network, no retraining of the standard or fast networks, no new gates or bars.
- No default change. OOC MCTS stays off by default (ADR-0027).
- The old TEST split is not reused for the decision.

## Seeds (all in §443's 78M range)
78009060–063 smoke; 78600000–78603999 main gate corpus; 78610000–199 lizard_fairy; 78611000–199 lizard_brew.
78500000+ stays reserved for the live gate.
