# Handoff plan — Self-play relabeling (5.7.3): retrain the strategic one-ply Q gate model on labels from the current combat controller

Date: 2026-08-07. Status: **READY TO EXECUTE** (plan-mode handoff, no context assumed).
Owner: any new agent. Repo: `sts_lightspeed/` (working dir `.../Documents/sts/sts_lightspeed`).

---

## 0. Read these first (required, in order)

1. `AGENTS.md` (repo root of `sts_lightspeed/`) — operating contract, traps, recording rules.
2. `docs/knowledge-base/README.md` (KB index) + `docs/knowledge-base/evaluation/current-baselines.md`.
3. `EXPERIMENTS.md` §124–§130 (the winrate wave this plan extends; **§126 = the deployed vnet; §129 = the gate-stack combat datagen follow-up, NULL; §130 = counter-aware OOC closed**). §124a/b/c, §127, §128 belong to a parallel agent's sessions — check the file tail for new entries and use the **next free § number** before writing (see §7).
4. `docs/knowledge-base/architecture/out-of-combat.md` (strategic model), `docs/knowledge-base/architecture/training-and-inference.md` (producers/trainers), `docs/knowledge-base/architecture/combat-search.md` (S3 + vnet).
5. This plan's parent: `docs/knowledge-base/plan-winrate-ideas-2026-08-07.md` §5.1 (Wave 3, deferred until now).

Concurrency note: a parallel agent owns `plan-value-targets-2026-08-07.md` (combat leaf/value work) and edits the same shared files (EXPERIMENTS.md, decision-log README, one_combat.cpp). Before writing anything, `git status` + `git log --oneline -3`; stage only your intended files; never `pkill -f v_server.py`; never delete ignored buffers.

---

## 1. Goal and hypothesis

**Goal:** generate new Tier-B strategic labels (`strategicgen2` output) with the **current combat controller** (S3−belief−chain + live-valid + the deployed vnet, ~12pp stronger than the controller that produced the existing labels), retrain the deployed model family (V4 token net) on them, and gate whether the retrain beats the deployed artifact.

**Hypothesis (action-plan 5.7.3):** the training distribution determines strategic-model quality. All existing strategic labels predate the honest enumerator (§113), live-valid (§122/§123) and the vnet (§126). The labels' `labelWon` (branch fight outcomes) are the part that changes; the `chosen`/Tier-A side stays heuristic-OOC by datagen design (verified, see §3).

**Pre-registered verdict rule:** candidate (new-data tok) ≥ control (old-data tok, same recipe) with paired CI excluding a meaningful loss → promotion path (second block 250000+ and @3k/64p). **Null → 5.7.3 closed as a distribution lever** — record it, do not iterate on data volume (the §62/§100/§105/§127/§129 pattern: offline gains and volume do not transfer).

---

## 2. Current state (verified 2026-08-07, HEAD c0aeb0a)

