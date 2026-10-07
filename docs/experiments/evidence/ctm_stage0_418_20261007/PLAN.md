# #418 Stage 0: CTM transfer and optimism check (frozen plan)

Authorized by Philipp on 2026-10-06 ("yes lets go. can we do 128 paired seeds and share the load on 10 local workers and 5 cloud sessions with 4 workers each?"). This plan is the frozen candidate. Do not change it while parts run. The analysis is owned by the New CTM stack thread.

## Frozen candidate

- **SHA:** `46153506cf183adcf422a0877310caa7747c1782` (main; it includes #419, #420 `d09a5519`, #421 `86a4619f`).
- **Mode:** `one_combat combattransitiongen N 10000 0 OUT.jsonl SEED_LO TEACHER.json`, run through `tools/seed_guard.sh`, Release build (`linux-gcc-release`), ascension 0, `OMP_NUM_THREADS=1`, one process per worker.
- **RNG regime:** project fair (`STS_FAIR=1`). Silver uses its private chance search.
- **Arms (same seeds, same binary, paired per seed):**
  - `exact10k`: flat exact-10k Silver, the old CTM teacher contract (`STS_SILVER_EXACT_ROOT_BUDGETS=1`, learned stop off).
  - `learned`: production learned stopping (ADR-0026). `budget_policy=learned_stop`, model `gbt-770201c31f7b`, threshold `0.0323`, cap 10k, `STS_SILVER_EXACT_ROOT_BUDGETS=0`, `STS_SILVER_LEARNED_STOP=1`.
  - Both arms: `STS_SEARCHER3=0`, `STS_SILVER_SEARCH=1`, `STS_SILVER_REUSE_CAP_MODE=allocated` (32k), `STS_SILVER_ADAPTIVE=0`, `STS_SILVER_VNET_LEAF_DIRECT=0`, `STS_EXECUTABLE_GIT_SHA=<SHA>`. Every other `STS_*` variable is cleared by `env -i`.
- **Collection OOC policy:** the generator's built-in chain (greedy rewards, `chooseMapAction`, `evalCardRewardPolicy`, `stepOutOfCombatPolicy`), as used for the 25k corpus. Models are `models/v_rich_trees.txt` and `models/v_win_trees.txt`, with hashes recorded in each teacher JSON.
- **Model under test (analysis only, not loaded by collection):** production CTM `selfplay/models/combat_transition_deepsets_lizard_t2.native` plus the Attention V2 Brew fallback plus the active-Lizard q/r/T2 correction, at the same SHA.
- **Seeds:** `50000000..50000127` (128 seeds, fresh; 41M..49M are taken). Smoke seeds `50001000..50001002` were used for the smoke runs only.
- **Teacher JSON:** `bin/make_teacher.py` writes one per arm and per binary, because `executable_sha256` must match the local build. Each machine therefore freezes its own two teachers. Pairing stays valid because both arms of a seed always run on the same binary.
- **Rows:** `combat_transition_row_v2` / `combat_transition_v1`, predictor `combat_predictor_input_v1` (field hash `1a92692da9247008`). These are the same schemas as the 25k corpus. Each JSONL file has a hash-bound `.manifest.json`.
- **Cost (measured on the smoke):** one seed with both arms takes about 115 s on one core (about 25 fights per arm). The whole stage is about 4 CPU-hours, roughly 10 to 15 minutes per part.

## Analysis and frozen decision rule (owned by the New CTM stack thread)

The analysis is offline only and makes no gameplay change. The production CTM scores every row of both arms. Seeds are the resampling unit: CIs are 95% source-bootstrap with 2,000 replicates, resampling seeds and keeping both arms of a seed together. Rows that are quarantined or out of CTM support are counted and reported. They are not scored.

Primary, on the `learned` arm (what real combat now plays):
1. **Optimism:** mean signed survival bias, predicted P(win) minus observed, overall and by room class (normal, elite, boss) x act. The same is measured for post-combat HP on won fights (predicted mean minus observed, in HP).
2. **Boss calibration:** boss-fight survival bias and the reliability table.

Secondary:
3. **Teacher transfer:** paired `learned` minus `exact10k` difference in per-fight survival NLL and signed-HP NLL, plus the same optimism metrics on `exact10k`. These show how much of any bias comes from the teacher change and how much was already there.
4. Support/refusal rate per arm (#369/#370 gaps), and fights per run.

Decision (frozen before running):
- **Path A** (keep the CTM; relax the `run_driver.cpp:248` guard behind a research flag) only if all three hold: the learned-minus-exact survival NLL delta has a 95% CI upper bound below 0.01 nat per fight; the HP NLL delta has a CI upper bound below 0.05 nat; and the learned-arm boss survival bias has a CI upper bound below +0.05.
- **Path B** (regenerate the corpus with the learned-stop teacher and refit) otherwise.
- If the boss bias is significantly positive on **both** arms, the optimism is not caused by the teacher change. That gets reported as a model or coverage problem: Path B alone would not fix it, and the next step goes to Philipp.

**Inference:** the expected sample is about 3,000 fights per arm but only about 128 boss-1 fights and few deaths, so the boss CI will be wide. With n=128, a null result on boss bias is inconclusive, not proof of calibration.

## Shards (disjoint; union = 50000000..50000127)

| Part | Workers | Seeds | Output dir |
|---|---|---|---|
| local | 10 | 50000000..50000042 (43) | `<repo>/build/ctm-stage0/part-local/`, returned to `/mnt/project-files/ctm-stage0/part-local/` |
| cloud1 | 4 | 50000043..50000059 (17) | `/mnt/project-files/ctm-stage0/part-cloud1/` |
| cloud2 | 4 | 50000060..50000076 (17) | `/mnt/project-files/ctm-stage0/part-cloud2/` |
| cloud3 | 4 | 50000077..50000093 (17) | `/mnt/project-files/ctm-stage0/part-cloud3/` |
| cloud4 | 4 | 50000094..50000110 (17) | `/mnt/project-files/ctm-stage0/part-cloud4/` |
| cloud5 | 4 | 50000111..50000127 (17) | `/mnt/project-files/ctm-stage0/part-cloud5/` |

The per-worker chunks are hard-coded in `bin/run_part.sh`. Each worker runs `exact10k`, then `learned`, on its chunk. A part is finished when `<out>/DONE` exists. It lists each worker's `completed=N/N quarantined=Q rows=R` line and the sha256 of every JSONL and manifest file. Rerunning the same command resumes: finished worker-arms are skipped via `*.done`, and a half-written arm is rerun from scratch.

## Cloud part commands (cloudK, K = 1..5)

`/mnt/project-files` is noexec, so run the scripts with `bash`/`python3` and copy the binary to local disk first.

```bash
cd /home/user/sts_ai            # the session's clone of pherrman1/sts_ai
git fetch origin main && git checkout --detach 46153506cf183adcf422a0877310caa7747c1782
git submodule update --init     # main clone only, not a linked worktree
cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j4
mkdir -p /tmp/ctm-stage0 && cp build/linux-gcc-release/one_combat /tmp/ctm-stage0/one_combat-46153506
(cd /mnt/project-files/ctm-stage0 && sha256sum -c bin/SHA256SUMS)
nohup bash /mnt/project-files/ctm-stage0/bin/run_part.sh cloudK /tmp/ctm-stage0/one_combat-46153506 \
  /home/user/sts_ai /mnt/project-files/ctm-stage0/part-cloudK > /tmp/ctm-stage0/run_part.log 2>&1 &
```

Wait for the `DONE` marker, check the background job's exit status, and reply with the DONE contents. If a worker fails, read `part-cloudK/*.log` and report it. Do not change seeds or flags.

## Local part commands (Philipp's machine, 10 workers)

The local session cannot see `/mnt/project-files`, so the three scripts are reproduced verbatim below (their sha256 values are in `bin/SHA256SUMS`). Use a fresh linked worktree through the lifecycle tool. Do not re-validate unrelated corpora.

```bash
cd <main checkout of pherrman1/sts_ai>           # not a linked worktree
git fetch origin main
python tools/agent/worktree.py create --detach --start-point 46153506cf183adcf422a0877310caa7747c1782 ../sts-ctm-stage0
cd ../sts-ctm-stage0 && python tools/agent/worktree.py check .   # repair . if submodules are off
cmake --preset linux-gcc-release && cmake --build build/linux-gcc-release --target one_combat -j10
mkdir -p build/ctm-stage0/bin build/ctm-stage0/part-local
cp build/linux-gcc-release/one_combat build/ctm-stage0/bin/one_combat-46153506
# write make_teacher.py, run_worker.sh, run_part.sh from the blocks below into build/ctm-stage0/bin/
(cd build/ctm-stage0 && sha256sum -c - <<'SUMS'
6b66c02287082de11e6c06df1b196058efe24a953b46f68a1e8bf213e622ada9  bin/make_teacher.py
f4e429adbedf3bbe2915f109a67046ec33d5874b983c431a70e9041b826a8004  bin/run_worker.sh
65dade2b83e7d51d4cf1ba8855ebe39b89084aba4807985a7dfcf90dac08e51c  bin/run_part.sh
SUMS
)
setsid nohup bash build/ctm-stage0/bin/run_part.sh local "$PWD/build/ctm-stage0/bin/one_combat-46153506" \
  "$PWD" "$PWD/build/ctm-stage0/part-local" > build/ctm-stage0/run_part.log 2>&1 < /dev/null &
```

It runs detached and logs under `build/`. Once `build/ctm-stage0/part-local/DONE` exists, return `tar czf ctm-stage0-part-local.tgz -C build/ctm-stage0 part-local` (about 150 KB of JSONL per seed and arm, so roughly 15 MB) as a thread attachment. The analysis thread unpacks it into `/mnt/project-files/ctm-stage0/part-local/`.

### bin/make_teacher.py

```python
#!/usr/bin/env python3
"""Freeze a #418 Stage 0 combattransitiongen teacher for one built binary.

usage: python3 make_teacher.py ARM BINARY REPO_ROOT OUT.json
ARM is exact10k or learned. git_sha is fixed to the frozen Stage 0 SHA;
executable_sha256 is the given binary (each machine freezes its own build).
"""
import hashlib, json, sys
from pathlib import Path

FROZEN_SHA = "46153506cf183adcf422a0877310caa7747c1782"
arm, binary, repo, out = sys.argv[1:5]
if arm not in ("exact10k", "learned"):
    sys.exit("ARM must be exact10k or learned")
sha = lambda p: hashlib.sha256(Path(p).read_bytes()).hexdigest()
search = {
    "simulation_budgets": [10000], "exploration_parameter": 25.0,
    "exploration_parameter_chance": 25.0, "chance_widening_c": 3.7028,
    "chance_widening_alpha": 0.52389, "end_turn_widening_c": 3.7028,
    "end_turn_widening_alpha": 0.52389, "reuse_cap_mode": "allocated",
    "reuse_cap": 32768, "sequential_halving": False, "pruning": False,
    "learned_visit_puct": False, "direct_learned_leaf": False, "adaptive": False,
    "particles": "not_applicable_silver_private_chance_search",
    "belief": "not_applicable_silver_private_chance_search",
}
env = {"STS_FAIR": "1", "STS_SEARCHER3": "0", "STS_SILVER_SEARCH": "1",
       "STS_SILVER_EXACT_ROOT_BUDGETS": "1", "STS_SILVER_REUSE_CAP_MODE": "allocated",
       "STS_SILVER_ADAPTIVE": "0", "STS_SILVER_VNET_LEAF_DIRECT": "0",
       "STS_EXECUTABLE_GIT_SHA": FROZEN_SHA}
if arm == "learned":
    search.update(budget_policy="learned_stop", learned_stop_model="gbt-770201c31f7b",
                  learned_stop_threshold=0.0323)
    env.update(STS_SILVER_EXACT_ROOT_BUDGETS="0", STS_SILVER_LEARNED_STOP="1")
models = [("ooc_floor_value", "models/v_rich_trees.txt"), ("ooc_win_value", "models/v_win_trees.txt")]
teacher = {
    "teacher_id": f"silver-ordinary-fair-{'learnedstop' if arm == 'learned' else 'exact10k'}-ctm-stage0-{FROZEN_SHA[:8]}",
    "git_sha": FROZEN_SHA, "executable_sha256": sha(binary),
    "combat_backend": "native_silver", "rng_regime": "project_fair",
    "search_configuration": search, "environment": env,
    "model_artifacts": [{"role": r, "path": p, "sha256": sha(Path(repo) / p)} for r, p in models],
}
Path(out).write_text(json.dumps(teacher, indent=2) + "\n")
print(out)
```

### bin/run_worker.sh

```bash
#!/usr/bin/env bash
# #418 Stage 0 worker: both teacher arms on one disjoint seed chunk.
# usage: run_worker.sh BINARY REPO_ROOT OUT_DIR WORKER_NAME SEED_LO N_SEEDS
# BINARY must be an executable copy (not on noexec /mnt/project-files).
set -euo pipefail
bin=$1 repo=$2 out=$3 name=$4 lo=$5 n=$6
frozen=46153506cf183adcf422a0877310caa7747c1782
here=$(cd "$(dirname "$0")" && pwd)
mkdir -p "$out"
cd "$repo"
[ "$(git rev-parse HEAD)" = "$frozen" ] || { echo "repo not at $frozen" >&2; exit 1; }
for arm in exact10k learned; do
  tag="$name-$arm"
  [ -f "$out/$tag.done" ] && continue
  python3 "$here/make_teacher.py" "$arm" "$bin" "$repo" "$out/$tag.teacher.json" >/dev/null
  # Clean STS_* environment, then exactly the frozen teacher environment.
  envargs=(-i PATH="$PATH" HOME="$HOME" OMP_NUM_THREADS=1)
  while IFS='=' read -r k v; do envargs+=("$k=$v"); done < <(
    python3 -c 'import json,sys;[print(f"{k}={v}") for k,v in json.load(open(sys.argv[1]))["environment"].items()]' "$out/$tag.teacher.json")
  env "${envargs[@]}" bash "$repo/tools/seed_guard.sh" "$bin" combattransitiongen "$n" 10000 0 \
      "$out/$tag.jsonl" "$lo" "$out/$tag.teacher.json" > "$out/$tag.log" 2>&1
  touch "$out/$tag.done"
done
```

### bin/run_part.sh

```bash
#!/usr/bin/env bash
# #418 Stage 0 part launcher. usage: run_part.sh PART BINARY REPO_ROOT OUT_DIR
# PART: local | cloud1..cloud5. Starts one worker per chunk, waits, writes DONE.
set -euo pipefail
part=$1 bin=$2 repo=$3 out=$4
here=$(cd "$(dirname "$0")" && pwd)
# name:first_seed:count  (disjoint, union = 50000000..50000127)
case "$part" in
  local)  chunks="w0:50000000:5 w1:50000005:5 w2:50000010:5 w3:50000015:4 w4:50000019:4 w5:50000023:4 w6:50000027:4 w7:50000031:4 w8:50000035:4 w9:50000039:4" ;;
  cloud1) chunks="w0:50000043:5 w1:50000048:4 w2:50000052:4 w3:50000056:4" ;;
  cloud2) chunks="w0:50000060:5 w1:50000065:4 w2:50000069:4 w3:50000073:4" ;;
  cloud3) chunks="w0:50000077:5 w1:50000082:4 w2:50000086:4 w3:50000090:4" ;;
  cloud4) chunks="w0:50000094:5 w1:50000099:4 w2:50000103:4 w3:50000107:4" ;;
  cloud5) chunks="w0:50000111:5 w1:50000116:4 w2:50000120:4 w3:50000124:4" ;;
  *) echo "unknown part $part" >&2; exit 2 ;;
esac
mkdir -p "$out"
[ -f "$out/DONE" ] && { echo "already DONE"; exit 0; }
sha256sum "$bin" > "$out/binary.sha256"
pids=()
for c in $chunks; do
  IFS=: read -r name lo n <<<"$c"
  bash "$here/run_worker.sh" "$bin" "$repo" "$out" "$part-$name" "$lo" "$n" > "$out/$part-$name.worker.log" 2>&1 &
  pids+=($!)
done
fail=0
for p in "${pids[@]}"; do wait "$p" || fail=1; done
[ $fail -eq 0 ] || { echo "a worker failed; see *.worker.log and *.log; rerun this command to resume" >&2; exit 1; }
{ echo "part=$part finished=$(date -u +%FT%TZ)"
  grep -h "combattransitiongen teacher=" "$out"/*-exact10k.log "$out"/*-learned.log | sed 's/ -> .*//'
  (cd "$out" && sha256sum *.jsonl *.jsonl.manifest.json)
} > "$out/DONE"
cat "$out/DONE"
```

