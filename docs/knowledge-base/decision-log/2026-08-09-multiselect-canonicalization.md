# 2026-08-09 — Multi-select mask canonicalization (STS_MULTISELECT_CANONICAL)

Date: 2026-08-09
Session/task: Collapse bitmask duplicates in EXHAUST_MANY/GAMBLE action
enumeration when the hand holds multiple copies of identical cards.

## Decision

- New opt-in env `STS_MULTISELECT_CANONICAL=1` (default off): in
  `src/sim/search/Action.cpp::pushMultiSelectActions`, after building each
  subset mask but before emitting the action, dedup by the selected-card
  multiset key; only the first-encountered mask per key is emitted.
- The key is a sorted vector of per-card identity values packed from
  `(id, upgradeCount, costForTurn, freeToPlayOnce, specialData)`
  (`cardIdentityKey`) — deliberately NOT bare CardId: that is the same card
  equivalence the PLAYER_NORMAL duplicate collapse already uses
  (`playerNormalGroundTruth` in `apps/test.cpp`), so upgraded or
  temporarily-modified copies remain distinct actions and the
  issue-47/48 parity contract is preserved even with the flag on.
- Applies to the `all` subset enumeration and to the per-card singles of the
  `single` deployment mode; `none` is unaffected. Searcher2/Searcher3 inherit
  the behavior because both delegate CARD_SELECT enumeration to the canonical
  `search::Action::enumerateCardSelectActions`.
- The flag is parsed next to the existing `STS_MULTISELECT_MODE` parse in
  `Action.cpp` (that parse lives in `Action.cpp`, not `apps/one_combat.cpp`).

## Rationale

- With duplicate cards, masks that differ only in which identical copy is
  selected are interchangeable: `chooseExhaustCards`/`chooseGambleCards` sort
  and compact the hand, so `{0,1}` vs `{0,2}` (three Strikes) produce the
  identical successor state. Emitting both dilutes PUCT visit counts across
  equivalent choices and bloats the tree (up to 1023 edges at a 10-card
  GAMBLE state).
- Pure-CardId keys were rejected because the parity fixture contains upgraded
  copies (e.g. `STRIKE_RED` + `STRIKE_RED+`): selecting {normal, upgraded}
  vs {normal, normal} are genuinely different effects, and CardId-only
  canonicalization would collapse them, breaking the parity contract the
  feature must preserve.

## Evidence

- `./build/test cardselect_parity` PASS (default mode unchanged; the test
  never sets `STS_MULTISELECT_CANONICAL` and runs in a fresh process).
- New `./build/test cardselect_canonical`: 10-card GAMBLE with 3 Strikes +
  3 Defends + 4 distinct cards: 1024 → 256 masks; 10 identical Strikes:
  1023 → 11 masks; hand [Strike, Strike, Strike+, Defend] keeps {0,1} and
  {0,2} distinct while collapsing {1,2} into {0,2} (exact mask lists pinned).
- 8-seed smoke `STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
  STS_S3_PARTICLES=64 ./build/one_combat bestbench 300 8 0 126700` —
  default (flag off) build, win% recorded in the gate report.
- **Inference:** branch-factor reduction is a search-scale lever for the
  known GAMBLE/EXHAUST_MANY subtree width; a win-rate gate with the flag on
  (paired seeds, same budget) is the next step.

## Alternatives considered

- Bare-CardId key — rejected (upgraded copies are distinct effects; parity
  contract).
- Always-on canonicalization — rejected (default off for safety; parity test
  and deployed behavior byte-identical unless opted in).
- Learned subset policy instead of dedup — orthogonal, deferred.

## Status and follow-up

- Opt-in; not yet gated on GCP. Next: paired 64-seed A/B `all`+canonical vs
  `all` @1k and @3k on the honest block; record in EXPERIMENTS.md; promote to
  default if it beats `all`.
- Artifacts: `./build/test cardselect_canonical` regression test added;
  `build/canon_smoke.csv` smoke output.
