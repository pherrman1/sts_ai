# s23 Lizard packaging for pathb-a20: BLOCKED at step 4

Code: origin/main 37b7d33eb1ab342eeb6fbe701b54f1d05b7d5a08 (tools/ and one_combat built from it; see CODE_SHA.txt).
Script: run_lizard_s23.sh. Every command with input/output sha256: commands.log.

Steps 1-3 succeeded:
- STD2.native e338506d... (STD1-escape b489e537... + writhingRitual)
- FAST0L.native d8064294... (FAST-export.native + mechanical-q Lizard header, STS_CTM_PINS=pins-12.json)
- FAST1L.native 6090417f... (stamped, control STD2)

Step 4 failed (s4-escextend.stderr):
`python tools/ctm_escape.py extend --artifact FAST1L.native --checkpoint run/capabilities/esc-fast-fit/escape.pt`
-> `ValueError: escape fit was made on a different artifact` (tools/ctm_escape.py:304-305).

Cause: escape.pt (sha256 18f346b5...) records metadata.baseArtifactSha256 =
6af8febe59c9c0c8796cabc2295c3294905f9bf99522c93f73dfcd71ff53656e, which is FAST1-esc-base.native (the artifact FAST1-escape
was extended from). `extend` requires the checkpoint's base artifact to equal the artifact being extended byte for byte, so
the "reuse the same escape.pt, no refit" instruction cannot be executed with current tools on FAST1L (6090417f...).
No payload check was run (FAST2L does not exist). Steps 5-8 did not run. Nothing was bypassed or patched.

Options (need a decision; each is a change to PREREG-LIZARD.md):
a) refit the fast escape on FAST1L (as run/run_lizard_a20.sh did), which drops the "no refit" / byte-identical payload property;
b) a tool change letting `extend` accept a checkpoint whose base differs only in header (same tensor payload sha256).
