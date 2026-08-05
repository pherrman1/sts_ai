# 2026-08-05-issue-48 — Multi-select full-subset enumeration regresses win rate (open)

**Tier:** High
**Status:** open
**Source pages:** [combat-search](../architecture/combat-search.md),
[decision log `2026-08-05-cardselect-parity-fix.md`](../decision-log/2026-08-05-cardselect-parity-fix.md)

## Symptom

After the issue-47 fix, enumerating every subset of the hand for
EXHAUST_MANY/GAMBLE (up to 1023 actions at a 10-card Gambler's Brew state)
regresses full-run win rate at fixed simulation budgets: full candidate
**39.5% vs 56.6% control** on 256 paired seeds @1k/256p (paired −17.2pp,
SE 3.1); S3-only bisect 43.8% vs 56.3% control on 64 seeds. Control
reproduces the §111 reference bit-identically.

## Evidence

`EXPERIMENTS.md` §112; CSVs `build/{control_1k,cand_1k,s3_only_1k_64}.csv`
(local + GCP `/home/philippherrmann/sts_sweep/build/`).

## Why it matters

Gambler's Brew (common potion), Elixir (common potion) and Purity (Ironclad
card) all route through these tasks. With 1000 sims the tree spreads over
hundreds of children with uniform policy priors (`combatFillActionFeatures`
yields identical features for every subset), so the subset choice is
near-random and the search budget is consumed at that node. The pre-fix S3
emitted no valid edges there, so the old agent effectively never used those
potions/cards; the fixed code plays them with a poor policy.

## Candidate fixes

- `STS_MULTISELECT_MODE=single` (empty + each single card + whole hand,
  ≤ n+2 actions) or `=none` (empty only) — implemented, awaiting A/B.
- A learned subset policy / narrower canonical subset space (future).

## Status

A/B of `single` vs `none` vs `all` on 64–256 seeds at 1k sims pending; S2-only
bisect pending (default binary is affected too). Promote the winner and update
`docs/knowledge-base/architecture/combat-search.md` on close.
