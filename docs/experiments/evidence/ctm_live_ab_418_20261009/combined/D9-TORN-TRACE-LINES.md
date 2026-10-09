# D9 (post-run, before reading any result): torn JSONL lines in trace files

`cloud_worker.sh combine` (a159119d) crashed in the frozen analyzer (live_ab_analyze.py:175, JSONDecodeError).
95,486 JSONL lines across all unit trace/support/action files; 7 lines in 5 files do not parse. Each is a torn
fragment (head or tail of a record missing), consistent with non-atomic appends to the network share:
- cand-63000088.mcts.csv.actions.jsonl line 425 (25 B)
- off-63000064.trace.jsonl lines 480 (1244 B), 505 (854 B)
- off-63000112.trace.jsonl lines 698 (59 B), 740 (1872 B)
- off-63000120.trace.jsonl line 1462 (1006 B)
- prod-63000072.trace.jsonl line 321 (1862 B)
All unit CSVs (primary metric source) parse with consistent column counts; all 48 .done rc=0.
Handling: the analyzer bytes are unchanged (510ccf0d). It was run on a local copy of the combined run tree with only
those 7 lines removed; the originals stay untouched in w01..w04/run. The primary verdict reads the CSVs, so it is
unaffected; trace-derived secondaries (boss-entry HP, battle rows) may miss at most these records (4 trace files,
off x3, prod x1).

Correction after the independent result review (2026-10-09, REVIEW.md in reviews/ctm-live-ab-418-result-review-20261009/):
the non-atomic open/write/close appends (run_driver.cpp:102) also silently overwrote about 20 trace records on 4 seeds
(off 63000066, 63000115, 63000126; prod 63000073; all wins). The CSV primary, boss deaths and BOSS_DEATH_EXCESS are
exact; only the off arm's descriptive by-act boss-entry counts, start HP and Smoke Bomb counts are slightly off.

## Correction (result review, 2026-10-09; added in the repo copy only)

Everything above this heading is byte-identical to the share copy
(`/mnt/project-files/ctm-pathb/live-ab-cloud/combined/D9-TORN-TRACE-LINES.md`, sha256 `ff70eb74…`), which is the
pre-correction version. The independent result review
([reviews/result/REVIEW.md](../reviews/result/REVIEW.md), finding 2) found the sentence "may miss at most these
records" wrong.

Each trace record is appended by open/write/close (`apps/one_combat/run_driver.cpp:102`). On the network share these
appends were not atomic: some landed at a stale offset and silently overwrote earlier records. A per-seed contiguity
audit of `fight` and `idx` numbers ([reviews/result/trace_gap_audit.py](../reviews/result/trace_gap_audit.py)) finds
about 20 whole records lost on 4 seeds, all of them wins:

| Unit (arm) | Seed | Lost battle rows | Lost ooc rows | CSV outcome |
|---|---|---|---|---|
| off-63000064 | 63000066 | fights 23, 27–31 (incl. act-2 boss) | idx 121 | won |
| off-63000112 | 63000115 | fights 10, 14–23 (incl. act-1 and act-2 boss) | idx 58 | won |
| off-63000120 | 63000126 | last fight (act-3 boss; only the torn tail remains) | – | won |
| prod-63000072 | 63000073 | fight 27 (non-boss) | idx 128 | won |

No `cand` trace is affected. The `actions.jsonl` tear (cand-63000088) is in a file the analyzer does not read.

* **Unaffected, exactly:** the CSV primary (win, pairing, McNemar, stall sensitivity), the boss-death counts
  (cand 19, prod 26, off 18; all four seeds are wins with `fightsLost=0`, and for all 384 runs the trace's lost-fight
  count equals the CSV), and `BOSS_DEATH_EXCESS`.
* **Slightly off (descriptive only):** the `off` arm's by-act boss-entry counts (`bossesEnteredByAct` 127/124/118
  where the CSV implies 128/126/119), and its mean start HP and Smoke Bomb counts. `prod` seed 63000073 misses one
  non-boss fight in its mean start HP; the cand−prod boss-entry HP pairing is unaffected.

Future runs should write traces to local disk and copy them to the share at unit end.
