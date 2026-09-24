# Research tooling

Last verified: 2026-09-08.

## Invocation

All scripts are designed to be run from the repository root:

```bash
cd <repo-root>
python tools/<category>/<script>.py ...
bash tools/<category>/<script>.sh ...
./tools/<category>/<script>.sh ...
```

Shell scripts that previously resided at root have had their internal `cd`
adjusted to preserve repo-root CWD after the move.

## Categories

| Directory | Purpose |
|-----------|---------|
| `analysis/` | Offline analysis, calibration checks, diagnostic probes |
| `data/` | Data preprocessing, tree truncation, format conversion |
| `run/` | Experiment orchestration shell scripts (ablation sweeps, gates, data generation loops) |
| `verify/` | Regression self-tests, deterministic-replay checks, parity validation |

The designated GCP benchmark workflow is centralized in
`tools/agent/gcp_benchmark.py`. It uses the existing user's gcloud
authentication and `gcloud compute ssh`; it does not store credentials or
manage arbitrary cloud resources. Its designated-target-only `copy-to`,
`copy-from`, and `job-status` commands keep artifact transfer and detached-run
inspection on the same pinned project/zone/instance/user/root contract.
Decision-bearing multi-arm runs should use its strict JSON manifest interface;
`tools/agent/research_run_manifest.example.json` is the maintained template.

`tools/agent/worktree.py` is the supported linked-worktree lifecycle entry
point. Its read-only `preflight` reports app-managed/external Git metadata
constraints before Git writes. Its `create` and `repair` commands initialize
and verify the pinned `json`/`pybind11` dependencies; `remove` refuses dirty
state and removes the clean checkout without globally deinitializing shared
submodule configuration. Prefer it to raw `git worktree add`/`remove` on
Windows.
`manifest-check` validates common seeds/configuration, required environment
variables, telemetry expectations, unique output paths, and frozen hashes;
`exact-sha-preflight` verifies the remote checkout, CMake source binding,
executable, and artifacts; `run-manifest` launches one arm and refuses to
overwrite an existing result, sidecar, or log.

`tools/agent/build.py` is the environment-aware entry point for checked-in
Linux CMake presets. It invokes CMake directly when available and otherwise,
on Windows, runs the complete configure/build sequence through one WSL shell.
Requested ccache preset pairs fall back to their ordinary counterpart when the
configured shared cache is unavailable or read-only. The probe runs in the
selected native or WSL build environment and forces configuration when a
fallback changes the binary directory.

`tools/agent/baseline_build.py` exports a baseline ref and its pinned submodule
commits to a temporary source tree, builds one executable, and retains only the
requested artifact under `build/baselines/`; it never creates a linked
worktree.

Existing tools that predate this reorganization (e.g., `tools/analyze_*.py`,
`tools/train_*.py`, `tools/tune_*.py`) remain in the flat `tools/` directory.
They maintain their own conventions and import paths.

Model export scripts have not been moved into a `tools/export/` category.
Root exporters (`export_combat_model.py`, `export_strategic.py`,
`export_strategic_tok.py`, `export_win_model.py`,
`export_ooc_checkpoint.py`) and flat `tools/` exporters
(`tools/export_catboost_vnet.py`, `tools/export_strategic_predictions.py`)
retain their existing locations and invocation conventions.

## Active vs reproducibility-only

Scripts under `tools/run/` include both current experiment harnesses (used
in ongoing strategic-policy research) and historical data
generation loops (`datagen_loop.sh`, `datagen2_loop.sh`) retained for
reproducibility. See `docs/knowledge-base/evaluation/current-research.md`
for the active set.

## Intentionally retained root clusters

Several dependency-sensitive clusters remain at repository root because
moving them would require new packaging, `sys.path` manipulation, or broad
import refactors:

- **Strategic token cluster:** `strategic_tok_net.py`,
  `strategic_tok_contract.py`, `strategic_split.py`,
  `strategic_metrics.py`, `strategic_gate_contract.py` — imported by root
  trainers, root exporters, and `tools/` scripts. Moving one would break the
  others.

- **PVNet eval cluster:** `combat_pvnet_parity.py`, `eval_combat_pvnet.py` —
  the evaluator imports the shared parity module.

- **Former self-play scripts:** `train_value_combat.py`, `train_winrate.py`,
  `train_rest_cf.py`, `train_policy.py`, `train_card_cf.py`, `v_server.py`
  and `paired_analysis.py` were driven by the self-play loop, which ADR-0020
  removed. They remain usable standalone.

- **Cross-imported modules:** `train_deckset.py`, `train_combat_deepsets.py`,
  `train_combat_dist.py`, `export_combat_model.py` — imported by both root
  scripts and `tools/` scripts.

- **All remaining root trainers, exporters, and evaluators:** each belongs to
  a research line with its own module and invocation context. Moving them
  individually would require systematic call-site and import auditing across
  the full experiment and self-play infrastructure. This is deferred to a
  later phase.
