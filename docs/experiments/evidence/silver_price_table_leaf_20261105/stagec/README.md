# Stage C campaign (price-table leaf at Shield & Spear)

Pre-registration: [../PREREG-stageC.md](../PREREG-stageC.md). Philipp's go: 2026-11-05 20:05 CET, 40 workers.

- `tools/extract_ss.py` (§724's script, Incense filter as an argument) on the restored unit tars of run 1
  (`value-clean-labels-run1`) and the key-rules, expert-anchored, gumbel-qcap and card-rule campaigns
  (`restore.py` from each share dir's `ARCHIVE-units.part*.tar.xz`): with Incense Burner 592 records (card-rule 57,
  expert-anchored 89, gumbel-qcap 38, key-rules 107, run 1 301) = §724's set; without it 4,435 records, 4,425 after
  deduplication.
- `tools/build_states.py`: 1,024 states (§724's 592 verbatim + 432 others, seed 20261105) → share
  `price-table-stagec/ss_states.tar` (sha256 `3422ca467f998538612541841fe5bd56a6d328f25aa34158dba46d9cfb009bab`).
- Anchors: `silver_price_table_test --report` on those states → share `price-table-stagec/tables.jsonl`
  (Incense 398 floor / 81 inside / 113 cap; others 308 / 61 / 63; no flat table).
- `units.txt`: state indices 0..1023 in `random.Random(20261105).shuffle` order (the gate order).
- Binary: v3 preset at code_commit `fb1477a5` (= #991's code), sha256 `4ace2751…`, in the share bin-cache.

## Smoke (author container, Release build of the same code, not part of the result)
Units 424 (Incense state, 20 runs) and 603 (other state, 12 runs), two at once: rc 0, 680 s and 772 s wall; the
T/TA/TI log lines as required; `analyze.py` on the two units: 0 bad rows, 0 dropped, gate PARTIAL (424 is the first
unit of the order, 564 the next), TA = T on 424 (floor). Estimated campaign: ≈ 1,024 × 12 min ≈ 205 CPU-h, ≈ 1.5 h
on 40 workers × 4 lanes.
