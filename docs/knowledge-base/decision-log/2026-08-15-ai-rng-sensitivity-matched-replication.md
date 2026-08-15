# 2026-08-15 — AI_RNG sensitivity matched replication correction

## Decision

The AI_RNG fixed-hidden sensitivity diagnostic requires a corrected matched
replication before a live rejuvenation-treatment experiment is considered.

## Evidence

The first matched result recorded by commit `d68af8c` was invalid: it reused the
exploratory belief-ON artifact names, hashes, and summary counts while claiming
the belief-OFF/V4 regime. That record is explicitly superseded in
`docs/experiments/ledger-06.md`.

The corrected run used commit `d0c02cd`, seeds `126732–126739`, fair Searcher3,
`STS_S3_BELIEF=0`, 64 particles, 1,000 base / 3,000 boss simulations, real
filtering with collapse-fresh and persistent posterior, chain/reuse/end-turn
marginalization off, CRN off, 64 rejuvenation proposals, and the V4 token model
with REST/EVENT/SHOP/TREASURE/BOSS_RELIC gates enabled.

Artifacts:

- `/tmp/final8_matched_sensitivity.csv` — SHA-256
  `cb724466559a74437ebefd7e3c20d660a623fefd7e0ffb8c5492ff8610a1398a`
- `/tmp/final8_matched_live.csv` — SHA-256
  `1447919f936fb421cb81fcda831af8c5d59e62f7eff754699b34629019f6b50c`
- `/tmp/final8_matched_live.csv.meta.json` — SHA-256
  `159f2e1cbac329841aeedeb8f256d96b66879d209c1f1f781fb957626ed3a6a8`
- `/tmp/final8_matched_exposure.csv` — SHA-256
  `5add23d9c22757ff3e1cfd06c26a19ab71e2f5c7b9a8d55aced320d3ba9c08e4`
- `/tmp/final8_matched_rejuv.csv` — SHA-256
  `b915e93fddb0f8083bfec1bc98bb62c601d74cc0666b636500929f3e4a1b5496`
- `/tmp/final8_matched.log` — SHA-256
  `3105f6c9c429eaae2ef05838e96c2b569140be5bced7ce6fc93a1eebf6e34ba4`

## Result

The corrected run selected 32 real roots across 8 seeds, 13 encounters, 14
floors, and 32 encounter/floor groups. ORACLE_A/B controls were exact at all
146 root-action rows each; block-isolation and source/search-index failures
were zero. At least one AI alternative changed the selected action in 3/32
roots, changed top-two visit ordering in 4/32, caused a Q-order flip in 5/32,
and produced a nonzero common-edge Q difference in 9/32 roots.

Per-root maxima had visit-TV Q25/median/Q75/max `0/0/0.01275/0.906`, maximum
common-edge |dQ| `0/0/2.42775/131.362`, and maximum oracle-selected |dQ|
`0/0/0.30925/17.482`. The exposure join covered all roots; the three
selected-action-change roots had aggregate AI exposure `0.020`, `1.000`, and
`1.000`.

## Interpretation

The corrected matched run does not reproduce the exploratory counts exactly
(exploratory: 3/32 selected, 4/32 top-two, 3/32 Q flips), but it again shows
decision/ranking effects across multiple seeds and encounter groups with valid
controls. This clears a separately preregistered, targeted live-treatment
experiment, not a global gameplay-promotion claim. No live rejuvenation was
implemented or run here.