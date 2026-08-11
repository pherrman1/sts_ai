# Research tooling

Last verified: 2026-08-11.

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
| `export/` | Model export for native consumption |
| `run/` | Experiment orchestration shell scripts (ablation sweeps, gates, data generation loops) |
| `verify/` | Regression self-tests, deterministic-replay checks, parity validation |

Existing tools that predate this reorganization (e.g., `tools/analyze_*.py`,
`tools/train_*.py`, `tools/tune_*.py`) remain in the flat `tools/` directory.
They maintain their own conventions and import paths.

## Active vs reproducibility-only

Scripts under `tools/run/` include both current experiment harnesses (used
in ongoing Searcher3 and strategic-policy research) and historical data
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

- **PVNet eval cluster:** `combat_pvnet_parity.py`, `eval_combat_pvnet.py`,
  `eval_combat_utility.py` — shared module imported by both eval scripts.

- **Self-play active scripts:** `train_value_combat.py`, `train_winrate.py`,
  `train_rest_cf.py`, `train_policy.py`, `train_card_cf.py`,
  `v_server.py`, `paired_analysis.py` — invoked by `selfplay/loop.sh` and
  related scripts; call-site changes risk breaking the loop state machine.

- **Cross-imported modules:** `train_deckset.py`, `train_combat_deepsets.py`,
  `train_combat_dist.py`, `export_combat_model.py` — imported by both root
  scripts and `tools/` scripts.

- **All remaining root trainers, exporters, and evaluators:** each belongs to
  a research line with its own module and invocation context. Moving them
  individually would require systematic call-site and import auditing across
  the full experiment and self-play infrastructure. This is deferred to a
  later phase.
