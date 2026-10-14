# §443 Stage 4 Step 1b: Lizard header, Writhing+Ritual and A20 Lizard refit (pre-registration, 2026-10-13)

Philipp, 2026-10-13 19:31Z: "Okay add the lizard support then? I want no fallbacks to v4". Written before any Step 1b
output exists. It replaces PREREG-REGATE.md Step 1 (which could not run); Steps 2 and 3 there are unchanged.

## Why
In §457 the `pathb-a20` escape candidate made OOC MCTS fall back to V4 on 64.6% of decisions: 6,556 refused imagined
combats were `active_unqualified_lizard` and 9 were `writhing_ritual_intersection`. FAST1-escape has no
`activeLizardCorrection` header (chain B skipped s23, `package_deepsets_lizard_artifact.py`), so there is nothing to refit.

## Steps (header-only except the r fit; no network training, no C++ change), on Philipp's machine, CPU only
1. STD2 = `ctm_capabilities.py writhing-ritual` on STD1-escape.
2. FAST0L = `package_deepsets_lizard_artifact.py FAST0 mechanical_q_candidate.json` (repo copy, 15da76f4) with the final
   A20 pins (`STS_CTM_PINS`). This adds the A0 mechanical-q header; its r is a placeholder replaced in step 7.
3. FAST1L = `ctm_candidate.py stamp --artifact FAST0L --control STD2`.
4. FAST2L: refit the fast escape on FAST1L exactly as chain B did for FAST1-escape (`ctmescapefeatures` on the same rows,
   `ctm_escape.py fit`, `extend`). Amendment 2026-10-13 19:5xZ, before any Lizard output existed: `extend` refuses a
   checkpoint fit on another file (ctm_escape.py:304), so the planned reuse cannot run. FAST1L has the same tensor payload
   as chain B's escape base, so the features and the fit should come out the same. Diagnostic (not a stop rule): whether
   FAST2L's payload equals FAST1-escape's byte for byte; if not, report the escape-head difference.
5. FAST3L = `ctm_capabilities.py writhing-ritual` on FAST2L; interim manifest `--standard STD2 --fast FAST3L`.
6. `one_combat ctmlizardfeatures` with that manifest over the Stage 1 forced slices (lizard_fairy 78300000+,
   lizard_brew 78301000+) and the Stage 1 main corpus.
7. `ctm_lizard.py fit` (L2 on VALIDATION, never trains on TEST), then `extend --fast-r --brew --fairy` -> FAST4L;
   final manifest `--standard STD2 --fast FAST4L` (candidate `pathb-a20`).

## Keep rule (unchanged from PREREG-REGATE.md Step 1.4)
Lizard support is kept only if, on VALIDATION, r NLL is at or below the TRAIN base-rate NLL for each child, and composed
survival on Tail-fired VALIDATION rows is within 0.01 of observed, for fairy and brew separately. Otherwise report
NOT_QUALIFIED and ask Philipp before any live use.

## Writhing+Ritual
**Inference:** adding `writhingRitual` without the intersection cohort gate is unvalidated; the cohort is tiny (9 refusals
in 128 A20 runs). It is added only so no imagined combat falls back to V4, and the result records that.

## What remains a fallback
`hp_envelope` (HP outside the declared domain) cannot be lifted without a new domain; §457's A20 arm had none. Any
remaining fallback is reported by reason.

## Then
A rerun of only the `combo` arm of §457 on seeds 87000000–127 with the new candidate and `STS_OOC_MCTS_ACTIVE_LIZARD=1`,
same binary as §457, reusing its `off` and `combo_def` rows; it gets its own ledger entry and pre-launch review.
Smokes use 74047010–099.

## Override (2026-10-14 09:38Z)
Keep rule result: criterion 1 PASS, criterion 2 FAIL as written (Tail-fired VALIDATION rows: fairy +0.070, n=44; brew
−0.014, n=21; all-row cohorts −0.0003 and −0.0013). Philipp chose "Override, re-gate" on the card "Override the failed
Lizard keep check and run the A20 CTM re-gate on fresh seeds?". The Lizard candidate (data branch c507cebb: STD2
e338506d, FAST4L ae785ec2, manifest 704f2a58) goes to the PREREG-REGATE.md Step 3 re-gate unchanged, as the
candidate arm. Recorded as an override, not a pass.
