# StS AI project guidance

## Project and architecture

- This project builds an AI for Slay the Spire on gamerpuppy's `sts_lightspeed` C++ simulator.
- The active experimental driver is `apps/one_combat.cpp`; the canonical experiment log is `EXPERIMENTS.md`. Update the log whenever a benchmarked idea changes the evidence or recommendation.
- Combat control (`BattleContext`, `search::Action`, card/target/end-turn decisions) is C++-only. The Python bindings expose strategic/run-level APIs, not step-by-step combat control. Prefer C++ for combat MCTS unless the task explicitly extends `bindings/slaythespire.cpp`.
- The Python environment is `../.venv`. ML dependencies include pandas and XGBoost; some experiments also use PyTorch.

## Current best known configuration (ascension 0)

- Use RICH V2 drafting with card skip threshold `-0.5`, heuristic pathing, shop-V knapsack, win-rate rest policy, and policy-guided PUCT combat.
- Models: `build/v_rich_xgb.json`, `build/v_win_xgb.json`, and `build/policy_trees_c.txt`; PUCT default `c_puct=2.5` and is on by default. Set `STS_POLICY=0` only for a deliberate UCB comparison.
- Equal-budget reference: 51.6% win at 1,000 combat sims. PUCT at 3,000 sims reached 62.3% over 512 seeds and is the recommended practical 2,000-3,000-sim region. PUCT improves scarce-search strength but crosses below UCB around 6,000-10,000 sims; at 20,000 sims UCB was stronger.
- Reproduce the standard point with a plain `python3 v_server.py`, then `./one_combat.elf bestbench 1000 512 0`. Validate model loading in output rather than assuming it.

## Immediate priority: evaluate the stronger-teacher redesign

- The gate repair is complete: independent meta/value/policy arms use paired common seeds, a dense
  floor+win score, adaptive looks up to 500 seeds, 99% bounds, and no tie promotion. Preserve it.
- Iteration 12 is the first redesign iteration: 1,000-sim combat teacher, decision-focused combat
  value weighting, paired rest-vs-smith targets, and two-iteration retrain/gate cadence. Let the
  iteration complete and compare candidate validation plus held-out decisions before changing
  capacity or margins.
- Keep deployment/gating at 400/600 sims. Meta and policy require a +0.5 lower-bound advantage;
  only the latency-oriented combat value uses the -0.5 non-inferiority margin.
- Keep V_floor for card/shop and V_win/paired action values for rest. Prior unified V_win
  card/shop ablations were clear regressions; those decisions need paired/ranking targets before
  another promotion attempt.

## Self-play operating context

- The resumable loop is `selfplay/loop.sh`; dashboard is `watch -n2 selfplay/status.sh`. Inspect `selfplay/state.env`, `.done` markers, and existing buffers before launching or restarting anything.
- The loop trains and independently gates meta `V_win` + paired rest action value, combat value,
  and policy prior. The deployed hybrid keeps V_floor for card/shop and uses win-shaped rest policy.
- Keep heuristic pathing while the active `V_win` is forward-map-feature-blind. Enabling `STS_PATH_V` with the old model caused a catastrophic regression. Model-driven events were a wash.
- Local RAM constraint: keep `POLICY_WINDOW=1` unless training is made chunked or moved to a high-memory machine. Policy CSVs are multi-gigabyte; do not load multiple rich/policy datasets concurrently on the local 31 GB machine. Prefer a plain shell rather than a PyCharm terminal for memory-heavy training.
- Do not delete large buffers casually: datagen is append/resume-safe, and a failed training read does not imply data loss. Raw iteration CSVs are not automatically pruned.
- The user does not want hand-authored expert-tier priors or arbitrary deck-bloat penalties in the self-play solution; the model should learn these effects from outcomes.

## Experimental conclusions to preserve

- Deckbuilding/out-of-combat policy has repeatedly been the whole-run win bottleneck. Learned rich state value improved drafting materially; win-probability value is specifically better for survival/rest decisions.
- The DeepSets deck model tied the GBM near 0.75 AUC and did not improve full-run win rate. Treat this as a data/label ceiling, not evidence that a larger architecture is automatically the next step.
- Dynamic potion saving/hoarding hurt win rate in both known-RNG and fair-play tests. Potion use itself is active; boss deaths are not evidence of potion hoarding.
- Depth-capped combat rollouts with the attempted leaf value created a turtle equilibrium and hangs. The default uncapped path is safe; do not re-enable the cap without a leaf value that rewards enemy-HP progress enough to eliminate the fixed point.
- Known-RNG combat results are optimistic. Use `STS_FAIR=1` for honest evaluation and clearly label known-RNG comparisons.
- Common-random-number rollout drafting was too noisy/expensive online. Prefer amortized learned value functions for drafting.

