# Decision log

Last verified: 2026-08-05 against the current working tree.

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
| 2026-08-05 | [`2026-08-05-v4-fixed-stats-retrain.md`](2026-08-05-v4-fixed-stats-retrain.md) | V4 fixed-stats retrain (issue 36): falsified on the gate — S2-paired −2.3/−3.9pp (n.s.), S3−belief−chain-paired **−8.98pp (p=0.028)**; deployed 05178ec8 stays, fixed model archived; glob scale now an active hyperparameter (§108). |
| 2026-08-05 | [`2026-08-05-model-artifacts-via-git.md`](2026-08-05-model-artifacts-via-git.md) | Deployable models now tracked via git: `selfplay/models/*.native` un-ignored (792K–1.6M, under GitHub limits); `*_state.bin`/checkpoints/buffers stay ignored (2.8–7.1 GB each) — retrained artifacts ship with their sha256 + docs in one commit, handoff between machines is pull-only. |
| 2026-08-05 | [`2026-08-05-s3-particles-sweep.md`](2026-08-05-s3-particles-sweep.md) | S3 particle × sims sweep: grid flat in particles (16/64/256) and flat-ish in sims (1k→3k +2-3pp, 4k noise); E1 closes the belief-capacity hypothesis (belief-ON @256 still −6.2pp); **S3−belief−chain promoted** — 60.2% (+14.8pp) @3k/256p and 57.4% (+12.1pp) @1k/64p vs the §99 45.3% ref, both CIs excluding zero on 256 paired seeds. |
| 2026-08-05 | [`2026-08-05-code-review.md`](2026-08-05-code-review.md) | Code review of the recent model stack + in-flight S3-ablation/S2-PVNet diff: 13 critical/high bugs fixed (probe_cpsi normalization, PVNet untrained heads + token layout, calibration split leak, S3 encode overflow, state.bin fingerprint, tok glob stats, exporter config flags, dist val selection, checker map-enc, g_s3Live semantics, CRN re-warm guard), bestbench-append trap found, rerun ledger created, issues 31–46 recorded. |
| 2026-08-05 | [`2026-08-05-s3-ablation.md`](2026-08-05-s3-ablation.md) | S3 feature ablation at 3k (V4 gate stack, fair): belief reweighting and chain compression are net-negative (−8.6 / −4.7pp when removed), CRN warm start (−14.1pp, was dead code and stays off), prune/live bit-identical inert; A2 S3−belief beats S2 ref +14.1pp (CI excludes 0); combined-arm 256-seed follow-up open, no default change. |
| 2026-08-05 | [`2026-08-05-label-noise-wave.md`](2026-08-05-label-noise-wave.md) | Label-noise wave (post-Phase F): futures=2 variance reduction (matched 500-seed control, 55→126k value grid) and trainer-side denoising (MARGIN_EPS/SPREAD_W/TERM_W) all null on dist_top1/q_top1 — the one-ply label ranking, not its noise, is the ceiling; learned-label line closed (§96/§100/§104/§105), K=6 (5.7.1b) deferred, 5.7.3 vs. abandoning labels is the open question. |
| 2026-08-04 | [`2026-08-04-combat-pvnet-parity-fixes.md`](2026-08-04-combat-pvnet-parity-fixes.md) | Combat PVNet parity fixes: 3 C++ inference bugs (GELU FFN, always-14 token layout, policy-head dot product) + offline eval harness; §72 replication 12.5%; payoff gate at 3k sims negative — A–H sweep stopped. |
| 2026-08-04 | [`2026-08-04-map-dag-encoder-wave.md`](2026-08-04-map-dag-encoder-wave.md) | Map-DAG encoder wave (5.3.2): V6 artifact built, offline gain, gameplay neutral-to-negative — falsified, stays opt-in/undeployed. |
| 2026-08-04 | [`2026-08-04-qwin-continuation-desktop.md`](2026-08-04-qwin-continuation-desktop.md) | Wave A1/B desktop execution: corrected-label retrain, V5 export, margin + regret-gate sweeps (both negative); Q_win heads under-confident at top deciles; K=6 transfer validation deferred. |
| 2026-08-04 | [`2026-08-04-phase-f.md`](2026-08-04-phase-f.md) | Phase F search distillation (5.7.1+5.7.2): soft-target policy objective falsified on the gate A/B — every policy-score arm loses to the Q-gate (~+3..+27pp) and the 39.8% reference (best −21.1pp); tie-dominated labelWon caps the ranking signal; `STS_OOC_STRATEGIC_SCORE` stays opt-in, 5.7.3 unchecked, K=6 targets the open follow-up. |
| 2026-08-02 | [`2026-08-02-phase5-round2-per-screen-heads.md`](2026-08-02-phase5-round2-per-screen-heads.md) | Phase 5 round 2: per-screen value heads; card gate neutral. |
| 2026-08-02 | [`2026-08-02-phase5-round4-campfire-event-gates.md`](2026-08-02-phase5-round4-campfire-event-gates.md) | Phase 5 round 4: one-ply Q gates for campfires and events (5.5.2/5.5.3). |
| 2026-08-02 | [`2026-08-02-pvnet-headline-not-reproducible.md`](2026-08-02-pvnet-headline-not-reproducible.md) | PVNet 66.4% headline does not reproduce on the current checkout (8.6% observed); falsified as recorded; root cause of the original number unknown. |
| 2026-08-02 | [`2026-08-02-strategicgen-phase5-round1.md`](2026-08-02-strategicgen-phase5-round1.md) | Phase 5 round 1: strategicgen all-actions datagen + Tier-A net + one-ply gate. |
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
