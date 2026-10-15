# Pre-registration: Silver Smoke Bomb escape penalty vs escape scored as a win, paired whole runs (ledger §473)

Written and committed before any cohort seed ran. Philipp, 2026-10-14 15:26Z, in the thread "Flag audit", after the
audit of default-off flags (`/mnt/project-files/flag-audit/AUDIT-2026-10-14.md`, item 5): "5 können wir gerne testen".
Worker count: [NWORKERS](NWORKERS) (Philipp's pick; the number committed here is a proposal until he picks one, and
the run commit may change only that file).

## Question

Silver scores a Smoke Bomb escape exactly like a win (`SilverSearcher::evaluateEndState`), although the escape forfeits
the fight's rewards. A unit fixture shows Silver fleeing Cultist and Jaw Worm at full HP; about 2,900 escapes appear in
the 510k-fight Silver corpus (`architecture/combat-search.md`). Does charging the forfeited rewards play better whole
runs?

## Arms ([arm_env.sh](arm_env.sh))

Both arms are the §422/§433 `off` environment (exact-10k live Silver, V4 OOC policy, OOC MCTS off, keys off,
`STS_STOP_AFTER_ACT=3`) on the ADR-0034 defaults (optional Recall filter and canonical multi-select masks on), plus:

| arm | `STS_SILVER_ESCAPE_PENALTY` |
|---|---|
| `base` | `0,0` (escape = win; the current default) |
| `escape` | `12,35` (normal and elite-trigger fights) |

The penalty is subtracted from an escape's victory score and capped at half the HP left. **The values are fixed
here, not tuned.** Reasoning in Silver's own units (potion 11, gold 0.25 per gold): a normal fight's rewards are about
15 gold (≈4), a 40% potion chance (≈4.4) and a card reward (≈4) → 12; an elite adds a relic and more gold → 35.
**Inference**, not a fitted value.

## Provenance

- Code commit [CODE_COMMIT](CODE_COMMIT) (main cfd843c2 plus ADR-0034, PR #540); workers build `one_combat` and refuse to run
  unless its sha256 equals [binary.sha256](binary.sha256). The run commit may differ only in docs and tools.
- Cohorts ([COHORT](COHORT)): **A0 seeds 102000000–102000499** and **A20 seeds 102000500–102000999**, fresh, both arms
  on every seed (coordinator-assigned 102000000–102000999). Seed i of the concatenated list goes to worker
  (i mod NWORKERS) + 1. Smoke seeds 74070750–74070767 ([SMOKE.md](SMOKE.md); 74070768–799 unused); pre-launch reviewer seeds
  74070800–74070849.
- Per-unit timeout 4 h. A seed drops out of its cohort's pairs (in both arms; counted in the report; no rerun or
  replacement) when either arm's unit (a) names a `[bestbench-seed-failure]` in its log, (b) ends with rc=124 (4 h
  timeout), or (c) has a worker stall record `stall-ARM-aASC-SEED.txt` (log silent 60 min, backtrace taken, process
  killed; brief §3).

## Analysis ([tools/analyze_silver_escape_473.py](../../../../tools/analyze_silver_escape_473.py))

Pairs: cohort seeds with a row in both arms. Paired seed bootstrap 95% CI, 10,000 resamples, RNG 473 (A0) / 493 (A20).
- **Primary A0:** Δwin = win(escape) − win(base).
- **Primary A20:** Δfloor = floor(escape) − floor(base).
- Each: **BETTER** if the CI lower bound > 0, **WORSE** if the upper bound < 0, otherwise **NOT_SHOWN**.
- Secondary (descriptive): the other metric per cohort, exact McNemar, end HP, boss deaths, seconds per run, pairs
  reaching floor 50, and pairs whose rows differ at all (most runs never hold a Smoke Bomb, so most pairs should be
  identical up to RNG divergence after the first escape decision).

**Reading.** Most runs are unaffected, so the test has little power: 500 pairs resolve about ±3.5 pp of A0 win rate
and about ±1 floor at A20 (Inference, from §471's design). NOT_SHOWN does not mean equal.

## Validity

All units rc=0 apart from the dropped seeds above; any other nonzero rc, crash, missing seed, non-cohort seed, or a
unit whose `.env` does not set `STS_SILVER_ESCAPE_PENALTY` to its arm's value or sets `STS_OOC_SKIP_OPTIONAL_RECALL` /
`STS_MULTISELECT_CANONICAL` makes the result INVALID (the analyzer checks all of these).

## Decision

- **BETTER** in either cohort and not WORSE in the other: propose `12,35` as the default (ADR); Philipp decides.
- **NOT_SHOWN** in both: Philipp decides on principle (as for ADR-0030/0031); no further tuning of the values on these
  seeds.
- **WORSE** in either cohort: the penalty stays off.
