# Mirror-trained prior F at real searched map roots: near-ties, sign of the q gap not identified (offline, 2026-10-24)

Follow-up to §677. Philipp (2026-10-24 07:56Z): run the offline check before any A/B. Question: in real A20 play,
how often would F (`student_mirror50.bin` `acc9051e…`) pick a different map move than student_sel (`cf6bf7fb…`), and
what did the production search find at those roots?

## Data

- Policy rows: data branch `claude/az-gen2-data` `43ad57f0`, `gen2/rows`, runs searched with student_sel as OOC prior
  (gen 0 and gen-1b arm A; `az-b-` = gen-1b arm B skipped): 2,176 A20 runs, 8,745 searched map roots with >= 2 paths.
  `logits` there = the search's improved policy pi' (Gumbel completed-Q target).
- Raw captures for root q / visits / played move: gen 0 tars (`claude/az-gen0-data` `54033d10`, `gen0/`) and gen-1b
  tars (`claude/az-gen2-data` `gen2/raw-gen1b-ab/`). Every departure matched its root (792 of 792).
- Scoring: `one_combat heart1score` (binary `b855ee27`) with `STS_OOC_HEART1_WING_BOOTS_COUNTER=1`. Script `roots.py`
  (`build`, `report`, `margins`); outputs `report.json`, `margins_summary.json`; hashes `inputs.sha256`.

## Result

| map roots | n | F ≠ student_sel | at departures: search played sel / F / other | F's move higher root q | mean dq (F − sel) | mean dP(kill) | median abs dq |
|---|---|---|---|---|---|---|---|
| all | 8,745 | 792 (9.1%) | 628 / 137 / 27 | 45.6% | −0.0059 | −0.0031 | 0.012 |
| act start | 1,323 | 362 (27.4%) | 285 / 53 / 24 | 48.9% | −0.0058 | −0.0033 | 0.012 |
| mid act | 7,422 | 430 (5.8%) | 343 / 84 / 3 | 42.8% | −0.0060 | −0.0030 | 0.012 |

By the visits F's move got (the search was guided by student_sel, so F's move is often barely explored):

| visits of F's move | n | mean dP(kill) F − sel | F's move higher q | search played F |
|---|---|---|---|---|
| < 100 | 77 | −3.6 pp | 24.7% | 0 |
| 100–499 | 130 | −2.0 pp | 20.0% | 0 |
| 500–999 | 150 | −1.1 pp | 22.7% | 0 |
| >= 1,000 | 435 | +1.0 pp | 64.8% | 137 |

Agreement with pi' (all map roots): student_sel 87.2%, F 83.9%. Median visits at departures: student_sel's move
2,631, F's 1,115. dP uses the gen-3 root_v calibration (as `az_gen3_train_20261022/flip/margins.py`).

## Interpretation

F would change the prior's top map move at about one root in eleven (one in four at act start). At those roots the two
moves are near-ties: median |dq| 0.012, about the typical gap between the two best visited candidates (0.011, §643).
The sign of the gap is not identified: pooled, F's move is −0.3 pp P(Heart kill), but that pooled figure is driven by
moves the student_sel-guided search barely explored (−3.6 to −1.1 pp below 1,000 visits); where F's move got at least
1,000 visits (435 roots) it is +1.0 pp and has the higher q 65% of the time. That is search-selection bias in both
directions, so this data cannot say whether F's moves are better or worse. The search played student_sel's move 79%
of the time, a verdict biased toward the guiding prior (2.4x the visits).

A departure is a change of the prior's argmax, not of the played move: the search would still pick among the same
candidates. A rough heuristic for the play effect: ~0.36 departures per run times |dP| of about 1 pp is at most
~0.4 pp Heart kills per run in either direction, below what a 1,024-pair A/B resolves (±2.7 pp, §621). Hence no A/B.
