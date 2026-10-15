# Investigation: PVNet 66.4% headline does not reproduce on the current checkout

- **Status:** closed (as recorded), follow-up flagged
- **Last verified:** 2026-08-02 (re-confirmed on the post-§73 binary; per-seed
  identical rerun, EXPERIMENTS.md §72)

## Symptom

The Phase 4b PVNet alpha sweep (EXPERIMENTS.md final ledger section,
2026-07-30) recorded a best 100-sim policy-only point of **66.4%** (and a
78.1% 32-seed point). The closest reconstructable configuration on the
current binary and the recorded seed block reaches **8.6%** — no 60–70%
combination exists on the current checkout.

## Scope

Full-run win rate of the Searcher3 + tracked PVNet combination at 100 sims,
fair play, on the recorded 126700–126827 block.

## Exact reproduction

```
STS_FAIR=1 STS_SEARCHER3=1 STS_PVNET=build/v_combat_pvnet.txt STS_PVNET_ALPHA=0 \
./build/one_combat bestbench 100 128 0 126700 build/pvnet_check_s3p0.csv
```
Tracked PVNet sha256 `05d809298921623af7c87c06e7dd31f5129abfd77cc702f75b9867949a59533f`;
tracked policy prior auto-loaded (banner `policyNet=ON`), satisfying the
`computeEdgePriors` enabling condition. Reference runs: default Searcher2 fair
@100 sims (`build/pvnet_check_base100.csv`), α=1.0
(`build/pvnet_check_s3p1.csv`).

## Expected / observed

- Expected (from the sweep): ~66% win rate at 100 sims, policy-only.
- Observed: **8.6% / 26.4 floor / 4.2 HP** (α=0), **5.5% / 24.4 / 2.8** (α=1.0),
  vs **4.7% / 29.5 / 2.0** same-budget default. Paired +3.9pp win (CI
  [−0.0, +8.6]), floor −3.1 (CI [−5.6, −0.6]); 9/128 discordant.

## Evidence

- EXPERIMENTS.md §72 (full provenance); `build/pvnet_check_*.csv`;
  current-baselines.md PVNet row and Known limitations updated;
  decision-log `2026-08-02-pvnet-headline-not-reproducible.md`;
  issue 16 (pvnet-sweep-provenance) updated with this re-check.

## Hypotheses

- **Inference:** the original sweep ran on pre-fix Searcher3 code. The sweep
  is dated 2026-07-30; the Searcher3 correctness fixes landed 2026-08-02
  (commits `63d8b89`, `d1e02a8`, issues 03–07, all closed). Bugs live at
  sweep time: composite seeding used unassigned values (03), `Belief::update`
  was a no-op and sampling uniform (04), `drawPileOrder` was ignored so
  particles reshuffled independently (05), and PVNet-only priors were zero
  (06) — the latter directly undercuts the sweep's "policy-only (α=0): PVNet
  priors guide PUCT" claim. The 66.4% is therefore most plausibly a number
  from a different, buggy search that no longer exists.
- **Inference:** the α-ordering claim (α=0 better than pure neural leaf)
  survives on post-fix code — directional sanity only, not a deployment
  recommendation.
- The tracked PVNet's fair training-data provenance is unverified (issue 16),
  so the model itself may also differ from the sweep's.

## Eliminated hypotheses

- Not a flag/load failure: startup banner confirms `PVNet=ON`, `policyNet=ON`,
  `searcher=Searcher3`, `fair-play`; artifact hash matches the recorded one.
- Not a measurement-regime mismatch: same `STS_FAIR=1` protocol as §68/§69.

## Current blocker / next check

None for the recorded claim — treat the 66.4% as falsified-as-recorded. If
PVNet is ever a candidate for default deployment, first re-derive what made
the original headline (block/OOC-stack/PVNet-snapshot differences) or drop it.
A productive follow-up is the Tier-B / strategic work in progress in the
working tree, not this number.

## Relevant code

- `apps/one_combat.cpp::main` (PVNet/DIST_VNET parsing, `STS_PVNET_ALPHA`)
- `src/sim/search/BattleScumSearcher3.cpp` (`computeEdgePriors` gating)
- `EXPERIMENTS.md` "Phase 4b PVNet alpha sweep" and §72
