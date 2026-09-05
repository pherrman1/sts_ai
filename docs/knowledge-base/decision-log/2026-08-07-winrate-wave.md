# 2026-08-07 — Winrate-wave kickoff: S3-centered plan adopted, baseline wave first

Date: 2026-08-07
Session/task: Kickoff of the S3-centered winrate improvement wave
(from the archived August 2026 winrate plan).

## Decision

- Scope: improve winrate with **Searcher3 as the focus**. S2 fair
  determinization work is out of scope by user choice. §122/§123 promotions
  (live-valid, forced-move) are done and not re-gated.
- Execution order: baseline re-measurement first (the 44.5% @3k / 37.5% @1k
  headlines predate the live-valid default flip), then Wave 1 (S3
  diagnostics + cheap knobs), then Wave 2 (S3 structural bets:
  on-no-valid-edge expansion, TERM_WIN+C_psi, boss-conditioned NN leaf).
  Wave 3 (self-play relabeling 5.7.3, counter-aware OOC pricing) is
  **deferred** — stop after Wave 2 per user instruction.
- Every policy-affecting arm gets a paired 256-seed fair gate with
  pre-registered decision rules; falsified lines are recorded, never
  silently dropped.
- Adopted §123 open follow-ups: (1) full-stack re-measurement with the
  live-valid default; (2) `fairgen` datagen with explicit `STS_LIVE_VALID=1`
  (datagen is not covered by the default due to parse order) when the
  policy-prior-v2 line runs.
- Re-derivation of the §106 S3 feature-ablation deltas (belief/chain/CRN) is
  in scope: those deltas were invalidated by §113 and live-valid changes
  particle-divergence behavior; the deployed S3−belief−chain config's
  superiority has never been honestly re-measured.

## Rationale

- §123's cpu-trade call (+8-15% cpu for +5-6pp win) establishes the gate
  bar and promotion precedent for the new S3 structural bets.
- All headline numbers on the recorded block were measured pre-live-valid;
  any gate needs a current paired reference, so the baseline wave is the
  prerequisite for everything else.
- **Inference:** the §106 deltas (belief/chain) interacted with the
  pre-fix enumerator regime (invalidated §113) and with the pre-live-valid
  tree behavior; both changed since, so the deployed default could be
  wrong in either direction — the re-derivation is cheap insurance.

## Alternatives considered

- Start directly with new search features without re-measuring — rejected:
  gates would lack a current paired reference and the new-default baseline
  shift would be unmeasured.
- Run the self-play relabeling (5.7.3) first — deferred per user instruction
  (stop after Wave 2); it remains the open highest-ceiling line.
- Focus on OOC/model levers first — rejected: user chose S3 as the focus.

## Evidence

- `EXPERIMENTS.md` §122/§123 (live-valid +5.5pp/+5.9pp, cpu-trade call),
  §113/§115 (honest references 44.5% @3k, 37.5% @1k/64p),
  §106/§115 (ablation deltas invalidated; re-derivation flagged),
  §117 (rollout-usage diagnostic → boss-leaf rationale),
  §116/§110 (TERM_WIN+C_psi open gate).
- Archived August 2026 winrate plan — the plan.

## Status and follow-up

- Implemented: plan file, this entry. Next: baseline wave B1–B4 on GCP
  sts-test; record §124; then Wave 1/2 items with gates.
