# Environment variables

Last verified: 2026-10-08 for default ascending fallback REMOVE ordering; 2026-10-08 for the v3 CTM research-candidate manifest and staged CTM pins; 2026-10-07 for `STS_CTM_PINS` and the CTM research-candidate manifest; 2026-09-27 for the automatic OOC CTM stack, active-Lizard default, and `STS_FORCE_RELIC` Lizard initialization; 2026-09-25 for native-only Silver (ADR-0022); 2026-09-24 for Silver-only combat (ADR-0020), the Searcher3 removal and the Silver whole-run default; 2026-09-15 for live visit-lock stopping and full-budget root-lock observation; 2026-09-14 for live OOC MCTS; 2026-09-09 against `apps/one_combat.cpp::main`.

Purpose: single concise reference for all `STS_*` and related env vars consumed
by `one_combat`. Code is authoritative; this page routes readers to the right
parse site.

## Active / current-default configuration

These control the default executing configuration; they are always parsed.

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `VPORT` | v_server TCP port | 5555 | `main` L9210 |
| `STS_NATIVE_OOC` | Use in-process GBMs for floor/win; `0` disables (legacy server mode) | `1` (ON) | `main` ~L9470 |
| `STS_WIN_NET` | Path to V_win compact tree; `1` = default `models/v_win_trees.txt`. An explicitly supplied path (including empty) that fails validation exits nonzero before any fallback | auto-loads `models/v_win_trees.txt` | `main` ~L9465 |
| `STS_FAIR` | Accepted for compatibility; combat is always project-fair Silver. `0` makes `one_combat` exit with an error (ADR-0020) | `1` | `main` |
| `STS_SEARCHER3` | Removed (ADR-0019). A non-zero value makes `one_combat` exit with an error; `0` is accepted | `0` | `main` |
| `STS_SIMS_NORMAL` | Per-fight sim budget, normal encounters | unset (uses caller argument) | `main` ~L9530 |
| `STS_SIMS_ELITE` | Per-fight sim budget, elites | unset | `main` ~L9530 |
| `STS_SIMS_BOSS` | Per-fight sim budget, bosses | unset | `main` ~L9530 |
| `STS_SKIP_THR` | Card-reward skip threshold (marginal V) | `-0.5` | `main` ~L9665 |

## Silver combat backend

