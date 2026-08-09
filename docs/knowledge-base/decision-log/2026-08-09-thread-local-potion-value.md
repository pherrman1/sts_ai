# 2026-08-09 — Isolate per-fight potion value in parallel benchmarks

Date: 2026-08-09

## Decision

Make `search::g_potionKeepValue` thread-local in
`include/sim/search/BattleScumSearcher2.h` and
`src/sim/search/BattleScumSearcher2.cpp`.

## Rationale

`apps/one_combat.cpp::runFullRunOOC` computes the potion keep value separately
for each live fight. Fair `bestbench` executes seeds concurrently, while
Searcher2 reads this value during combat evaluation. A process-global value
therefore allowed one seed to overwrite another seed's combat setting.

## Evidence

Before the change, repeated nominally identical 64-seed controls produced
37.5% and 7.8% wins. After the change, two 8-seed runs with the same frozen
S3/VNet/Act-3 configuration matched all `won`, `floor`, `act`, `hpEnd`, and
death fields.

## Status

Implemented; larger paired benchmark requalification remains required.
