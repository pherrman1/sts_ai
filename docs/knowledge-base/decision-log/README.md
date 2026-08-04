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
| 2026-08-04 | [`2026-08-04-phase-f.md`](2026-08-04-phase-f.md) | Phase F search distillation (5.7.1+5.7.2): soft-target policy objective falsified on the gate A/B — every policy-score arm loses to the Q-gate (~+3..+27pp) and the 39.8% reference (best −21.1pp); tie-dominated labelWon caps the ranking signal; `STS_OOC_STRATEGIC_SCORE` stays opt-in, 5.7.3 unchecked, K=6 targets the open follow-up. |
| 2026-08-04 | [`2026-08-04-dynamic-sim-budget.md`](2026-08-04-dynamic-sim-budget.md) | Dynamic sim budgets: convergence early stop inert under fair play (bit-identical to flat, 3 settings); C_psi difficulty-adaptive per-fight budget (`STS_SIM_ADAPT=1`) delivered — +1.8pp win / −12% compute vs flat@2k over 767 seeds (not significant), ties V4@3k on one block at −39% compute; not promoted. |
| 2026-08-04 | [`2026-08-04-combat-side-wave.md`](2026-08-04-combat-side-wave.md) | Combat-side wave: fair 1,500-tree vnet rejected under the gate stack (α0.3 −3.1pp, α0.5 tie, at 3.2× cpu); 4,000-sim fair budget of the gate stack statistically established (+7.4pp win / +2.7 floor / +4.2 HP on 256 paired seeds); V4@3k arm open. |
| 2026-08-04 | [`2026-08-04-qwin-wave-a1.md`](2026-08-04-qwin-wave-a1.md) | Wave A1 Q_win: probability action-value head (BCE on labelWon) + Q_HP/Q_floor aux heads, OOC_STRAT_V5 artifact (V3 kept loadable, refs bit-identical), fresh 1.9 GB tierb datagen on GCP, V3 retrain on laptop CPU (early stop, best epoch 24, q_brier 0.053), V_win bootstrap found grossly miscalibrated (Brier 0.232, max decile err 0.42) — recalibration decision open. |
| 2026-08-04 | [`2026-08-04-ooc-map-route-wave.md`](2026-08-04-ooc-map-route-wave.md) | Map-route wave: M1 one-ply map Q gate negative at every margin (−15.6..−19.5pp, direct-Q-per-route falsified on V3), C1 V4 on the 256-block holds (41.0%, +3.9pp vs V3), M2 C_psi route search negative (−3.1..−21.1pp; heuristic pathing stays), S1 scrub blocked on training-data location. |
| 2026-08-03 | [`2026-08-03-trainer-throughput-v4.md`](2026-08-03-trainer-throughput-v4.md) | V4 trainer throughput: GPU-resident state (default ON, CPU fallback on OOM), fused per-screen value/quantile heads (math-identical, verified 1 ulp), eval chunks, expandable_segments, torch.compile `mode="default"` default ON (needs python3-dev; 2.15x step, CUDA graphs unusable, suppress_errors fallback); fp16/TF32 rejected with measurements; ~40 → ~16 min per 40 epochs, metrics & export parity unchanged; best-state indentation bug fixed. |
| 2026-08-03 | [`2026-08-03-ooc-per-screen-margins.md`](2026-08-03-ooc-per-screen-margins.md) | Per-screen one-ply gate margins: `STS_OOC_STRATEGIC_MARGIN_{CARD,REST,EVENT,SHOP,TREASURE,BOSS_RELIC}` overrides (sentinel -1.0 = fall back to the global margin; verified bit-identical when unset/explicitly 1.0). |
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