`one_combat` always installs the native Silver backend (`NativeSilverBackend`,
ADR-0021/ADR-0022); it is the only combat searcher
([ADR-0020](../../../decisions/0020-silver-only-combat-remove-searcher2-and-selfplay.md)).
The retained graph is compacted at 32,768 nodes. Any other `STS_SILVER_*`
variable with a non-empty value, and any value other than the accepted one
below, makes `one_combat` exit with an error: the vendored model's options
(telemetry, diagnostics, captures, reuse-cap overrides, leaf VNet, leaf corpus,
root prior, visit-lock and rho-racing stopping) were removed with it
(ADR-0022). The same applies to its `STS_COMBAT_BUDGET_DIAG_FILE`,
`STS_COMBAT_SEQUENTIAL_DIAG_FILE` and `STS_COMBAT_SEQUENTIAL_DIAG_CHECKPOINTS`
diagnostics.

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_SILVER_SEARCH` | Accepted for compatibility; Silver is always installed. `0` makes `one_combat` exit with an error (ADR-0020) | `1` | `main` |
| `STS_NATIVE_SILVER` | Accepted for compatibility; `0` (the removed vendored model) makes `one_combat` exit with an error (ADR-0022) | native | `main` |
| `STS_SILVER_ADAPTIVE` | Enable retained-root adaptive Silver (#199): fresh multi-action roots search 10,000; a retained root stops at 500 when its top-two visit-share gap reaches `STS_SILVER_ADAPTIVE_TOP_GAP`; `0` gives flat Silver or, with `STS_SILVER_LEARNED_STOP=1`, learned stopping | `run`/`bestbench`/`reprobench` without a sims argument resolve an unset value to `0` with learned stopping (ADR-0026) unless an adaptive knob or `STS_SILVER_LEARNED_STOP` is set; `STS_SILVER_LEARNED_STOP=0` alone keeps #199 there; every other invocation resolves an unset value to `0` (flat caller budget) (ADR-0018, ADR-0020) | `NativeSilverBackend` |
| `STS_SILVER_ADAPTIVE_TOP_GAP` | Stopping threshold for `STS_SILVER_ADAPTIVE` (top-vs-second visit-share gap `>=` this value) | `0.2932885906040268` | `NativeSilverBackend` |
| `STS_SILVER_LEARNED_STOP` | Learned stopping: each multi-action root searches to the 250..10,000 checkpoints and stops at the first strict visit lock or compiled stop-model risk below the threshold (`NativeSilverStopModel.h`). Requires `STS_SILVER_ADAPTIVE=0` (an unset value resolves to `0` when this is `1`); refuses an untrained model | `1` for `run`/`bestbench`/`reprobench` without a sims argument and without adaptive knobs (ADR-0026); otherwise off | `main`, `NativeSilverBackend` |
| `STS_SILVER_LEARNED_STOP_THRESHOLD` | Risk threshold for `STS_SILVER_LEARNED_STOP` | the compiled model's default (`0.0323` for `gbt-770201c31f7b`) | `NativeSilverBackend` |
| `STS_SILVER_LEARNED_STOP_BOSS_FALLBACK` | Research-only: with `STS_SILVER_LEARNED_STOP=1`, boss rooms use the #199 retained-root rule instead of learned stopping. Requires `STS_SILVER_LEARNED_STOP=1` | unset/off | `NativeSilverBackend` |
| `STS_SILVER_LEARNED_STOP_BOSS_MAX` | Research-only: with `STS_SILVER_LEARNED_STOP=1`, a boss root that reached 10,000 simulations without stopping continues in 10,000 steps up to this cap, until its leader is strictly locked against the cap. `0` or unset: off; otherwise must exceed 10,000; exclusive with `_BOSS_FALLBACK` | unset/off | `NativeSilverBackend` |
| `STS_SILVER_FINAL_BOSS_BINARY` | Research-only A0 Act-3 boss terminal score: victory 100, otherwise 0. Requires `STS_STOP_AFTER_ACT=3`, exact-root budgets, and learned/adaptive/stop-trace off. No strength qualification implied. | unset/off | `NativeSilverBackend`, `SilverSearcher` |
| `STS_SILVER_STOP_TRACE` | Research-only CSV of root features and leaders at every learned-stop checkpoint; searches each multi-action root to 10,000. Requires `STS_SILVER_ADAPTIVE=0`; exclusive with `STS_SILVER_LEARNED_STOP` | unset/off | `NativeSilverBackend` |
| `STS_SILVER_ADAPTIVE_RETAINED_ONLY` | Accepted only as `1` (adaptive Silver is always retained-only) | `1` | `main` |
| `STS_SILVER_EXACT_ROOT_BUDGETS` | `1`: the flat budget applies in boss fights too (no boss multiplier) and one-action roots are searched; used by the frozen exact-10k research contracts | off | `NativeSilverBackend` |
| `STS_SILVER_ESCAPE_PENALTY` | `<normal>,<elite>`: Silver score penalty (HP-equivalent) for a Smoke Bomb escape in normal and elite-trigger fights, capped at half the HP left; see combat-search.md | unset (`0,0`, escape scored as a win) | `NativeSilverBackend` |
| `STS_SILVER_SEARCH_SINGLETON_ROOTS` | `1`: search roots with one legal action instead of committing that action without search | off (one-action roots unsearched) | `NativeSilverBackend` |
| `STS_SILVER_REUSE_CAP_MODE` | Accepted only as `allocated` (the native cap) so frozen environments stay valid | `allocated` | `main` |
| `STS_SILVER_VNET_LEAF_DIRECT` | Accepted only as `0`; no leaf VNet exists | `0` | `main` |
| `STS_SILVER_TELEMETRY` | Accepted only as `0`; Silver telemetry was removed | `0` | `main` |
| `STS_SILVER_USELESS_TRACE` | Default-off JSONL census for the qualified last-card Defend/forced-End-Turn equivalence class, with root statistics and replay snapshots. Observes concrete RNG after selection; never a search/pruning input. | unset/off | `NativeSilverBackend` |
| `STS_SILVER_PUBLIC_TRACE`, `STS_SILVER_PUBLIC_TARGET` | Both required together; emit public wire state, selected semantic action and existing root alternatives/statistics for exact `SEED:FLOOR`. Public wire search seed is zero; outer run identity is a locator. Unsupported conversion is explicit. No extra search or private snapshot; child Q includes inherited samples. | unset/off | `NativeSilverBackend` |
| `STS_SILVER_TREE_PROFILE` | Opt-in append-only JSONL path for real backend decisions: endpoint classes, tree/rollout depths, context, budgets and reuse. Use a fresh file per run; an unwritable path fails explicitly. See [combat search](../architecture/combat-search.md#silver-tree-profile). | unset/off | `NativeSilverBackend` |
| `STS_SILVER_DEBUG_TREE` | Default-off debug capture: attach the reachable native Silver search graph (node states, visits/Qs, semantic edge labels, chance metadata) to each advisor combat response. Does not alter search or ordinary responses when unset. | unset/off | `apps/one_combat/advisor_stdio.cpp`; `apps/one_combat/native_silver_advisor.cpp` |
| `STS_SILVER_DEBUG_TREE_NODE_CAP` | Maximum native graph nodes included by `STS_SILVER_DEBUG_TREE`; oversized captures are marked truncated. | `8192` (maximum `100000`) | `apps/one_combat/advisor_stdio.cpp` |
| `STS_SILVER_ROOT_PRIOR_MODEL` | Removed with the root prior (ADR-0022); `one_combat_advisor` exits at startup and `one_combat` exits with an error when it is set | unset | `advisor_stdio.cpp`; `main` |
| `STS_OOC_DEBUG_TREE` | Attach a bounded OOC MCTS search graph to the live advisor's OOC evaluator. Search selection and ordinary responses are unchanged when unset. | unset/off | `apps/one_combat/advisor_stdio.cpp`; `OocMctsPlanner` |
| `STS_OOC_DEBUG_TREE_NODE_CAP` | Maximum OOC graph nodes included; omitted edges and truncation are marked in the capture. | `4096` (maximum `100000`) | `apps/one_combat/advisor_stdio.cpp` |
| `STS_EXECUTABLE_GIT_SHA` | Lowercase 40-hex reviewed executable Git SHA. Research manifests bind it to their frozen SHA; `one_combat` uses it for benchmark/training provenance, teacher and frozen-spec identity checks, and result sidecars instead of resolving the launcher's working-directory HEAD. Malformed values fail closed. | unset; working-directory Git SHA fallback outside manifest-bound runs | `one_combat` |

`bestbench` metadata records `effectiveCombatBackend="native_silver"`, the
reuse-cap mode (`allocated`) and cap, the adaptive and exact-root-budget
settings, and the executable Git SHA. The vendored-era keys (`silverUpstreamSha`,
diagnostic paths, visit-lock and rho-racing flags) and the legacy
`searcher3`/`s3*` and combat-model keys are kept with empty/false/zero/`off`
values for schema compatibility.

## OOC one-ply Q gate stack (opt-in)

All require `STS_OOC_STRATEGIC_*_NN` model loaded and the per-decision-type
enable flag:

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_OOC_PUBLIC_FUTURES` | Verified 2026-10-08. Research-only native fallback common encounter scenarios (integer 0..256): average predictions after redrawing the four unseen encounter identity fields conditional on observed prefix. Scope is the controlled native V4 fallback profile; does not sanitize legacy server or actual-RNG hypothetical-action paths. | unset/0 (legacy) | `ooc_native_fallback`, main value wrappers |
| `STS_OOC_SHOP_DECK_SIZE_FIX` | Research-only correction: hypothetical shop deck size increases for cards only and decreases for removal. Strict 0 or 1. | unset/off | `nativeShopPlan` |
| `STS_OOC_SKIP_OPTIONAL_RECALL` | Research-only REST eligibility repair: when keys are off, remove Ruby Recall from the V4 gate and random fallback if another legal action exists. Preserve the forced-only-Recall case. Strict 0 or 1; default behavior unchanged. | unset/off | `ScumSearchAgent2`, `oocOnePlyRestPolicy` |
| `STS_OOC_SKIP_FULL_HP_REST` | Research-only policy candidate: in an unresolved campfire at positive full HP, exclude REST only if REST and SMITH are both legal and present and Dream Catcher is absent. Preserve other actions and their order; covers the low-max-HP direct-rest branch too. Strict 0 or 1. No dominance or strength claim. | unset/off | `ScumSearchAgent2`, `oocOnePlyRestPolicy` |
| `STS_OOC_REMOVE_LOW_OBTAIN_WEIGHT` | Default fallback REMOVE ranking: ascending acquisition weight. Explicit `0` restores legacy descending ordering; `1` matches unset. Bonfire sacrifices, other selection types and native shop removal retain their current policy. Strict 0 or 1; no upgrade, curse or tie-breaking refinement. | unset/on | `ScumSearchAgent2::cardSelectPolicy` |
| `STS_OOC_CARD_WIN_RANK` | Research-only native reward fallback: preserve public8 floor take/skip, then rank taken cards using public8 logistic win predictions. Requires native loaded models, public8, margin gate, MCTS and alternate card families off. Strict 0 or 1. | unset/off | main native card wrapper, `nativeCardWinRankPick` |
| `STS_OOC_CARD_WIN_RANK_TRACE` | Emit existing floor/win marginals and semantic card actions to stdout for candidate diagnostics; adds no predictions or RNG draws. Requires the candidate enabled. Strict 0 or 1. | unset/off | main native card wrapper |
| `STS_OOC_STRATEGIC_NN` | V3 strategic net path | unset (off) | `main` ~L9295 |
| `STS_OOC_STRATEGIC_TOK_NN` | V4 token net path (deployed format) | unset (off) | `main` ~L9300 |
| `STS_OOC_MCTS` | Opt-in live OOC MCTS selector; requires native V4, a compatible combat artifact, and ordinary exact-10k Silver real combat with effective cap 32768. Native leaf mode requires `v_win`; boss leaf mode does not call it, though the unchanged fallback policy may. | `0` | `configureLiveOocMcts`, `runFullRunOOC` |
| `STS_OOC_MCTS_SIMS` | Positive simulations per supported OOC root | `512` | `configureLiveOocMcts` |
| `STS_OOC_MCTS_COMBAT_MODEL` | Compatible native combat-transition artifact; when unset with OOC MCTS enabled, uses the tracked qualified DeepSets + active-Lizard artifact. Explicit paths override it; empty values and load failures are fatal. | unset (automatic default stack) | `configureLiveOocMcts` |
| `STS_OOC_MCTS_COMBAT_RESOLVER` | Research only (§411). `silver` replaces the CTM with native Silver: each imagined combat is played at `STS_OOC_MCTS_SILVER_SIMS` simulations per root with the root prior on, on a redraw of the six combat RNG streams from the planner RNG. Requires `STS_SILVER_ROOT_PRIOR`, `_WEIGHT`, `STS_SILVER_ROOT_PRIOR_SCOPE=override` and exact root budgets; excludes the CTM variables. Any other value is fatal. | unset (CTM) | `configureLiveOocMcts`, `SilverCombatTransitionSampler` |
| `STS_OOC_MCTS_SILVER_SIMS` | Silver simulations per root for the Silver resolver (1..999999) | unset (required with the resolver) | `configureLiveOocMcts` |
| `STS_OOC_MCTS_BREW_FALLBACK_MODEL` | Pinned current-standard V2 artifact (SHA256 `e9a18951710fdfe9e1a81a2703090a41f039067c670a1d8a0393b5e7e8e0ddfd`) used only for pre-combat Entropic Brew states when the primary artifact declares that fallback contract. The automatic OOC CTM stack supplies it by default; an explicit path overrides it, and metadata/bytes are checked. | standard Attention artifact with automatic default stack; otherwise unset | `configureLiveOocMcts` |
| `STS_OOC_MCTS_ACTIVE_LIZARD` | Enables or disables the qualified active-Lizard correction. Accepts only `0` or `1`; the automatic default CTM stack enables it, `0` is a diagnostic rollback, and `1` with a custom combat model requires a Brew fallback. Active Lizard + Brew, Fairy, and Mark-of-the-Bloom retain their declared boundary behavior. | `1` with automatic default stack; otherwise `0` | `configureLiveOocMcts` |
| `STS_OOC_MCTS_LEAF_VALUE` | `screengbm`, `native`, `direct`, `screen`, `constant`, `boss`, or `bossrollout`. `screengbm`: covered non-map screens get `sigmoid(logit(X2-B) + GBM residual)` over run and public screen features, anchored on the pinned `models/candidates/v_win_x2b_trees.txt` (also at MAP leaves) (ADR-0027). `native`: bounded policy-chain playout to the next MAP, then `v_win`. `direct`: `v_win` at the first non-combat state, no playout (research). `screen`: #379 MLP on four screen families (research). Boss mode averages a survival-dominant expected-HP utility over all ten Act1--4 bosses and does not call `v_win` at the leaf. `bossrollout` (research, ledger §391 negative): the policy-chain continuation with CTM fights runs until the next boss after the searched decision is beaten (1) or the player dies (0); an active Lizard Tail the CTM cannot price is spent inside the rollout | `screengbm` (ADR-0027) | `configureLiveOocMcts`, `OocGameContextModel::evaluateLeafImpl` |
| `STS_OOC_MCTS_SCREEN_LEAF_MODEL` | Screen leaf model: GBM residual trees for `screengbm`, exported MLP for `screen` | `models/candidates/screen_leaf_gbm_v1.trees` for `screengbm`; required for `screen` | `configureLiveOocMcts` |
| `STS_OOC_MCTS_LEAF_WIN_MODEL` | Research: logistic CompactTreeNet file that values `native`/`direct` leaves instead of the process `v_win` (`STS_WIN_NET`/B0); rejected with the screen, boss, bossrollout and constant leaves. `tools/vwin_export_ensemble.py` writes such files (e.g. `models/candidates/v_win_f2_e3_trees.txt`, F2 from §396) | unset | `configureLiveOocMcts`, `OocGameContextModel::anchorValue` |
| `STS_OOC_MCTS_EARLY_STOP` | Strict visit-lock stopping even without a non-aborting provider guarantee; may skip later support/continuation aborts; `0` restores guarantee requirement; root-lock trace overrides stopping | `1` when OOC MCTS enabled | `configureLiveOocMcts`, `OocMctsPlanner::search` |
| `STS_OOC_MCTS_MERGE_OUTCOMES` | `1`: pool sampled chance-node successors whose search-equivalence keys are equal into one decision node (#384); `0` keeps independent particles | `0` | `applyLiveControl`, `OocMctsPlanner::search` |
| `STS_OOC_MCTS_ROOT_LOCK_TRACE` | Optional JSONL per searched root: hypothetical earliest strict visit lock/action/remaining budget/suffix time and eventual abort/completion; forces full budget and suppresses all root shortcuts; no support qualification | unset (off) | `configureLiveOocMcts`, `selectOocMctsAction` |
| `STS_OOC_MCTS_REUSE_TRACE` | Optional JSONL per real OOC decision: does the real root's public (and RNG-counter) fingerprint match a stored decision node of the previous completed non-singleton search, at what depth, on which root branch, and with how many visits/subtree nodes. Observation only; captures each tree (cap 100,000 nodes); rejects `STS_OOC_MCTS_GRAPH_FILE`. Analyze with `tools/analyze_ooc_reuse_trace.py`. Fresh path per run. | unset (off) | `configureLiveOocMcts`, `selectOocMctsAction` |
| `STS_RUN_PROFILE` | Append-only JSONL for real floor timing/counters and in-search OOC root checkpoints/exact branching; preserves budgets, early stops and singleton shortcuts. Analyze with `tools/analyze_run_profile.py`. Fresh path per run. | unset/off | `runFullRunOOC`, `selectOocMctsAction`, `oocMctsPolicyStep` |
| `STS_OOC_MCTS_TRACE` | Optional completed-run CSV of search/continuation/combat counts and timing plus `.support.jsonl`; works with OFF | unset | `writeLiveOocMctsTrace` |
| `STS_OOC_STRATEGIC_TOK_CHECK` | First-decision glob parity hook | `0` (off) | `main` ~L9305 |
| `STS_OOC_STRATEGIC_Q` | Q-head vs V2 successor-value scoring; `0` = V2 | `1` (Q head) | `main` ~L9310 |
| `STS_OOC_STRATEGIC_SCORE` | `policy` = sigmoid(policy logit) scoring (5.7.2) | `q` (Q head) | `main` ~L9380 |
| `STS_OOC_STRATEGIC_MARGIN` | Global one-ply gate threshold (V units) | 1.0 | `main` ~L9375 |
| `STS_OOC_STRATEGIC_REST` | Campfire Q gate (5.5.2) | `0` (off) | `main` ~L9315 |
| `STS_OOC_STRATEGIC_EVENT` | Event Q gate (5.5.3) | `0` (off) | `main` ~L9320 |
| `STS_OOC_STRATEGIC_SHOP` | Shop Q gate (R6) | `0` (off) | `main` ~L9325 |
| `STS_OOC_STRATEGIC_TREASURE` | Treasure Q gate (R6) | `0` (off) | `main` ~L9330 |
| `STS_OOC_STRATEGIC_BOSS_RELIC` | Boss relic Q gate (R6) | `0` (off) | `main` ~L9335 |
| `STS_OOC_STRATEGIC_MAP` | Map route Q gate (M1) | `0` (off) | `main` ~L9340 |
| `STS_OOC_STRATEGIC_GATE` | `regret` replaces margin rule with regret-gate (Wave B) | margin rule | `main` ~L9412 |
| `STS_OOC_STRATEGIC_GATE_EPS` | Regret threshold ε | 0.03 | `main` ~L9410 |
| `STS_OOC_STRATEGIC_MARGIN_CARD` | Per-screen margin overrides (fall back to global when unset/negative) | −1.0 (use global) | `main` ~L9385+ |
| `STS_OOC_STRATEGIC_MARGIN_REST` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_EVENT` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_SHOP` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_TREASURE` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_BOSS_RELIC` | — | −1.0 | `main` |
| `STS_OOC_STRATEGIC_MARGIN_MAP` | — | −1.0 | `main` |
| `STS_COLLECT_KEYS` | Collect act-4 keys (emerald/sapphire in rewards, ruby at rest) | `0` (off) | `main` ~L9244 |

## OOC model-driven decisions

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_REST_V_THRESH` | Rest-site heal-gain threshold | unset | `main` ~L9243 |
| `STS_REST_WIN` | Win-rate rest policy (heal vs upgrade by P(win)) | `1` (ON, `g_restWin`) | `main` ~L9247 |
| `STS_CARD_WIN` | Card picks by P(win) instead of V_floor | `0` (off) | `main` ~L9252 |
| `STS_CARD_WIN_SKIP` | Skip threshold for card-win picks | 0.0 | `main` ~L9254 |
| `STS_CARD_NN` | Card picks via deck-set NN | `0` (off) | `main` ~L9258 |
| `STS_CARD_ACTION` | Direct paired card/skip action NN | `0` (off) | `main` ~L9265 |
| `STS_SHOP_WIN` | Shop bundles scored by P(win) | `0` (off) | `main` ~L9525 |
| `STS_BOSS_RELIC` | Boss relic pick via V_win | `0` (off) | `main` ~L9440 |
| `STS_NEOW_V` | Neow bonus pick via V_win | `0` (off) | `main` ~L9445 |
| `STS_PATH_V` | Model-driven pathing (forward-map feats) | `0` (off) | `main` ~L9480 |
| `STS_PATH_GRAPH` | Graph NN path scores | `0` (off) | `main` ~L9485 |
| `STS_PATH_ACTION` | Paired route-action NN | `0` (off) | `main` ~L9490 |
| `STS_EVENT_V` | Model-driven event choices | `0` (off) | `main` ~L9500 |
| `STS_BOSS_V` | Boss-survival V blended into near-boss picks | `0` (off) | `main` ~L9630 |
| `STS_VPATH` | V-strength path modulation (needs v_server) | `0` (off) | `main` ~L9660 |
| `STS_POTION_SAVE` | Dynamic potion-saving | `0` (off, shelved §35) | `main` ~L9510 |

## OOC experimental / datagen

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_OOC_ACTION_NN` | OOC decisions via next-combat action NN | `0` (off) | `main` ~L9270 |
| `STS_OOC_CHECKPOINT_NN` | OOC via native checkpoint-distilled NN | unset (off) | `main` ~L9277 |
| `STS_OOC_MAP_ROUTE` | C_psi route search (M2) | `0` (off) | `main` ~L9345 |
| `STS_OOC_MAP_ROUTE_HORIZON` | M2 horizon (clamped 2..5) | 3 | `main` ~L9346 |
| `STS_CPSI_NN` | C_psi combat outcome surrogate path; `1` = default | unset (off) | `main` ~L9350 |
| `STS_OOC_SHOP_BEAM` | Multi-step shop beam search (B1) | `0` (off) | `main` ~L9362 |
| `STS_OOC_SHOP_BEAM_WIDTH` | B1 beam width | 32 | `main` ~L9363 |
| `STS_OOC_SHOP_BEAM_DEPTH` | B1 search depth (0 = until leave) | 0 | `main` ~L9365 |
| `STS_OOC_SHOP_BEAM_BUDGET` | B1 max expanded nodes per decision | 4096 | `main` ~L9367 |
| `STS_SIM_ADAPT` | Adaptive per-fight sim budget; uses C_psi unless `STS_SIM_ADAPT_CTM` is set | `0` (off) | `main` ~L8820 |
| `STS_SIM_ADAPT_CTM` | Qualified native CTM artifact for deterministic death/winning-HP adaptive budgeting; unsupported fights keep the caller's base budget | unset (C_psi path) | `main` ~L8825 |
| `STS_SIM_ADAPT_MIN_FRAC` / `STS_SIM_ADAPT_MAX_FRAC` | Clamp adaptive fight budgets as fractions of the caller's base budget | `0.4` / `2.0` | `main` ~L8822 |
| `STS_DG_TEMP` | Datagen softmax temperature | unset | `main` ~L9675 |
| `STS_BOSS_DRAFT` | Boss-gated rollout drafting | `0` (off) | `main` ~L9570 |
| `STS_ACT_FIGHT_PROBE_DRAFT` | All-act encounter rollout draft | `0` (off) | `main` ~L9580 |
| `STS_ACT_FIGHT_PROBE_ALL_OOC` | Acts 1-3 all-OOC checkpoint rollout | `0` (off) | `main` ~L9620 |

## Simulator health monitor

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_SIM_HEALTH_CAPTURE_DIR` | While set, every `[sim-health][HARD]` failure serializes the offending `BattleContext` to `<dir>/sim_bug_<seed>_f<floor>_t<turn>_d<decision>_<reason>_<seq>.bin` (raw `serializeBattleContext` blob) plus a `<stem>.txt` metadata sidecar (reason, seed, floor, encounter, turn, decision index, player HP, outcome, input state, card-select task/pickCount, pile sizes, action bits, RNG counters, searcher/fair mode). Diagnostics print regardless. See `behavior/simulator-health-monitor.md`. | unset (off) | `SimHealth.cpp::reportSimHealthFailure` |

## Datagen / generation modes

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STRATEGIC_SAMPLES_PER_RUN` | Max strategic rows per run | 5000 | `main` ~L9422 |
| `STRATEGIC_SAMPLE_ALL` | Sample all OOC decisions (not just first N) | `0` | `main` ~L9424 |
| `STRATEGIC_BRANCH_FIGHTS` | Branch-fight futures per action | 2 | `main` ~L9426 |
| `STRATEGIC_BRANCH_SIMS` | Comma-separated sim budgets per branch | unset | `main` ~L9428 |
| `STRATEGIC_BRANCH_FUTURES` | Futures per branch fight | 4 | `main` ~L9435 |
| `STS_LEAFDIAG_PER_STRATUM` | Leafdiag reservoir capacity per stratum | varies | `main` ~L9880 |
| `STS_LEAFDIAG_DEEP_DEPTH` | Leafdiag deep-tree stratum threshold | varies | `main` ~L9885 |
| `STS_FRONTIERGEN_PER_STRATUM` | Frontiergen reservoir capacity per stratum | varies | `main` ~L9890 |
| `STS_CTM_RESEARCH_CANDIDATE_MANIFEST`, `STS_CTM_RESEARCH_CANDIDATE_MANIFEST_SHA256` | C++ CTM runtime (#418 retrain): set together; a `ctm_research_candidate_v1` manifest, a `_v2` one that also pins a declared HP domain, or a `_v3` one that also lists each artifact's capabilities (`escape`, `writhingRitual`, `lizardBrew`, `lizardFairy`), and its SHA256. Artifacts whose metadata declares `researchCandidate` with that `candidateId`, and whose bytes the manifest lists, are checked against its identity pins instead of production's; everything else keeps the production pins. A candidate can never claim the production default. See `architecture/out-of-combat.md` | unset (production pins only; candidate artifacts are rejected) | `combat_transition_runtime.cpp` |
| `STS_CTM_PINS` | Python CTM training/export tools only (#418 retrain): a `ctm_retrain_pins_v1` JSON file that replaces their pinned production corpus, split, prepared-array, checkpoint and row-count identities. Every key must be present unless the call site keeps the production default (`required=False`); `python tools/ctm_pins.py` lists the keys and defaults; `tools/ctm_retrain_pins.py` stages the file through the chain. JSON receipts written through `combat_transition_surrogate.json_dump` record `ctmPinsSha256`, which tools strip (`ctm_pins.strip`) before comparing a re-read receipt | unset (production pins) | `tools/ctm_pins.py` |

## Benchmark / run control

| Variable | Effect | Default | Parse site |
|----------|--------|---------|------------|
| `STS_STOP_AFTER_ACT` | Stop benchmark after Act N boss; at A20 with N=3 it waits for the second Act-3 boss (`run_driver.cpp`, §402) | 0 (full run) | `main` ~L9627 |
| `STS_FORCE_RELIC` | Force a relic at run start (paired A/B), removing it from relic pools; forced Lizard Tail is initialized active (`data=1`), while other forced relics retain zero-initialized data | unset | `main` ~L9690; `run_driver.cpp::installRunForcedRelic` |

## Known limitations

- `STS_SILVER_ADAPTIVE` and `STS_SILVER_LEARNED_STOP` have mode-dependent
  defaults (ADR-0018, ADR-0020, ADR-0026); the exact precedence is in `apps/one_combat.cpp::main`.
- This table intentionally omits legacy server-mode env vars consumed only by
  `v_server.py` (not `one_combat`).

## Relevant code

- `apps/one_combat.cpp::main` (~L9208–L9965) — single parse site for all env vars above
- `EXPERIMENTS.md` — experiments that introduced each flag
- `docs/knowledge-base/evaluation/current-baselines.md` — current recommended configuration

# E2c native model validation

The E2c native model is consumed only by the explicit `one_combat runwinparity`
validation command. It is not invoked by ordinary gameplay or by the `e2cgen`
RAW/POST producer.

- `STS_RUNWIN_SHADOW_MODEL`: compact E2c RAW logistic-tree model supplied to
  `runwinparity`; the historical variable name is retained for parity-fixture
  compatibility.

Searcher3 and all its `STS_S3_*`, `STS_REUSE_*`, particle-probe and fightrep
variables were removed by ADR-0019.