## Build and safety gotchas

- Use C++17 and OpenMP. On the current Linux host, use native `g++` and typically `OMP_NUM_THREADS=12`; old WSL paths in historical notes are obsolete unless explicitly working on Windows.
- `BattleContext` combat loops must check `bc.outcome == Outcome::UNDECIDED`; `bc.isBattleOver` can lag and lead to an empty-action segfault.
- If changing layouts in `Node`, `Edge`, or the searcher, recompile every translation unit that includes those headers to avoid ABI/stack corruption.
- When incrementally updating `build/libsts.a`, preserve the archive's path-mangled object basename. Duplicate objects such as two `BattleContext` members can silently link stale code. Verify the archive contains exactly one matching member or do a clean full rebuild.
- Never use `pkill -f v_server.py` or similar broad patterns: they can kill the launching shell. Resolve and kill the exact PID.

## Detailed migrated context

- The original curated Claude notes are preserved at `~/.codex/imports/claude/sts/memory/`.
- Start with `MEMORY.md`, then read only task-relevant notes such as `selfplay-gate-fix.md`, `selfplay-loop.md`, `alphazero-lite-plan.md`, `value-model-v2-rich.md`, `winrate-value-model.md`, or `gcp-compute-setup.md`.
- Treat dated “running now” statements as historical snapshots. Verify processes, files, model versions, metrics, and line numbers against the workspace before acting.

## Native OOC checkpoint model

- `apps/ooc_checkpoint_net.h`: compact MLP inference (GELU, Linear, LayerNorm implemented from scratch). Binary weights exported by `export_ooc_checkpoint.py`. Loaded with `STS_OOC_CHECKPOINT_NN=<path>`. Replaces all OOC decisions (cards, path, shop, rest, events) with a single forward-pass NN — no v_server needed.
- `train_ooc_checkpoint.py`: trains the model from teacher CSV (checkpoint oracle traces). Predicts meanUtility directly from (state, action bits, screen, act).
- `export_ooc_checkpoint.py`: dumps trained model to 1.25MB binary, 32-sample parity check vs PyTorch (GELU approx error ~0.001).

## Run tracing (`runtrace` mode)

- `./one_combat.elf runtrace <seed> <sims> <asc>` — per-node human-readable trace of one seed.
- With `STS_OOC_CHECKPOINT_NN=<path>`: shows NN utility scores for every OOC decision.
- Output format per screen:
  - **Draft:** `card_name(V:+marginal NN:score)` per card, `NN: skip=score picks SKIP/CARD [DISAGREE]`
  - **Rest:** `HEAL = score`, `smith:CardName = score`, `DIG/LIFT/TOKE = score`
  - **Neow upgrade:** `[NN upgrade] #N = score` for each deck card
  - **Map/shop/event/treasure:** `[NN <screen>] #N = score`
- Env flags: `STS_STOP_AFTER_ACT=N` to stop after act N; `STS_REFIGHT_FLOOR=N STS_REFIGHT_N=K` to re-fight a specific combat K times.

## Checkpoint oracle (all-OOC combat-strength evaluator)

- Env: `STS_ACT_FIGHT_PROBE_ALL_OOC=1`. Scores every legal OOC action by MCTS-simulating upcoming combats at each reached checkpoint, weighted by encounter distribution.
- **Cheap variant (67b):** `STS_VNET=build/v_combat_fair_trees.txt STS_VNET_ALPHA=0.3 STS_ACT_FIGHT_PROBE_CHECKPOINT_SIMS=50,25,10` — uses combat value net leaf to make 50/25/10-sim checkpoint MCTS viable. **46× faster** than original §66 pure-MCTS oracle. Act-1: 87.5% clear vs baseline 50.0%.
- Teacher collection: add `STS_ACT_FIGHT_PROBE_LOG=/path/teacher.csv` for durable per-action rows.
