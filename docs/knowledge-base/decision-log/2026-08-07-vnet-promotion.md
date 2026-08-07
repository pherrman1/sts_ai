# 2026-08-07 — V_combat leaf promoted to default ON in the fair-S3 path (§126)

Date: 2026-08-07
Session/task: Winrate wave close-out; promotion decision for the fresh
honest-data combat value leaf (`docs/knowledge-base/plan-winrate-ideas-2026-08-07.md`).

## Decision

- **Promote** the fresh 804-tree combat value net (`build/v_combat_honest.txt`,
  trained on 287,517 honest `combatgen` rows, seeds 0-1499) to **default ON
  in the fair-S3 path** at `STS_VNET_ALPHA=0.3` (unconditional blend), with
  the recorded cpu-trade call: accept ~2-2.4× cpu for a reproducible
  **~+12pp win** (+2-3 floor, +4-6 end HP).
- Scope mirrors the live-valid default (§123): fires only when
  `STS_FAIR=1` and `STS_SEARCHER3=1`; an explicit `STS_VNET=…` overrides;
  `STS_VNET=<missing-path>` disables. S2 fair / non-fair paths stay
  env-only. `fairgen` datagen is not covered; `combatgen` datagen is
  covered (envs set during parse) — future combat labels align with the
  deployed leaf.
- The boss-only / act-3 conditioning knobs (`STS_VNET_COND_BOSS`,
  `STS_VNET_COND_ACT3`) stay opt-in: measured flat (§126), the value is
  spread across all rollout-heavy contexts.

## Rationale

- Three independent significant paired gates at α=0.3 (256 seeds each):
  **+12.5pp @1k/64p block 126700 (CI [+5.5,+19.5]), +12.1pp @1k/64p block
  250000 (CI [+4.7,+19.5]), +12.5pp @3k/64p (CI [+6.2,+18.8])** — the §123
  two-gate promotion rule is exceeded. Highest honest winrate recorded:
  55.1% @3k/64p vs the pre-vnet 46.9%.
- §97's rejection (old 1,500-tree vnet, old-era data, α0.3/0.5) does not
  transfer: the fresh honest-data model at low α is strongly positive; the
  α curve (12.5 → 5.5 → 5.9 pp for α 0.3 → 0.5 → 0.7) shows a noisy-but-
  right leaf blended lightly is the operating point. **Inference**:
  the honest labels (post-§113 searcher, live-valid) are the difference.
- **Inference:** datagen was heuristic-OOC (combatgen's own loop); the
  transfer to the gate-stack distribution is measured empirically (it
  works) but a gate-stack-distribution retrain is the natural follow-up.

## Alternatives considered

- Boss-only conditioning (the original plan §4.3 framing) — tested first,
  flat at both α; the unconditional low-α blend carries the value. Rejected.
- α=0.5 default — significant @1k (+5.5pp) but weaker; α0.3 wins both
  points and the 3k operating point.
- Keep env-only (no default flip) — rejected: three gates + a recorded
  cpu-trade call meet the promotion precedent; leaving the top arm opt-in
  would keep the binary's default stack ~12pp below its best measured
  configuration.

## Evidence

- `EXPERIMENTS.md` §124 (baseline re-measurement + ablation re-derivation),
  §125 (cPUCT/S3_EXPAND/TERM_WIN gates), §126 (vnet line, gates, verdict).
- `apps/one_combat.cpp::main` (default-load block),
  `src/sim/search/BattleScumSearcher3.cpp::vnetCondAllowed`,
  `include/sim/search/BattleScumSearcher3.h`.
- Per-seed CSVs `build/vnet_{all_a03_1k,a03_3k,all_a05_1k,all_a07_1k,boss_a03_1k,boss_a05_1k,all_a05_3k}.csv`,
  `build/vnet2_{ctl,a03}_250k.csv`; model sha256 `e69d64cf…`
  (`docs/knowledge-base/evaluation/current-baselines.md`).
- `docs/knowledge-base/plan-winrate-ideas-2026-08-07.md` §4.3.

## Status and follow-up

- Implemented (default flip in the working tree), recorded, docs updated.
- Follow-ups: second @3k vnet gate on a fresh block (firm the win point);
  gate-stack-distribution retrain of the vnet labels; particle-count
  interaction at 256p; the §124a PVNet gate now pairs against the §124/§126
  references.
