# Refactor-on-contact candidates

Last verified: 2026-08-08.

These are cleanup opportunities that were **deliberately deferred** during the
2026-08-08 surgical refactor pass. Each has a specific trigger condition: when
future work naturally touches the affected code, reconsider the cleanup. Do
**not** proactively seek out these changes — the cost of a standalone change
exceeds the benefit.

---

## `g_devalueHighHp` dead code in Searcher2

**Trigger:** any future change to `include/sim/search/BattleScumSearcher2.h`,
`src/sim/search/BattleScumSearcher2.cpp`, or the `evaluateEndState` function.

**What to remove:**
- `extern bool g_devalueHighHp` declaration in the header (line ~143)
- `bool g_devalueHighHp = false` definition in the `.cpp` (line ~27)
- The `if (g_devalueHighHp) { … }` block in `evaluateEndState` (the concave-HP
  term that is now always false)

**Why deferred:** the flag is harmless and always false; removing it would
touch the search layer for a pure cleanup task. The `evalcombat`/`evalrun`
modes that were the only setters were removed in the 2026-08-08 refactor
(`apps/one_combat.cpp`).

**Evidence:** `docs/knowledge-base/architecture/combat-search.md` Known
limitations; historical evidence .

---

## `computeEdgePriors` duplication (Searcher2 vs Searcher3)

**Trigger:** any future change that modifies the prior-computation logic in
either `src/sim/search/BattleScumSearcher2.cpp::computeEdgePriors` or
`src/sim/search/BattleScumSearcher3.cpp::computeEdgePriors` (free function).

**What to consider:**
- Both versions share ~95% of their logic: extract combat features once,
  softmax over PVNet policy head (when available), else GBM policy net fallback.
- The only difference: S2 caps the GBM fallback at 64 edges with stack arrays;
  S3 uses dynamic `std::vector<double>` with no cap.
- If either version changes, extract the common logic to a shared free function
  (templated on the Node/Edge type, or using a common prior-assignment
  interface) to prevent the two from silently diverging on the PVNet path.

**Why deferred:** hasn't caused a bug yet; the divergence is only in the GBM
fallback (which is rarely used when PVNet is loaded). Template/overload
complexity for a single shared function is disproportionate until a real change
forces the issue.

**Evidence:** 2026-08-08 audit; historical evidence .

---

## `runFullRun` vs `runFullRunOOC` — two parallel full-run paths

**Trigger:** any future change that modifies the full-run benchmark pipeline
(`bestBench`, `runFullRunOOC`, `ScumSearchAgent2::playoutBattle`,
`ScumSearchAgent2::stepOutOfCombatPolicy`).

**What to consider:**
- `runFullRun` (line ~235) is the older path used by `bench`/`run`/`runbench`
  legacy modes; it uses the `ScumSearchAgent2` heuristic OOC stack.
- `runFullRunOOC` (line ~2582) is the current path used by `bestbench` and all
  active experiments; it uses the native-OOC + gate-stack OOC policy.
- If a future change modifies both, consider whether one can become a thin
  wrapper around the other (e.g., `runFullRun` delegating to `runFullRunOOC`
  with hardcoded flag-equivalents for the old heuristic stack).

**Why deferred:** the two paths serve different RNG regimes (known-RNG vs
project-fair) and different OOC stacks. They're intentionally separate, and
consolidating them risks subtly changing historical benchmark semantics.

**Evidence:** `apps/one_combat.cpp`; historical evidence .

---

## Model-loading helpers in `main()`

**Trigger:** any future change that adds a new model artifact or modifies the
model-loading sequence in `apps/one_combat.cpp::main` (~L9208–L9965).

**What to consider:**
- Each model load follows the same pattern: `getenv`, conditional `load()`,
  `std::cout` diagnostic. Some have default-auto-enable logic (e.g., VNet
  default-ON for fair+S3, policy net auto-load).
- Small helper functions like `loadValueModel` already exist for a few models.
- If the model-loading block grows significantly or a new model needs
  default-auto-enable logic, extract the pattern into a consistent helper
  (e.g., `loadModelWithDefault(path, description, fallbackPath)`).

**Why deferred:** the current pattern is ~5–15 lines per model and is readable
inline. Extracting prematurely would hide the load order and precedence logic
behind abstractions.

**Evidence:** `apps/one_combat.cpp::main`; historical evidence .

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

**Evidence:** historical evidence .
