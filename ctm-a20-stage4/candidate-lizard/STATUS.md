# s23 Lizard packaging for pathb-a20: DONE (after amended step 4)

Code origin/main 37b7d33eb1ab342eeb6fbe701b54f1d05b7d5a08; one_combat built from it (CODE_SHA.txt).
First attempt (run_lizard_s23.sh) blocked at step 4: see ERROR.md. PREREG-LIZARD.md was then amended (sha256 d2ea9904...):
step 4 = refit the fast escape on FAST1L as chain B did. Continuation: run_lizard_s23_b.sh (log run_b.log; commands.log has
every command with input/output sha256).

- STD2.native            e338506d... (STD1-escape + writhingRitual)
- FAST4L.native          ae785ec2... (FAST0L -> stamp -> escape refit -> writhingRitual -> lizard --fast-r --brew --fairy)
- candidate-pathb-a20-lizard.json  704f2a58...
- Step 4 diagnostic (step4-payload-check.txt): FAST2L tensor payload == FAST1-escape payload byte for byte
  (36853140...; escape tensors max abs diff 0). Refit escape.pt: esc-fast-fit/ (sha256 in SHA256SUMS).
- Chain-B gates on the refit: escape VALIDATION nll 0.2574 < constant 0.4332; hpClasses [-219, 231] equal to standard.
- Features (s6): fairy activeLizardRows 13558 / supported 13553; brew 12566/12566; none 13303/13297.
- lizfit/fit.json and s7-fit.stdout: fit receipt (fast/standard r, L2 chosen on VALIDATION, evaluation per split/child).
Not pushed: esc-fast/features.{csv,f32} (escape features, 28 MB + 148 MB; sha256 in commands.log).
