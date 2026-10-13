# §443 pathb-a20 escape candidate (data only, never merge)

Shipped so the §457 OOC MCTS A20 A/B can run in the cloud. Built on Philipp's machine by
`build/ctm-a20/run_escape_a20.sh` at 643a4892 (Stage 2), copied unchanged from `build/ctm-a20/run/`.

- `STD1-escape.native` standard, sha256 b489e537…
- `FAST1-escape.native` fast, sha256 34870815…
- `candidate-pathb-a20-escape.json` v3 manifest (candidateId `pathb-a20`), sha256 7274c5c3…
- `escape-exposure-override-a20.json` Philipp's E1 exposure override the escape capability ships on.
- `final-headers-escape.txt` header summary at build time.

Load as a research candidate: `STS_CTM_RESEARCH_CANDIDATE_MANIFEST=<path to manifest>`,
`STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256=7274c5c3386166be23cae19a28d792d43b237bc8d612277f4b1c7173308ebdc5`,
fast `FAST1-escape.native`, Brew fallback `STD1-escape.native`. No Lizard support: active-Lizard rows are refused.

## Stage 4 step 1 (Lizard refit) did not run
`one_combat ctmlizardfeatures` (binary from 643a4892) aborted on all three scopes (lizard_fairy, lizard_brew, none) with
`active-Lizard correction enabled without its frozen artifact metadata` (logs in `step1-attempt/`). FAST1-escape has no
`activeLizardCorrection` header: chain B skipped s23 (`package_deepsets_lizard_artifact.py`, the mechanical-q Lizard
packaging), so there is nothing for `ctm_lizard.py extend` to refit either. Adding that header changes FAST0, which forces
a restamp and a fast escape refit, so it is a new pre-registered step, not part of PREREG-REGATE.md step 1.

`SHA256SUMS`: check with `sha256sum -c` from this folder.
