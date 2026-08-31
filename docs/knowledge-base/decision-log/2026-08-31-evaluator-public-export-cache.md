# 2026-08-31 — Evaluator public-export cache

Date: 2026-08-31
Session/task: Reduce repeated coding-agent candidate preparation cost.

## Decision

Cache the immutable public tracked export below evaluator-owned runtime state,
keyed by source `HEAD` and the exact `json` and `pybind11` gitlink revisions.
Publish a cache entry atomically only after submodule-pin validation, hidden-data
removal, and content/path/executable-mode tree hashing. Validate its manifest
and tree digest on every hit and revalidate the materialized candidate copy.
Archive the captured root and submodule SHAs directly so dirty or changing
source worktrees cannot alter bytes under that identity. Materialize candidates
as ordinary independent files and create their sole
root commit only after task mutation, hidden-data verification, and optional
skill overlay.

## Rationale

Repeated `git archive`, extraction, and submodule materialization duplicated
the same public source work for every full preparation. The cache is below all
task-specific mutation while preserving standalone candidate repositories and
the hidden-object boundary.

## Alternatives considered

- Shared clones, alternates, or borrowed object stores — rejected because a
  candidate would depend on external object ownership and lifetime.
- Writable hardlinks — rejected because candidate mutation could affect another
  candidate or the cache.
- Caching a prepared Git repository — rejected because task mutations, skill
  overlays, or hidden evaluator objects could cross the cache boundary.

## Status and evidence

Implemented with opt-in phase timing through `STS_AGENT_EVAL_TIMINGS=1`.
Candidate isolation and cache fail-closed behavior remain covered by the full
real-preparation evaluator regression. Final native-ext4 and hosted Linux timing
evidence belongs in the draft PR evidence packet.
