# 2026-08-09 — S3 fair forced-move budget pool redirect (STS_S3_POOL_REDIRECT)

Date: 2026-08-09
Session/task: Implement the forced-move-only budget pool redirect for the S3
fair path, isolating the clean sub-case of the falsified STS_CONV_ROOT
experiment (§118).

## Decision

Added `STS_S3_POOL_REDIRECT` (default off, opt-in). When enabled in
`ScumSearchAgent2::playoutBattleFair`'s Searcher3 branch, each forced-move
decision (the §120/§121/§123 contraction, default ON) donates its unspent
base sim budget to a per-fight `fightPool`; each non-forced decision then
searches with `baseSims + min(fightPool, baseSims)` (poolFrac 1.0). The
pool is pure budget redirect — **no stability-based early stopping** — so
the §118 falsified line is not revived; this is the clean forced-move-only
sub-case §118 never isolated.

## Rationale

The forced-move contraction is decision-neutral (0/256 per-seed diffs,
§120/§121/§123) and saves −8.5% cpu in the S3 fair path, but the saved sims
were discarded. Redirecting them to genuinely ambiguous decisions is a
budget-neutral way to spend the same total compute where it helps, without
the stability-stop heuristic that lost −2.3pp at §118. Gated opt-in so the
default configuration is untouched and byte-identical when off (**Inference**:
reinvesting saved sims into non-forced decisions could help, hurt, or be
neutral; the paired gate is the arbiter — the §118 result does not predict
this sub-case because that arm bundled the stability stop with the pool).

## Alternatives considered

- Revive the §118 root-stability stop with the pool — rejected: already
  falsified at 256 paired seeds (−2.3pp); the plan explicitly forbids it.
- A poolFrac env knob — deferred: poolFrac is a code-level 1.0 constant for
  now; the plan only requested the `STS_S3_POOL_REDIRECT` gate.
- Auto-donate to the pool whenever forced moves occur (no flag) — rejected:
  breaks decision parity for all existing fair-S3 results; opt-in keeps the
  §123 configuration intact.

## Evidence

- `src/sim/search/ScumSearchAgent2.cpp` — `playoutBattleFair`, S3 branch:
  `fightPool` donation + spend.
- `include/sim/search/BattleScumSearcher3.h` + `src/sim/search/BattleScumSearcher3.cpp` — `g_s3PoolRedirect` global (default false).
- `apps/one_combat.cpp::main` — parse next to `STS_S3_BELIEF`.
- 8-seed smoke (`bestbench 300 8 0 126700`, fair S3−belief−chain/64p):
  ON 25.0% vs OFF 37.5%, 4/8 per-seed outcome flips (noise-dominated at
  300 sims); parity: unset vs `=0` per-seed-identical on all outcome
  columns. EXPERIMENTS.md §143; paired 256-seed gate pending.
- `docs/knowledge-base/architecture/combat-search.md` — forced-action
  contraction section documents the flag and the §118 non-revival.

## Status and follow-up

- Implemented, opt-in, default off; §143 paired gate pending (orchestrator).
