# Offline gate for the card-select student (written 2026-10-17 before training)

Scoring: native `one_combat heart1score` on held-out rows, i.e. capture files with seed % 8 == 7.
- Old capture: 8 seeds, ~126k rows.
- New capture: seeds 111156103, 111, 119, 127, 135, 143, 151, 159.

Both `student_sel.bin` and `studentc.bin` are scored. Top-1 means agreement of the student's argmax with heart1's
argmax over the row's tokens. Rows with fewer than 2 tokens are skipped.

- G1: on the old held-out rows, `student_sel` top-1 ≥ 92.0% (student C: 93.0%).
- G2: on the new held-out card-select rows, `student_sel` top-1 > student C top-1 for each of
  REMOVE, TRANSFORM, TRANSFORM_UPGRADE and UPGRADE.
- G3: on the new held-out node rows, `student_sel` top-1 ≥ student C top-1 − 1 pp in each act with ≥ 1,000 held-out
  rows (acts 1–3). Act 4 has only 121 held-out node rows: it is reported but not gated.

The student passes if G1, G2 and G3 all pass. Passing makes it a candidate for the requalification parity check
and a short A/B. It does not make it a default.

Student C baseline on these rows (native, 243,103 rows, `studentc_gate_baseline.txt`): old 92.99% (§488's 93.0%,
so the scoring reproduces it); new node rows by act 90.1 / 85.3 / 82.0 / 67.8% (act 4: n=121); new selects REMOVE
0.06%, TRANSFORM 0.11%, TRANSFORM_UPGRADE 0.00%, UPGRADE 18.8%, DUPLICATE 46.7%, OBTAIN 78.5%.
Scripts: `gate_prep.py` (held-out rows), `gate_score.py` (top-1 by group); binary 5eff2ad7.
