# Decision log

Last verified: 2026-08-02 against the current working tree.

This is the chronological, dated record of decisions made while working with
LLM coding agents. Every session that makes a significant choice appends one
entry file before the session closes. It is intentionally lightweight: a
decision is logged when it is made, and unverified reasoning must be labelled
**Inference**, **Unverified**, or **Open question** rather than omitted.

## When to log

Log an entry when a session decides or learns any of:

- an architecture or design choice — code structure, algorithm, interface,
  schema, environment variable, or deployed configuration;
- a process or tooling choice — agent workflow, commands, tools, conventions;
- a notable rejected alternative and the reason it was rejected;
- a new fact or correction to prior understanding, including anything that
  should later be promoted to a knowledge-base page.

Write the entry before the session closes. Never rewrite an earlier entry;
append a new entry or explicitly supersede the logged decision instead.

## Entry format

One file per session or task: `YYYY-MM-DD-<slug>.md`. Copy
[`_template.md`](_template.md). Each entry contains:

- date and task or context;
- the decision actually made;
- rationale, labelled **Inference**, **Unverified**, or **Open question** when
  not directly verified;
- alternatives considered and why they were rejected;
- evidence with repository-relative paths plus a class, function, executable,
  test, or script name;
- status and follow-up.

Keep entries short. When a fact stabilizes, promote it to the relevant
knowledge-base page in the same change instead of expanding the entry.

## Relationship to other records

- `decisions/` holds durable, evidence-backed architectural decision records.
  This log is the chronological source; a logged decision is distilled into
  `decisions/` only when its rationale is directly supported by repository
  evidence.
- `EXPERIMENTS.md` holds benchmarked policy/model results. A logged decision
  may reference an experiment entry; it does not replace the ledger.
- `investigations/` holds reproducible unresolved diagnoses. A reproducible
  open question in this log may be promoted there.
- `docs/archive/` holds dated plans and superseded schemas; it is not current
  instruction.

## Index

Reverse chronological; one line per entry file.

| Date | File | Topic |
| --- | --- | --- |
| 2026-08-03 | [`2026-08-03-b1-shop-beam.md`](2026-08-03-b1-shop-beam.md) | B1 shop beam search (§2): `oocShopBeamPolicy` behind `STS_OOC_SHOP_BEAM=1` (width 32/depth until-leave/budget 4096), V3/token leaf heads, StratFingerprint+offer-set dedup, replaces the one-ply shop gate when enabled. |
| 2026-08-02 | [`2026-08-02-hidden-info-audit.md`](2026-08-02-hidden-info-audit.md) | Hidden-information boundary audit (plan 5.6.4, §A.14): Searcher3 fair machinery clean and deterministic; strategic layer leaks (future-encounter features, CF branches copying true run streams) flagged in apps/one_combat.cpp, outside fix scope; TREASURE chest-size heuristic risk flagged; no fixes applied. |
| 2026-08-02 | [`2026-08-02-mermaid-diagrams.md`](2026-08-02-mermaid-diagrams.md) | Added mermaid diagrams to docs: replaced 5 ASCII diagrams (kept ASCII only in ooc-strategic-v4) and illustrated 6 prose-only data-flow sections. |
| 2026-08-03 | [`2026-08-03-ooc-next-wave.md`](2026-08-03-ooc-next-wave.md) | Next wave: V4 full-gate stack top arm (41.4%, +20.3pp), margin 1.0 + 256-block confirmation, mixture below K=3, shop beam negative, Phase-B encoder neutrals, C_psi export fix, hidden-info audit. |
| 2026-08-02 | [`2026-08-02-ooc-wave-r6-r8.md`](2026-08-02-ooc-wave-r6-r8.md) | OOC wave: R6 one-ply gates for shop/treasure/boss relic (+18.8pp, first statistically established result), R7 Q-iso verdict (token state encoder, not the Q head, caused V4 calibration gap), K=1 label horizon better Q calibration, seed-128087 isolation. |
| 2026-08-02 | [`2026-08-02-phase5-round5-token-state-v4.md`](2026-08-02-phase5-round5-token-state-v4.md) | Phase-5 round 5: token-based run state (V4) delivered (A1–A4); held-out ranking beats V3 but the deployed gate (+3.1pp @ m5) does not — V3 stays default, V4 opt-in. |
| 2026-08-02 | [`2026-08-02-ooc-guideline-spec-of-record.md`](2026-08-02-ooc-guideline-spec-of-record.md) | OOC guideline adopted as spec of record; new action plan supersedes archived Phase 5; design distilled into KB + decisions record. |
| 2026-08-02 | [`2026-08-02-phase5-round3-tierb-q-labels.md`](2026-08-02-phase5-round3-tierb-q-labels.md) | Phase-5 round 3: Tier-B one-ply labels, Q-head gate, V3 format; V2 value-head misalignment correction. |
| 2026-08-02 | [`2026-08-02-determinism-verification.md`](2026-08-02-determinism-verification.md) | Verified fair replay is bit-identical; closed issue 10. |
| 2026-08-02 | [`2026-08-02-issue-fixes.md`](2026-08-02-issue-fixes.md) | Fixed 24 of 30 tracked issues via parallel subagents; benchmarked the default fair stack (§68). |
| 2026-08-02 | [`2026-08-02-issue-tracker.md`](2026-08-02-issue-tracker.md) | Created the prioritized knowledge-base issue tracker. |
| 2026-08-02 | [`2026-08-02-karpathy-coding-guidelines.md`](2026-08-02-karpathy-coding-guidelines.md) | Merged Karpathy coding guidelines into AGENTS.md. |
| 2026-08-02 | [`2026-08-02-decision-log-setup.md`](2026-08-02-decision-log-setup.md) | Established the decision log and the knowledge-base usage contract. |
