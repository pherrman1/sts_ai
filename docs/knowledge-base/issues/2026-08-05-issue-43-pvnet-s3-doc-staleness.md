# Issue 43: STS_PVNET / STS_S3_* documentation is stale or absent

- **Status:** closed
- **Tier:** Medium
- **Last verified:** 2026-08-05
- **Source:** code review 2026-08-05; knowledge-base + AGENTS.md

## Symptom

- `combat-search.md:102-104` and `AGENTS.md` claim "`STS_DIST_VNET` and
  `STS_PVNET` are consumed only by Searcher3 ... does not make default
  Searcher2 use it". The in-flight S2-PVNet priors wiring makes the PVNet half
  false (default Searcher2 consumes the PVNet policy head when `STS_PVNET` is
  set and not value-only).
- The five `STS_S3_*` ablation flags were documented nowhere until the
  concurrent 2026-08-05 session's §106 write-up; even that text describes
  `STS_S3_LIVE=0` with the pre-fix "most-visited-then-fallback" semantics and
  CRN as unguarded.

## Evidence

- `docs/knowledge-base/architecture/combat-search.md` (env-var list, PVNet claim).
- `AGENTS.md` ("Critical safety and correctness traps").
- `src/sim/search/BattleScumSearcher2.cpp:434-458` (S2 PVNet priors).

## Why it matters

Doc drift misleads future sessions (AGENTS.md's own "authoritative sources"
contract) and hides that `STS_PVNET` means different things per searcher
(S2: priors-only; S3: priors + leaf value; `VALUE_ONLY` inert in S2, PUCT-quirk
in S3).

## Candidate fix direction

Update both docs in the same change as the code; document the ablation flags
and their per-arm semantics; note the S2/S3 divergence.

## Relevant code

- `docs/knowledge-base/architecture/combat-search.md`
- `AGENTS.md`

## Resolution (2026-08-05)

Fixed in the 2026-08-05 code-review working tree: `combat-search.md` env-var
list and PVNet-consumption claims updated, `STS_S3_LIVE` semantics corrected,
CRN guard noted; AGENTS.md trap line corrected; ablation §106 entry updated.
