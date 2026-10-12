# §443 A20 CTM Stage 1 corpus (data only, never merge)

Data-only branch for shipping the §443 Stage 1 corpus to the training machine (Philipp's "data branch ok",
2026-10-12). Run commit 90f6df64, binary 12e881be, teacher `ctm-a20-stage1/teacher.json`.
- `w01..w16.tar.gz`: main corpus seeds 78200000–78231999 (40 units of 50 per worker). Units with rc=134 in a
  DONE file are replaced by `rerun-stalled.tar.gz` (one seed per unit); stalled seeds 78217905, 78218250, 78220424,
  78220620, 78225246 are excluded. Drop the partial jsonl of the rc=134 units.
- `w00.tar.gz`: forced slices lizard_fairy 78300000+600, lizard_brew 78301000+600, ritual_writhing 78302000+400,
  high_maxhp 78303000+100.
- `PREREG-GATES.md`: draft gates and TEST/VALIDATION split. `SHA256SUMS`: check with `sha256sum -c`.
