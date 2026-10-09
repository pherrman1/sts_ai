# A20 synthetic Silver corpus: plan (2026-10-09, draft, nothing large run yet)

Philipp (2026-10-09 00:45Z): "Can we do something like the silver synthetic
data thread but for A20 instead of A0?" Also wants the A20 second boss fought.

## Verified facts (450376c8, the frozen A0 corpus generator)
- `one_combat silversynthgen N SIMS ASC ...` already takes ascension; it
  builds `GameContext(IRONCLAD, seed, asc)` (silver_synth_gen.cpp:271) and
  plays each run until the game ends, with no stop-after-act rule.
- The simulator plays the A20 second Act 3 boss itself
  (GameContext.cpp:604, :1215). No generator change or PR is needed.
- Wire states carry `ascension`, and the combat features include it
  (CombatValueNet.cpp:281), so A0 and A20 rows can be mixed in one model.
- Binary rebuilt from 450376c8 in a fresh cloud container: sha256 8906180f…,
  identical to the A0 corpus binary. Same teacher.json. Only ASC differs.
- Seeds: 60M range unused in the ledger. Smoke used 60009000-60009017.

## Smoke (18 natural + 2 perturbed runs, seeds 60009000-017, ASC=20)
Files: smoke-450376c8/. 0 errors, ascension 20 in every wire.
- 9.8 fights/run (A0 corpus: 21.4), ~180 roots/run (A0: ~400).
- Fights by act: Act 1 127, Act 2 38, Act 3 12 (72% Act 1).
- Deaths: 11/18 in Act 1 (Sentries, Nob, Lagavulin, Act 1 bosses),
  5 in Act 2, 1 in Act 3. Seed 60009006 beat both A20 Act 3 bosses
  (Time Eater, then Awakened One).
- Cost: ~1 CPU-min per natural run (A0: ~3.3); perturbed ~1.5x.

## Proposed corpus (needs Philipp's go; the coordinator starts workers)
20 cloud workers x 4 cores, brief BRIEF-worker.md:
natural 60000000-60001079, perturbed 60002000-60003079 (2,160 runs).
Expected: ~21k fights, ~390k roots (about 2x the A0 1x corpus), ~1.5k Act 3
fights, ~250 Act 3 boss fights and ~100 second-boss fights (extrapolated
from 2/18 runs reaching Act 3 bosses; rough). ~1 h wall per worker after a
~25 min build.

Weakness: natural A20 runs are mostly Act 1. If late-act / boss coverage turns
out to matter, a follow-up "A20 shadow" variant (small PR, default off, A0
output byte-identical) could record every fight of an A0 trajectory as a
detached A20 copy (ascension 20 + Ascender's Bane), plus an extra A20 second
boss after the Act 3 boss. Not proposed until the gate below says A20 differs.

## Decision rule (offline, pre-register before looking at test folds)
Folds by source seed: (seed - base) % 5, base 60000000 natural / 60002000
perturbed; train 0-2, val 3, test 4 (same scheme as §397/§400).
T1 transfer: on A20 test roots, top-1 agreement with the 10k pick for
  (a) existing A0-trained prior v2 (prior-v2-20261008/prior-v2.txt),
  (b) v2 recipe trained on A20 train folds, (c) trained on A0 + A20.
  - If (b) or (c) beats (a) by >= 3pp with the seed-clustered 95% CI
    excluding 0: A20 search behaviour is not captured by A0 data; go to T2.
  - If within 3pp: A0 combat knowledge transfers; A20 rows only become extra
    encoder training data. Stop the A20-specific prior route.
  Also reported: by act, bosses only, second boss only (descriptive).
T2 replay at A20: silversynthreplay on A20 test roots, budgets 256/1k/2k;
  pass = regret at 2k below plain with CI excluding 0. Only after a pass:
  propose an online A20 screen on fresh seeds (Philipp's word).

Context: at A0 the prior route was a compute saving only offline (§397) and
negative online (§399); §400 v2 ties v1 at 2k. The expectation here is modest.
A20 is where the agent loses (0/32 with the second boss, #346), so a lever
there is worth more than at A0.
