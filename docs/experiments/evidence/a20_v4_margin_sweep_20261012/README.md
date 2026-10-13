# §448 evidence: A20 V4 at A0, V4 margin sweep, and gold-decision breakdowns (2026-10-12)

Requested by Philipp in the project thread (2026-10-12): "we have a v4 model for a20, right? can we play 128
seeds on a0 with this model, no ooc search, no fallback to heuristic?", then "do a margin sweep, use 8 cloud
workers", then "can you help me analyze the heuristic vs v4 on the golden decisions? … where does the v4 do good
decisions, where bad, on which decisions?" and "do we have a similar overview for one of the stronger ooc mcts
runs?". Descriptive runs; nothing was pre-registered and no default changes.

## Frozen inputs

- Code: main `4a407a0c`, Release `one_combat` sha256 `f085352b…` (built in each container; `worker.sh` checks it).
- Models: A20 V4 = §419 round 1 + 2 Q-head retrain `v4_a20_r12.native` (sha256 `08d239f9…`, share only:
  `/mnt/project-files/v4-a20-retrain/models/`); A0 V4 = deployed `selfplay/models/ooc_strategic_tok_final.native`
  (`e62abd83…`). The retrain kept the A0 input normalization (ascension mean 0, inv 1e6), so at A0 its ascension
  input equals the original A0 training input.
- Base: the §422 `off` environment (exact-10k Silver, learned stop off, keys off, `STS_REST_WIN=0`, act-3 stop,
  OOC MCTS off), plus `STS_OOC_STRATEGIC_MAP=1`; every V4 gate on (rest + upgrade target, event incl. Neow, shop,
  treasure, boss relic, map; card rewards are always gated once V4 is loaded). `STS_OOC_STRATEGIC_MARGIN` varies.
  **The map gate is not part of the default stack**; it was added to approximate "no fallback to the heuristic".
- Seeds 81000000–81000127 (A0), smoke 81009000. Every arm in the sweep uses all 128 seeds (paired).

## Runs

- `first_run/`: A20 V4, margin 0, one container (`env.sh`, `unit.sh`, 16 units of 8 seeds, 4 in parallel).
  `analyze.py` matches the per-decision trace (`STS_OOC_DECISION_TRACE`) to the V4 gate trace
  (`STS_OOC_STRATEGIC_TRACE`) to list decisions V4 did not make. Raw: `/mnt/project-files/a20-v4-at-a0-448/runs.tar.gz`.
- `sweep/`: 13 arms (A20 V4 and A0 V4 at margins 0, 0.25, 0.5, 1, 2, 4; `heur` = A0 V4 at margin 1e6) on 8 cloud
  workers (`worker.sh`, brief `BRIEF-worker.md`; workers received brief sha `c519f6ea` plus the one-sentence
  watcher re-arm delta that became `1167470d`). Worker W ran seeds 81000000+16(W−1)..+15 for all arms. All 104 arm
  files rc 0, no seed failures; tars verified from a second container. `analyze_sweep.py` (paired bootstrap, 10,000
  resamples, RNG 20261012) reads the extracted tars and the first run. Tar hashes in `data-sha256.txt`.
- `gold2/`: offline breakdowns on the §432 Gold2 decisions (A20, 16 independent futures per option, `labelFloor`).
  V4 Q values come from the §432 `tsq.py` at 0 epochs with `tsq_qdump.patch` (dumps per-row Q; pip `torch` 2.14.1
  CPU); `gold_breakdown.py` scores them. `mcts_breakdown.py` scores the §425 OOC MCTS root picks
  (`../ooc_mcts_a20_gold_20261011/searches-*.jsonl.gz`, 4 searches per decision, unowned searches fall back to the
  heuristic) on the same Gold2 labels; decisions whose search option set does not contain every gold option are
  skipped (1), as are decisions without searches (11). Scripts expect the extracted Gold2 table at
  `/root/gold/gold2.csv` (concatenation of `gold2-w*.tar.gz` `out/s-*.csv`, 108,579 rows).

## Results

See ledger-06 §448. `first_run/SUMMARY.txt`, `sweep/SUMMARY.txt`, `gold2/REPORT.md` and `gold2/REPORT-mcts.md` hold
the full tables.
