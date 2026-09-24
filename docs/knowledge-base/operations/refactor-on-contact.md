# Refactor-on-contact candidates

Last verified: 2026-09-24 (Searcher2 entries removed with Searcher2, ADR-0020); 2026-09-07.

These are cleanup opportunities that were **deliberately deferred** during the
2026-08-08 surgical refactor pass. Each has a specific trigger condition: when
future work naturally touches the affected code, reconsider the cleanup. Do
**not** proactively seek out these changes — the cost of a standalone change
exceeds the benefit.

---

## `runFullRun` vs `runFullRunOOC` — two parallel full-run paths

**Trigger:** any future change that modifies the full-run benchmark pipeline
(`bestBench`, `runFullRunOOC`, `ScumSearchAgent2::playoutBattle`,
`ScumSearchAgent2::stepOutOfCombatPolicy`).

**What to consider:**
- `runFullRun` is the older path used by the retained `run` mode; it uses the
  `ScumSearchAgent2` heuristic OOC stack.
- `runFullRunOOC` (line ~2582) is the current path used by `bestbench` and all
  active experiments; it uses the native-OOC + gate-stack OOC policy.
- If a future change modifies both, consider whether one can become a thin
  wrapper around the other (e.g., `runFullRun` delegating to `runFullRunOOC`
  with hardcoded flag-equivalents for the old heuristic stack).

**Why deferred:** the two paths serve different RNG regimes (known-RNG vs
project-fair) and different OOC stacks. They're intentionally separate, and
consolidating them risks subtly changing historical benchmark semantics.

**Evidence:** `apps/one_combat.cpp`; decision log `2026-08-08-surgical-refactor.md`.

---

## Model-loading helpers in `main()`

**Trigger:** any future change that adds a new model artifact or modifies the
model-loading sequence in `apps/one_combat.cpp::main` (~L9208–L9965).

**What to consider:**
- Each model load follows the same pattern: `getenv`, conditional `load()`,
  `std::cout` diagnostic. The Searcher2/3 combat-model loads and their
  default-auto-enable logic were removed (ADR-0019, ADR-0020).
- Small helper functions like `loadValueModel` already exist for a few models.
- If the model-loading block grows significantly or a new model needs
  default-auto-enable logic, extract the pattern into a consistent helper
  (e.g., `loadModelWithDefault(path, description, fallbackPath)`).

**Why deferred:** the current pattern is ~5–15 lines per model and is readable
inline. Extracting prematurely would hide the load order and precedence logic
behind abstractions.

**Evidence:** `apps/one_combat.cpp::main`; decision log `2026-08-08-surgical-refactor.md`.

---

## Findings summary maintenance

**Trigger:** the "Current findings summary" at the top of `EXPERIMENTS.md`
grows beyond ~80 lines, becomes stale, or is reported as a maintenance burden.

**What to consider:**
- Promote it to `docs/knowledge-base/evaluation/current-findings.md` and keep
  `EXPERIMENTS.md` purely chronological.
- Add a one-line cross-reference at the top of `EXPERIMENTS.md` pointing to the
  separate findings page.

**Why deferred:** the summary is currently 60 lines and was added in the
2026-08-08 refactor. Premature extraction would add an extra file for minimal
benefit. Wait for evidence that the inline summary is actually reducing agent
reads before deciding.

**Evidence:** decision log `2026-08-08-surgical-refactor.md`.
