# Student C card-select fine-tune on the 3060 Ti (brief, 2026-10-17)

Data branch `claude/heart1-distill-data` (never merge). Code: `main` at 360055d0 (#615 merged) or later.
This is one GPU job: torch parity check, fine-tune, export, and a push of the results to this data branch.
No seeds are played. If any step fails, stop and report it. Do not work around the failure.

## Inputs (this branch)

- `data/cap-*.capture.jsonl.gz`: the old capture, 64 files, 1.01M tree-node rows, keys off, acts 1-3, V4-prior trees.
- `data-select-20261017/w01..w08.tar.gz`: the new capture. 64 A20 seeds 111156100-163, run e703d7bc, code ade19f01,
  binary 5eff2ad7, keys on, Act 4 included, student-C trees. 765,286 node rows and 390,406 card-select rows.
  `SHA256SUMS` lists the tars. Each tar extracts to `x/out/cap-a20-<seed>.capture.jsonl.gz` plus logs.
- `results/C_d64_trim/student.pt`: student C's state dict. Its export is `studentc.bin` (`eff2f74f…`).
- `data-select-20261017/parity_records.jsonl`: 390 records from the new capture. 150 have nonzero card misc;
  the other 240 have nonzero relic counters, 60 from each of acts 1-4.
- `data-select-20261017/studentc_baseline.txt`: student C vs heart1 top-1 on all new rows.

## Steps

0. Setup:
   - sts repo: `git fetch origin main claude/heart1-distill-data`, then build `one_combat` at origin/main (Release;
     CMake needs `CMAKE_POLICY_VERSION_MINIMUM=3.5`).
   - Data: check out the data branch in a separate clone or directory, check the tars with
     `sha256sum -c data-select-20261017/SHA256SUMS`, and extract each tar into its own directory.
   - silverbot: use daniel-ziegler/sts_lightspeed at 84ab3ea, built (its `build/` provides the compiled module).
     Reuse the checkout that trained student C if it is at 84ab3ea; otherwise clone and build it. Call its path SB.
1. Check that student C exports correctly:
   `python3 tools/heart1/export_heart1_weights.py results/C_d64_trim/student.pt c.bin --allow-other-checkpoint --n-heads 4 --trim-map`.
   - If the sha256 is not eff2f74f…, run `one_combat heart1score` with both c.bin and studentc.bin on parity_records.jsonl.
   - The logits must agree to 1e-5.
2. Parity check of the new inputs (gate P):
   - `python3 tools/heart1/student_inputs.py perturb SB results/C_d64_trim/student.pt pert.pt`
   - Export pert.pt to pert.bin with the step-1 flags.
   - `python3 tools/heart1/student_inputs.py score SB pert.pt parity_records.jsonl torch.jsonl --trim-map`
   - `one_combat heart1score pert.bin parity_records.jsonl native.jsonl`
   - **P passes** if, on all 390 lines, the logit counts are equal and max |torch - native| ≤ 1e-3.
   - Also report: the max diff, and how far pert's logits moved from c.bin's (it must be > 0, or the extra inputs do nothing).
   - If P fails, stop.
3. Fine-tune with student C's recipe, initialized from student C:
   `python3 tools/heart1/distill.py SB OUT --data data/cap-*.capture.jsonl.gz <new>/*/x/out/cap-a20-*.capture.jsonl.gz
   --dim 64 --layers 2 --mult 2 --heads 4 --trim-map --amp --device cuda --workers 6 --init results/C_d64_trim/student.pt
   --extra-inputs --compact --lr 3e-4 --epochs 6`
   - Validation is held-out seeds (seed % 8 == 7): 8 old seeds and 8 new seeds.
   - lr 3e-4 and 6 epochs are this brief's fine-tune default. Student C itself was trained at 1e-3 for 8 epochs from scratch.
   - Keep the log.
4. Export OUT's best state dict to `student_sel.bin` with the step-1 flags. Record its sha256.
5. No gate here. The thread that wrote this brief runs the offline gate in the cloud with the native forward
   (`heart1score` of `student_sel.bin` and `studentc.bin` on the held-out rows, old and new, against heart1's logits).
   It needs only the pushed `student_sel.bin`.
6. Push to this data branch under `results/E_d64_sel_xin/`:
   - student.pt, student_sel.bin, log.txt, summary.json;
   - parity.txt with step 1-2 outputs and max diffs;
   - SHA256SUMS.
   Push the data branch only. Don't touch main or any other branch.

## Not in scope

- No seeds are played and nothing switches on. `student_sel.bin` is a new file, default off.
- Using it needs an explicit `STS_OOC_HEART1` path.
- #591's non-UPGRADE card-select exclusion stays until Philipp decides.
