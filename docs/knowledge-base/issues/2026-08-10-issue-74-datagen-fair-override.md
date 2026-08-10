# Issue 74: `datagen` silently overrides `STS_FAIR`

- **Status:** closed (2026-08-10)
- **Tier:** Low
- **Date:** 2026-08-10
- **Source:** Investigator audit 2026-08-10, `apps/one_combat.cpp:10769`

## Symptom

`datagen` mode does `search::g_fairPlay = argc > 7 ? std::stoi(argv[7]) != 0 : false;`
with no warning — an env `STS_FAIR=1` run of `datagen` reverts to known-RNG
unless the positional arg is given. `datagen2`/`datagen3` have no such override.

## Evidence

- `one_combat.cpp:10769`: positional arg override without warning.
- `datagen2`/`datagen3` respect env — inconsistent.

## Candidate fix directions

Add a warning when the positional arg overrides the env var.

## Relevant code

- `apps/one_combat.cpp:10769`
