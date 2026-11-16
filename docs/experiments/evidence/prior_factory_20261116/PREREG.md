# Prior data factory (issue #1053 next prior): pre-registration (2026-11-16)

**What:** a data run, not a gate. It produces training data for the next combat prior (plan:
`/mnt/project-files/rollout-prior-next/PLAN.md`, sources A, B and C): G16 + mb4 whole-run games (D2's environment,
§775's G16 arm) recorded by `one_combat silverazgen`, with STS_AZGEN_EXTRA_LABELS=nodes:2,playouts:2,sims:2000,
minvisits:256 (record_env.sh):
- **A, roots:** every searched root, as D2 (edges with visits, Q, max-backed Q, g7f_E prior, Gumbel pick).
- **B, tree nodes:** per root up to 2 interior decision nodes of the played tree with at least 256 visits
  (PLAYER_NORMAL, more than one edge), drawn uniformly without replacement.
- **C, playout states:** per root up to 2 states that the search's playouts visited (reservoir sample).
- B and C are each labelled by a fresh 2,000-simulation Gumbel root search with the played search's configuration
  (g7f_E prior and playouts, k 16, max backup 4), written as rows of kind `extra`. Tree rows also carry the played
  tree's edges at that node.

**Authorization:** Philipp, 2026-11-16 00:46 CET (32 workers, open-ended until he says stop, hard cap 24 h).

**Seeds:** new block 113200000-113204095 (units of 2 runs, in order). 113299990-113299999 are smoke seeds. The
block 1132xxxxx appears nowhere else in the repository except inside model weight files.

**End:** the author writes the share's `STOP_AT` at launch (launch + 22 h, so that running units end by about
24 h) and creates `STOP` earlier on Philipp's word, or when the share's total use reaches 9.0 GB (10 GB quota;
about 1.3 MB per run). The run is then a finished campaign: data verified with `verify_campaign.py` (units never
claimed are listed missing, as expected), moved off the share for training, and continued in a new batch if
Philipp's go still holds.

**Smoke (author, 2026-11-16, code a002b841, seed 113299990, release build):** 801 root rows and all 32 fight rows
identical with and without the extra labels (only the teacher id differs, `-xl2n2p2000`); 2,842 extra rows (1,412
tree, 1,430 playout), 3.5 per root; label search 0.054 s each; wall 855 s vs 678 s (+26 %, the labels add 23 % CPU);
jsonl 46 MB, 2.06 MB gzip, 1.29 MB xz -6.

**Checks per unit (run_unit.sh):** the manifest's production chain, production combat, whole-run Gumbel root with max
backup 4, Act 4 strong and the extra-label settings; net-0420 loaded; seeds inside the block.
