# 2026-08-05 — CARD_SELECT action-parity fix, and the multi-select search regression it exposed

Date: 2026-08-05
Session/task: Phase 1 of the 60.2%→expert plan — make every enumerator of
legal card-selection actions match the simulator's validity contract
(`search::Action::isValidAction`), with an exhaustive parity test.

## Decision

- New `./build/test cardselect_parity` command (`apps/test.cpp::testCardSelectParity`):
  fabricates CARD_SELECT states for all 20 `CardSelectTask` values (3 hand-size /
  pickCount variants each) plus 3 PLAYER_NORMAL states, computes ground truth
  from `isValidAction` (the simulator's own contract), and requires the
  canonical enumerator `search::Action::enumerateCardSelectActions`, the
  Searcher2 member, and the Searcher3 free function to match it exactly.
  Deterministic (3-run hash-identical).
- Fixed the canonical enumerator (`src/sim/search/Action.cpp`): added
  HOLOGRAM/MEDITATE (discard pool), NIGHTMARE/RECYCLE/SETUP (hand pool), SEEK
  (draw pool), and full-subset enumeration for EXHAUST_MANY (all subsets of the
  hand of size ≤ pickCount) and GAMBLE (all subsets).
- Searcher2 and Searcher3 now delegate their CARD_SELECT branches to the
  canonical enumerator (`BattleScumSearcher2.cpp::enumerateCardSelectActions`,
  `BattleScumSearcher3.cpp::enumerateActionsForNode`); the stray `break;`
  cluster in S3 was removed. Before the fix: S3's default branch was
  `for (i < csi.pickCount)` — wrong pool for WARCRY/FORETHOUGHT/HEADBUTT/
  SECRET_*/DUAL_WIELD/LIQUID_MEMORIES/HOLOGRAM/MEDITATE/NIGHTMARE/RECYCLE/
  SETUP/SEEK, no EXHUME-card filter, garbage edges for INVALID; S2 and the
  canonical enumerator missed HOLOGRAM/MEDITATE/NIGHTMARE/RECYCLE/SETUP/SEEK
  and emitted a single bogus empty subset for EXHAUST_MANY/GAMBLE.
- New env `STS_MULTISELECT_MODE=all|single|none` (default `all`): deployment
  knob that prunes the multi-select action space to empty+singles+full
  (`single`) or empty only (`none`) without emitting invalid actions (verified:
  zero "extra" mismatches in the parity test). The parity test enforces the
  `all` contract.

## Rationale

- Ground truth is the validity contract because `Action::execute` +
  `isValidAction` are the simulator's own acceptance rule; any enumerator that
  cannot produce an accepted action is blind to a legal choice (issue 47).
- Delegation to one canonical function keeps the three enumerators from
  drifting apart; the parity test pins the contract.

## Evidence (paired GCP benchmarks, §112)

- Control (original files at 619c12c, seeds 126700–126955, 1k sims/256p, fair,
  S3−belief−chain, V4 gate stack): **56.6% / floor 43.0 / HP 35.2** —
  bit-identical pairing vs the §111 `gate_2026-08-05_margin_base1k.csv`
  (0/256 seed mismatches).
- Full candidate (all three fixes): **39.5% / 41.0 / 18.9** — paired
  **−17.2pp (SE 3.1)**, 14 candidate-better vs 58 baseline-better.
- S3-only bisect (new canonical+S3, control S2, seeds 126700–126763 @1k):
  **28/64 = 43.8%** vs control 36/64 = 56.3% on the same subset — the S3
  change alone is the regression driver; the S2-only bisect was not run
  (queued).
- **Inference:** the regression mechanism is the full-subset enumeration at
  GAMBLE (Gambler's Brew potion) and EXHAUST_MANY (Elixir potion, Purity)
  states: up to 1023 children with uniform policy priors
  (`combatFillActionFeatures` gives identical features to every subset) at a
  fixed 1000-sim budget → near-random subset choice and the search's budget
  consumed at that node. The old S3 emitted no valid edges there, so the old
  agent effectively never used those potions/cards; the new code actually
  plays them, with a poor policy.
- **Unverified:** that `single` mode fixes the regression — the
  `STS_MULTISELECT_MODE=single` and `=none` 64-seed A/Bs were not yet run when
  this entry was written.

## Alternatives considered

- Keep full subsets and fix the priors with a learned subset policy — rejected
  for now: no such policy exists, and correctness of enumeration is
  independent of search-scale handling.
- Revert the whole parity fix — rejected: the parity test proves the old
  enumerators were wrong on 48/63 states; the deployment knob is the
  intended scale fix.

## Status and follow-up

- Committed as `parity` branch work (commit message: cardselect parity fix);
  `STS_MULTISELECT_MODE` default `all` is NOT yet recommended for deployment —
  run the `single`/`none` A/B before promoting (issue 48).
- Next session: (1) run `single` vs `none` vs `all` 64-seed A/B on GCP,
  (2) run the S2-only bisect (default binary), (3) promote the winner and
  re-benchmark 256 seeds @1k and @3k against the §107 win reference
  `pt2_p256_s3k_both_256.csv`, (4) close issue 48 and update
  `docs/knowledge-base/architecture/combat-search.md`.
- Artifacts: `build/{control_1k,cand_1k,s3_only_1k_64,base_1k,base_3k}.csv`
  (local + GCP `/home/philippherrmann/sts_sweep/build/`); GCP tree currently
  has the control files installed (S2 control + S3 control + canonical with
  the mode gate is NOT yet synced — re-sync `src/sim/search/Action.cpp` +
  `BattleScumSearcher3.cpp` before the next GCP run).
