# Decision-flip check (review of #814)

Inputs: validation-fold (seed % 8 == 7) runs of the gen-3 window. The policy rows come from the data branch
`claude/az-gen2-data` (`gen2/rows`, plus `gen3/rows_new` converted by `../tools/convert_vtargets.py`). The raw
captures are:
- gen 0 tars: data branch `claude/az-gen0-data` `54033d1` (`gen0/`);
- gen-1b A/B tars: data branch `gen2/raw-gen1b-ab`;
- gen-2 A/B and exploration unit tars: share `az-gen2-ab/units`, `az-gen3-explore/units`.

Nets: student_sel `cf6bf7fb`, gen-2 pick `fc32d8f4`, gen-3 pick `d5780dee`. Scoring: `one_combat heart1score BIN
records.jsonl out_{sel,g2,g3}.jsonl` with `STS_OOC_HEART1_WING_BOOTS_COUNTER=1`.

1. `python3 build.py DIR student_sel ROWDIR...` collects the policy rows of runs searched with student_sel. With `gen2`
   in place of `student_sel` it collects the gen-2 B arm instead. Score the rows, then run `analyze.py DIR`
   (`student_sel_searched.txt`, `gen2_searched.txt`).
2. `python3 margins.py DIR RAW_TAR...` adds root q, visits and the played move at the departures
   (`margins_*.txt`).
3. `python3 fastroots.py build DIR RAW_TAR...`, score, then `fastroots.py report DIR` cover the searched roots without
   a policy row (`fast_margins.txt`).
4. `python3 agree.py FLIPDIR FASTDIR` reports gen 3 vs gen 2 agreement (`agree.txt`).
