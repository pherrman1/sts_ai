# Mirror-trained prior F at real searched map roots (offline, 2026-10-24)

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

Agreement with pi' (all map roots): student_sel 87.2%, F 83.9%. Median visits at departures: student_sel's move
2,631, F's 1,115. dP uses the gen-3 root_v calibration (as `az_gen3_train_20261022/flip/margins.py`).

## Interpretation

F would change about one map decision in eleven (one in four at act start). At those roots the two moves are
near-ties: median |dq| 0.012, about the typical gap between the two best visited candidates (0.011, §643), and F's move
has the higher root q almost half the time (49% at act start). On average F's move is slightly worse (−0.3 pp
P(Heart kill) per departure). The search played student_sel's move 79% of the time, but that verdict is biased
toward the guiding prior: it got 2.4x the visits. With ~0.36 departures per run at about −0.3 pp each, the expected
effect of swapping the prior is about −0.1 pp Heart kills per run, an order of magnitude below what a 1,024-pair A/B
resolves (±2.7 pp, §621). So the column bias costs nothing measurable in play, and F is no better at real roots.
Caveat: root q comes from searches guided by student_sel (prior and rollouts), so F's moves are less explored.
