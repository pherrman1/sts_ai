# §488 OOC MCTS with the distilled heart1 student C as the tree prior (2026-10-15)

Pre-registration: [PREREG.md](PREREG.md). Result and interpretation: ledger §488 in `docs/experiments/ledger-06.md`
(after the run).

- Code commit in `CODE_COMMIT` (main `982f1366` plus: the heart1 port reads the network size and map trim from the
  weights file; the exporter writes `meta.n_heads` / `meta.trim_map`). Release `one_combat` sha256 in `binary.sha256`
  (GCC 13.3.0, cloud container); main's own build reproduces the §487 binary `2779f937…` here.
- Weights (`student_weights.txt`): `student.pt` from `claude/heart1-distill-data@68fe88be` (never merged), exported
  with `tools/heart1/export_heart1_weights.py ... --allow-other-checkpoint --n-heads 4 --trim-map` to
  `/mnt/project-files/student-c-488/studentc.bin`.
- Arms (`arm_env.sh`): `v4` (the §486 `v4` arm) and `studentc` (the §486 `heart1` arm with the student's weights).
  One `bestbench 10000 1 20 SEED` unit per seed and arm (`run_unit.sh`, 8 h timeout), `NWORKERS` workers over the
  cohort in `COHORTS` (`worker.sh`); results go to `/mnt/project-files/student-c-488/`.
- Checks before the run (this container):
  - heart1 unchanged: `one_combat heart1score heart1.bin` (`1e92f2a6…`) on 3,000 captured tree-node records (1,500
    each from capture seeds 108000007 A20 and 108000039 A0, held out from training; `random.seed(0)`,
    `random.sample(rows, 1500)` per file over the rows with a `record`) gives byte-identical output with
    main's binary and this one, and with `STS_OOC_HEART1_SCALAR=1`.
  - Student parity (`student_parity.py`, silverbot @84ab3ea with its `slaythespire` module, torch 2.14 CPU): native
    vs torch max |Δ| 1.55e-05 over logits and values, argmax 3,000/3,000; native student top-1 vs heart1 2,777/3,000
    (92.6%; rewards 94.2%, map 85.0%, shop 89.3%). AVX and scalar student outputs are byte-identical.
  - Cost in `heart1score` (3,000 records, one core): heart1 93 s, student 5.6 s including start-up.
- Smoke (run binary, `/mnt/project-files/student-c-488/smoke.tar.gz`, sha256 `2780f362…`):
  - `v4` on §486 seed 107000049 reproduces the §486 `v4` row (won 0, floor 16, act 1, hpEnd 0) and all 48 OOC
    decisions in the trace (`idx`, `pre`, `post`, `by`).
  - Seed 74072190: `studentc` loads `(dim 64, heads 4, hidden 256, layers 2, trim_map 1)`, logs `prior=heart1`,
    the student scores 94,780 of 94,780 prior builds (no fallbacks), clears act 3 in 647 s, MCTS CPU 4.95 s per owned
    decision; `v4` dies on floor 42 in 312 s, 2.99 s per owned decision.
  - Smoke seeds 74072190–74072199 are reserved for this thread (190 used).
- Analysis: `python3 tools/analyze_student_prior_488.py report.json DIR... --ref486 DIR...` over the extracted `out/`
  folders of this run and of §486 (selftest: `python3 tools/analyze_student_prior_488.py selftest`).