- **Deployed recommended config** (the gate reference): fair S3−belief−chain, `STS_S3_PARTICLES=64`, V4 one-ply gate stack (`STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_final.native`, REST/EVENT/SHOP/TREASURE/BOSS_RELIC=1, `STS_OOC_STRATEGIC_MARGIN=1.0`), and the **vnet default** (`build/v_combat_honest.txt` @ α0.3, §126). Recorded reference on block 126700–126955 @1k/64p: **`build/vnet_all_a03_1k.csv` = 50.4% wins** (this IS the deployed-config control CSV — reuse it, do not re-run).
- `build/strategic_tierb.csv` (6.5 GB, §73 corpus, the deployed tok's original training data) exists locally — control-retrain input.
- `build/strategic_qwin_cal.csv` (7.57 GB, §95/§96 corrected corpus, 809k rows/1,295 seeds) exists locally — optional secondary input.
- Deployed artifact metrics for recipe validation: `selfplay/models/ooc_strategic_tok_final_metrics.json`.
- GPU training machine: local RTX 3060 Ti (trainers default CUDA; `STRAT_DEVICE=cpu` only for smokes).
- GCP benchmark server `sts-test` (24 threads, preemptible). Only reachable via `/home/philippherrmann/google-cloud-sdk/bin/gcloud` — plain ssh does NOT resolve it. Server tree = `/home/philippherrmann/sts_sweep` (non-git rsync copy; sync via tar-over-ssh, then `cmake --build build -j 24`). **Check the box is free before every long run** (`uptime`, `ps aux | grep one_combat`) — the parallel agent uses it.

---

## 3. Verified facts about `strategicgen2` (do not re-derive; details for debugging)

- Mode: `one_combat strategicgen2 <nSeeds> <sims> <asc> <out> <seedOff>` (apps/one_combat.cpp, `strategicGen2`/`runStrategicGenSeed2`).
- Env knobs: `STRATEGIC_SAMPLE_ALL=1` (label every decision; required), `STRATEGIC_BRANCH_FIGHTS` (default 3), `STRATEGIC_BRANCH_SIMS` (default 150,100,50), `STRATEGIC_BRANCH_FUTURES` (default 1 — the §84-optimal contract, keep), `STRATEGIC_SAMPLES_PER_RUN`.
- **Main-run OOC policy is heuristic** (comment: "mirrors runFullRunOOC with no opt-ins", apps/one_combat.cpp:6748) — the one-ply gate envs do NOT affect it. `chosen` rows keep their old meaning.
- **Branch continuation OOC is also heuristic** (`finishOocCounterfactual`, apps/one_combat.cpp:4360 — no `oocOnePly*Policy` calls).
- **Branch battles use the configured searcher.** With the envs in §5, branch battles run S3−belief−chain with the live-valid and vnet **defaults** (envs are parsed before mode dispatch; the "STS_VNET not loaded" warning at apps/one_combat.cpp:6834 must NOT appear — verify in the smoke).
- Output CSV: one row per legal action per decision, rich state block = the 1017-col `richRow` between `chosen` and `won`, then terminal cols, then the Tier-B suffix `labelWon,labelHp,labelFloor,labelBootstrap` on sampled rows. Schema is unchanged → `train_strategic_tok.py` consumes it directly (it validates "the 1017-col rich state block" itself; `TOK_PROBES_FILE` unset = no probes, §80 says probes are neutral — skip them).
- `strategicgen2` **appends** when `seedOffset > 0` → re-runs duplicate rows. Datagen is **preemption-safe by chunking** (distinct offsets per chunk, concatenate after).
- Row volume reference: §104's set ≈ 809k rows / 1,295 seeds.

---

## 4. Phase 0 — Verification & smoke (local, 0.5–1 h)

```bash
cmake --build build -j   # HEAD must build clean
export STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0
STRATEGIC_SAMPLE_ALL=1 ./build/one_combat strategicgen2 10 1000 0 build/sp_smoke.csv 300000 2>&1 | tail -5
```

Verify: banner shows Searcher3, `S3-abl[...]=01010`, `[live-valid … ON]`, `[V_combat leaf default ON: build/v_combat_honest.txt, alpha 0.3 …]`; **no** line-6834 vnet warning; CSV header matches the trainer's expectations:

```bash
python3 - << 'EOF'
import pandas as pd
h = pd.read_csv('build/sp_smoke.csv', nrows=0).columns.tolist()
i = h.index('chosen'); j = h.index('won')
print("state cols:", j - i - 1)   # must be 1017
print("tierB suffix ok:", h[-4:])
EOF
```

Also: row count per seed (expect ≈ 100–700 rows/seed; record it for the scale estimate), and a quick label sanity (non-empty `labelWon` fraction with `STRATEGIC_SAMPLE_ALL=1`). Run `./build/test` + `ctest --test-dir build --output-on-failure` (expect the known CRLF `selfplay_syntax` failure only).

## 5. Phase 1 — Self-play datagen (GCP, ~1–1.5 h wall; check box free first)

Seeds **300000–301499** (fresh; no overlap with any recorded seed range). Three chunks of 500, one process each:

```bash
# per chunk (on sts-test, after syncing the tree and building):
export STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STRATEGIC_SAMPLE_ALL=1
OMP_NUM_THREADS=24 ./build/one_combat strategicgen2 500 1000 0 build/sp_300000.csv 300000
OMP_NUM_THREADS=24 ./build/one_combat strategicgen2 500 1000 0 build/sp_300500.csv 300500
OMP_NUM_THREADS=24 ./build/one_combat strategicgen2 500 1000 0 build/sp_301000.csv 301000
```

Run with `nohup` (launch pattern that works: `nohup ./script.sh > out 2>&1 < /dev/null &`; ssh will hang — that's normal, poll separately). Pull the three CSVs (`gcloud compute scp`, server→local works), concatenate (header once) to `build/strategic_sp_1500.csv`. Sanity: total rows ≈ 0.8–1.3M; per-decision `labelWon` spread; **§104 Step-1-style diagnostic**: `argmax(labelWon)` vs `chosen` agreement overall and per screen (REST/MAP/EVENT/BOSS_RELIC/REWARDS/TREASURE/CARD_SELECT/SHOP) — the old corpus read 38.0% strict / 58.1% in-set; record the new numbers (if they moved a lot, the labels genuinely changed; if not, the controller change did not shift the label ranking — informative either way, do not gate on it).

## 6. Phase 2 — Training (local GPU, ~1–2 h per run; run control and candidate with the SAME recipe)

Recipe: `train_strategic_tok.py` defaults (GPU; `STRAT_TOK_COMPILE=1` is default ON — needs CPython dev headers; `torch._dynamo.config.suppress_errors` falls back to eager). No probes. Before each run: `rm -f <OUT>_tok_state.bin` (killed-trainer corruption trap). Smoke first: 2-epoch CPU slice on a CSV slice (`STRAT_DEVICE=cpu`, tiny epoch count via `STRAT_EPOCHS`).

```bash
# Control (old data):
python3 train_strategic_tok.py build/strategic_tierb.csv build/tok_control.pt
python3 export_strategic_tok.py build/tok_control.pt selfplay/models/ooc_strategic_tok_control.native
# Candidate (new self-play data):
python3 train_strategic_tok.py build/strategic_sp_1500.csv build/tok_sp.pt
python3 export_strategic_tok.py build/tok_sp.pt selfplay/models/ooc_strategic_tok_sp.native
```

Validate the control against the deployed artifact's `ooc_strategic_tok_final_metrics.json` (same metric shapes; close ≠ required — recipe-drift is precisely what the control isolates). Offline compare on a held-out split of the NEW data (q_top1, policy top-1) for control vs candidate — per §62, expect flat-or-worse offline; that alone is a recorded finding, not a gate. Exporter parity checks must pass (numpy-vs-torch asserts).

## 7. Phase 3 — Paired gate (GCP, ~1–1.5 h; truncate CSVs first — bestbench appends without dedup)

Two arms on block 126700–126955, @1k/64p, full stack, fair S3−belief−chain, vnet default:

```bash
export STS_FAIR=1 STS_SEARCHER3=1 STS_S3_BELIEF=0 STS_S3_CHAIN=0 STS_S3_PARTICLES=64
export STS_OOC_STRATEGIC_TOK_NN=selfplay/models/ooc_strategic_tok_control.native
export STS_OOC_STRATEGIC_REST=1 STS_OOC_STRATEGIC_EVENT=1 STS_OOC_STRATEGIC_SHOP=1
export STS_OOC_STRATEGIC_TREASURE=1 STS_OOC_STRATEGIC_BOSS_RELIC=1 STS_OOC_STRATEGIC_MARGIN=1.0
OMP_NUM_THREADS=24 ./build/one_combat bestbench 1000 256 0 126700 build/gate_tok_control.csv
# repeat with STS_OOC_STRATEGIC_TOK_NN=...tok_sp.native → build/gate_tok_sp.csv
```

Pair with `python3 paired_analysis.py build/gate_tok_sp.csv build/gate_tok_control.csv sp control` (note: the tool reports delta = B − A). Also pair both against `build/vnet_all_a03_1k.csv` (the deployed reference, 50.4%). Verify the load messages per arm (`[OOC one-ply strategic TOK net ON: …]` for the RIGHT artifact — a file existing is not evidence it loaded).

**Decision (pre-registered):** candidate ≥ control, CI excluding a meaningful loss → second gate on block 250000+ (paired control on the same block) + @3k/64p point; then promotion decision per the §123/§126 precedent (two gates + recorded cpu-trade call). Anything else → **record 5.7.3 as falsified at the distribution lever** (null counts, it completes the hypothesis chain).

## 8. Phase 4 — Recording (definition of done)

- EXPERIMENTS.md: **one entry per phase-group** (datagen + offline diagnostic; training; gate verdict) with the full provenance recipe (date, executable mode, env flags incl. every `STS_*`/`STRATEGIC_*`, model paths + sha256 of the exported natives, seeds, threads, regime, searcher, metric formula, artifacts). Use the **next free § number** (grep `^## §` tail; the parallel agent collides — §130 was the last written as of this plan).
- Decision log: `YYYY-MM-DD-selfplay-relabeling.md` per `docs/knowledge-base/decision-log/_template.md` + update the README index.
- Plan file: mark `plan-winrate-ideas-2026-08-07.md` §5.1 executed/closed with the verdict.
- KB: `training-and-inference.md` (datagen provenance note if the workflow changed), `current-baselines.md` ONLY on promotion.
- Commit (repo convention: artifacts ship with sha256 + docs in one commit; the working tree may contain the parallel agent's in-flight edits — stage only intended files, mention interleaving in the commit message). `git diff --check` clean.

## 9. Traps (AGENTS.md distillate)

- Combat loops terminate on `bc.outcome == Outcome::UNDECIDED`; never assume a model loaded because its file exists.
- Never compare fair and known-RNG results as one series. `STS_FAIR=1` + `STS_SEARCHER3=1` are required for the fair-S3 regime.
- `fairgen` datagen is NOT covered by the live-valid default (parse order) — not used here, but don't extrapolate.
- Killed trainer → corrupt `_tok_state.bin` (byte-size-valid but wrong): `rm` before any rerun.
- `bestbench`/`strategicgen2` append without dedup — truncate before runs, chunk with distinct offsets.
- GCP instance is preemptible: chunked datagen, verify the box is free first, poll by CSV row counts (`wc -l`) rather than logs (output buffering).
- `Node`/`Edge`/searcher header changes need a full rebuild — none expected here (no C++ changes planned; `strategicgen2` needs no code change).
- The parallel agent edits shared docs concurrently — stage explicitly, re-check § numbers at write time.

## 10. Open decisions (recommended defaults chosen — override only with a reason)

1. **Control retrain on old data: YES** (required to isolate the data effect from recipe drift).
2. **Scale: 1,500 seeds** (matches the §104 1,295-seed volume; ~1–1.5 h GCP).
3. **Model family: tok (V4) only** — it is the deployed family; the flat V5 gate arms were negative (§96/§104) and would double the work for a non-deployed comparison.
4. **Full-teacher variant (wire the one-ply gates into `strategicgen2`'s OOC, so `chosen` also comes from the deployed policy): NOT this pass** — it changes the Tier-A label meaning and needs its own datagen + its own pre-registration. Note it as a follow-up if the basic relabeling shows signal.
5. **Probes (`TOK_PROBES_FILE`): OFF** (§80 neutral).

Estimated total: ~1 day calendar (mostly GPU/GCP waiting), ~3–4 h hands-on.
