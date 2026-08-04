# 2026-08-03 — Per-screen one-ply gate margins

Date: 2026-08-03
Session/task: Track: per-screen margin knobs for the one-ply Q gates in `apps/one_combat.cpp`, defaulting to the global margin when unset.

## Decision

Added six per-screen margin overrides, each defaulting to `-1.0` (unset = fall back to `g_oocStrategicMargin`, so behavior is bit-identical when unset):

- `STS_OOC_STRATEGIC_MARGIN_CARD` → `g_oocStrategicMarginCard` — card rewards (`oocOnePlyCardRewardPolicy`)
- `STS_OOC_STRATEGIC_MARGIN_REST` → `g_oocStrategicMarginRest` — campfire rest options and smith upgrade-target picks (`oocOnePlyRestPolicy`, `oocOnePlyUpgradeSelectPolicy`)
- `STS_OOC_STRATEGIC_MARGIN_EVENT` → `g_oocStrategicMarginEvent` — events (`oocOnePlyEventPolicy`)
- `STS_OOC_STRATEGIC_MARGIN_SHOP` → `g_oocStrategicMarginShop` — shop buys (`oocOnePlyShopPolicy`)
- `STS_OOC_STRATEGIC_MARGIN_TREASURE` → `g_oocStrategicMarginTreasure` — treasure (`oocOnePlyTreasurePolicy`)
- `STS_OOC_STRATEGIC_MARGIN_BOSS_RELIC` → `g_oocStrategicMarginBossRelic` — boss relics (`oocOnePlyBossRelicPolicy`)

Each gate resolves `const double margin = g_oocStrategicMarginX >= 0.0 ? g_oocStrategicMarginX : g_oocStrategicMargin;` **before** its scoring loop and gates on `best - second < margin`. Globals ~:739, env parse in `main()` after the `STS_OOC_STRATEGIC_MARGIN` block ~:6675; a `[OOC per-screen margins: card=...]` banner prints when any override is set.

## Rationale

- Screen-level tuning: the gates sit on different value scales (e.g. treasure has few near-tied options, events are stochastic), and a per-screen margin lets sweeps tune one screen without disturbing the calibrated global margin 1.0.
- Unset must be behavior-identical: `-1.0` sentinel (negative = impossible threshold, since a margin of `best - second >= -1` would trivially pass) keeps the fallback an explicit, testable branch rather than a default-argument trap.

## Alternatives considered

- Default each knob to the global's value at parse time — rejected: cannot distinguish "explicitly set" from "inherited", so future global changes would silently change screens, and the smoke proof of bit-identical fallback is cleaner with the sentinel.

## Evidence

- `apps/one_combat.cpp`: globals ~:739-744, gates ~:3134/3193/3239/3286/3332/3377/3422 (resolution before loop; `best - second < margin`), env parse ~:6675-6696.
- Smoke (`build2`, `STS_FAIR=1 bestbench 100 8 0 128000`, seeds 128000-128007): no gates 12.5% / floor 26.4; gates on (REST/EVENT/SHOP/TREASURE/BOSS_RELIC, `STS_OOC_STRATEGIC_NN=selfplay/models/ooc_strategic.native`, global margin 1.0) 12.5% / floor 37.4; same + `STS_OOC_STRATEGIC_MARGIN_TREASURE=0.1` 0.0% / floor 37.0 — k0≠k1 (gates fire) and k1≠k2 (treasure override has an effect). All knobs explicitly `=1.0`: game-state columns byte-identical to k1 (only the per-run wall-clock `sec` column differs).
- `./build2/test` exit 0; `git status --short` shows only ` M apps/one_combat.cpp`.

## Status and follow-up

- Implemented; default behavior unchanged (verified). Full paired margin sweeps are the orchestrator's record.

## Sweep results (appended 2026-08-03)

- 24-run coordinate sweep (GCP server, parity-verified binary) + 256-seed
  validation of the only positive point. Full table in EXPERIMENTS.md §89.
- **Verdict: single global margin 1.0 confirmed.** Cards are clearly worse
  below 1.0 (−8.6pp at 0.1); every other screen is flat-to-worse at every
  non-1.0 point; BOSS_RELIC at 2.0 is +0.8pp on 256 seeds (CI [−1.2,+3.1],
  3% of seeds affected) — not adopted per the pre-registered rule. Knobs
  stay available for future label/head changes.
