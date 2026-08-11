# 2026-08-11 — Tracked build/ artifacts relocated/deleted; build/ is now purely ignored output

Date: 2026-08-11
Session/task: Phase-2 repository hygiene — eliminate tracked artifacts from
`build/` without changing gameplay/model behavior.

## Decision

- `build/` now contains **no tracked files**; it is purely ignored build output
  and generated artifacts.
- **Relocated (byte-identical, `git mv`)** the six live deployable models from
  `build/` to a new tracked top-level `models/` directory:
  - `models/policy_trees_c.txt` (policy PUCT prior, auto-loaded by default)
  - `models/v_combat_pvnet.txt` (opt-in PVNet; documented tracked identity +
    `pvnetparity`/parity-script defaults)
  - `models/v_rich_trees.txt` (native OOC floor net, loaded at startup)
  - `models/v_win_trees.txt` (native OOC win net, loaded at startup)
  - `models/v_rich_xgb.json` (v_server `VMODEL` default; CF-collection floor
    reference)
  - `models/v_win_xgb.json` (v_server `VWIN` default; selfplay fresh-bootstrap
    source)
- **Deleted** five obsolete/closed-line artifacts (results and hashes recorded
  in `EXPERIMENTS.md` / decision logs):
  - `build/policy_trees_c_v2.txt` (§127 prior-v2 gate NULL, line closed,
    decision log `2026-08-07-policy-prior-v2-pipeline.md`)
  - `build/v_combat_honest.txt` (§126 deployed vnet, superseded by the §148
    7k-tuned model — zero code references; `apps/one_combat.cpp` default is
    `models/v_combat_7k_tuned.txt`)
  - `build/v_combat_quantile.txt` (§133 quantile-R closed, reference-only)
  - `build/v_combat_utility.txt` (§128/§131 value-only utility net, offline
    research only, no C++ loader ever written)
  - `build/v_pvnet_fresh.txt` (§131 ablation artifact, results recorded)
- Trainer **output** defaults (`train_combat_pvnet.py`, `train_value_rich.py`,
  `train_winrate.py`, `export_win_model.py::OUT`) intentionally still write to
  `build/` — generated outputs belong in the disposable directory; deployed
  models live under `models/`.

## Rationale

- `build/` was already git-ignored, so tracked files there were uncloneable
  provenance mistakes: a fresh clone could not know which tracked files were
  required, and cleanup/cloning/ownership were ambiguous.
- Code and maintained docs proved six files are required by current behavior /
  supported tooling (default loaders, `v_server.py`, `selfplay/loop.sh`
  bootstrap, parity/calibration scripts, `current-baselines.md` artifact
  identity block); deleting them would silently change fresh-clone behavior.
- The five deleted artifacts are closed experimental lines whose gate evidence
  and model hashes are already recorded in `EXPERIMENTS.md` and the decision
  log; per the hygiene rule, historical result evidence belongs there, not as
  multi-MB tracked models.
- Text/JSON formats preserved exactly (no `.native` conversion, no retrain,
  no re-export).

## Alternatives considered

- Blind `git rm -r --cached build/` — rejected: would silently delete live
  default models (`policy_trees_c.txt`, `v_rich_trees.txt`, `v_win_trees.txt`).
- Keep tracking inside `build/` — rejected (target design: `build/` disposable).
- Move live artifacts into `selfplay/models/` — rejected: that directory's
  tracked subset is exclusively `*.native` self-play exports; the floor/win/
  policy/PVNet/XGB models are `one_combat`/server deployables, so a dedicated
  top-level `models/` directory is the smallest clean location.

## Evidence

- `git ls-files build/` → empty after the change.
- Relocated files byte-identical: sha256 before/after match for all six
  (e.g. `v_rich_trees.txt` `3a342046…`, `v_win_trees.txt` `fc52c14c…`,
  `policy_trees_c.txt` `24793bd3…`, `v_combat_pvnet.txt` `a7a55e52…`,
  `v_rich_xgb.json` `466ea196…`, `v_win_xgb.json` `fde62d54…`).
- Stale hash corrected: `current-baselines.md` listed `v_combat_pvnet.txt` as
  `05d80929…`; the tracked blob actually hashes to `a7a55e52…` (verified
  `git hash-object` == working tree), so the identity block now records the
  true hash.
- Loaders/producers updated: `apps/one_combat.cpp` (default native OOC floor/
  win, policy PUCT, `winnettest`/`policystats`/`pvnetparity` defaults),
  `v_server.py`, `selfplay/loop.sh` (bootstrap + baseline cache key),
  `run_pvnet_gate.sh`, `run_s3_ablate.sh`, `run_s3_particles_sweep.sh`,
  `check_vwin_calibration.py`, `fit_vwin_calibration.py`, `parity_vwin.py`,
  `export_win_model.py`, `combat_pvnet_parity.py`, `eval_combat_pvnet.py`,
  `eval_ensemble.py`, `train_meta_entity.py`,
  `selfplay/run_card_cf_collection.sh`, `selfplay/run_future_fight_collection.sh`.
- Docs updated: `AGENTS.md`, `CODE_MAP.md`, `current-baselines.md`,
  `environment-variables.md`, `combat-search.md`, `out-of-combat.md`,
  `selfplay-loop.md` (this file). Historical `EXPERIMENTS.md` / decision-log /
  issue records intentionally left with their original `build/` paths.

## Open questions

- The fair-S3 default vnet (`build/v_combat_7k_tuned.txt`, §148) is a live
  default model that remains **untracked/ignored** in `build/` — out of scope
  for this cleanup (not a tracked file). A fresh clone therefore silently runs
  the fair-S3 path without the vnet leaf unless the file is synced manually.
  Consider tracking it under `models/` in a follow-up, with sha256 + docs per
  the artifact-shipping convention.

### Resolution (2026-08-11 follow-up)

This open question is **closed**. The §148 7k-data tuned combat VNet is now
tracked at `models/v_combat_7k_tuned.txt` (sha256
`ea35b78c888e70e09566e1143d296577b0bea2ec8d437276b7aab81a7cdaf15c`, byte-identical
to the deployed artifact). `apps/one_combat.cpp` loads that tracked path for the
automatic fair-S3 default (α=0.3), the load-failure diagnostic names the same
path, and current KB docs (`current-baselines.md`, `combat-search.md`,
`environment-variables.md`, `research/combat-models/vnet.md`) reference
`models/v_combat_7k_tuned.txt`. A fresh clone now receives the fair-S3 default
VNet through ordinary `git pull`; `build/` remains purely ignored/generated.

## Status

Complete for all 11 originally tracked `build/` files. `git ls-files build/`
is empty; newly generated build products remain ignored.
