# Heart runtime recovery and tiny paired capture

**EXACT_RUNTIME_RECOVERED + NO_NEAR_INFINITY_STATE_OBSERVED.** The exact-source rebuild reproduced the required executable bytes. All three frozen public trajectories match through their target fights. The ingredient-bearing combats never compressed below 16, 30 and 19 active cards respectively. No candidate or kill was found in the frozen K=4 annotation; this does not prove absence.

Starting #844 SHA: `0772ffe7ca8c63bd941036fa3c8cbecf040c934a`. Same existing app-managed worktree and branch `research/infinity-public-root-pilot`; no branch switch, new worktree/thread, merge, AZ lead, fresh random cohort or model work.

## Runtime recovery and build

Expanded bounded search: the prior 70 named executables/61 hashes across retained primary/app-worktree build/bundle locations; 20 Heart-related build roots (candidate paths limited to five levels); the retained Heart transport tar; and Downloads/cloud-{1,2,3}-return.tar.gz. No exact executable found. The GitHub workflow-run query for the exact source commit returned zero runs, so there was no matching workflow artifact to retrieve. No sealed TEST/confirm/validation payloads or unrelated filesystem trees were crawled. `/root` cloud-worker custody was inaccessible and `/mnt/project-files` absent. Detailed paths/hashes/exclusions: [artifact-search.json](artifact-search.json).

Historical source: `d8fd2a105a8d2a481b7639e26c683f75e382e3d4`.
Required and rebuilt executable SHA256: `0e17e0f22259afe21f35ba89a0413f2af7663cfae1312311f1ea8c71b00c2d52`.

This is an exact reconstruction from source, not an archive-recovered original file or merely a hash-different behavioral candidate. The 772 tracked snapshot files remained unchanged and read-only. Pinned submodules: json `2222d386c905e6a6ebf73c61571a8a2cf196e843`, pybind11 `63d627c5747befad7720a43ebbe5614fd5d83247`. A Git archive under ignored build storage provided source without another checkout/worktree. No source patch, generated-source substitution or compatibility shim was needed.

Local toolchain: g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0; cmake version 4.4.2; OpenSSL 3.0.13 30 Jan 2024 (Library: OpenSSL 3.0.13 30 Jan 2024). Historical compiler version was not separately retained in inspected metadata; executable-byte identity is established directly. Historical cloud_worker.sh supplied `cmake --preset linux-gcc-release` then `cmake --build --preset linux-gcc-build --target one_combat --parallel 4`. Both exited 0. Release/C++20, -O3/-DNDEBUG, -fopenmp, -flto; PGO OFF, no added flags. Link emitted only the serial LTRANS warning. Actual flags/link command and dependency hashes are in [build-result.json](build-result.json); complete [configure](configure.log.gz)/[build](build.log) logs and [source manifest](source-build-plan.json) are retained.

Read-only custody copy: `build/infinity-heart-runtime-20261024/hash-identical-one_combat`; source build: `build/infinity-heart-runtime-20261024/source/build/linux-gcc-release/one_combat`. Both have the exact required hash. Runtime directories used symlinks to the preserved Heart model bundle; this task only read those files. All three attempts used these same frozen model bytes:

| Artifact | SHA256 |
|---|---|
| `studentc.bin` | `eff2f74f57dc2f566bbd44be30988592503cc8db51e51ff1e70cd2dec4636509` |
| `v_rich_trees.txt` | `3a3420469b1d648e0e306d6cb6a7e85f3d3499105e3ff3a56eee6c579194ffe3` |
| `v_win_x2b_public_trees.txt` | `e2d3aa65291df2914119f5d8129fb3aa6b7339ba6fa72eeaf9e86b9402beca90` |
| `ooc_strategic_tok_final.native` | `e62abd833fc8cb9081a1cec4a1a012832ac3b0e3166da3892841911664f1184c` |
| `combat_transition_deepsets_pathb_r2_lizard.native` | `c6d56bbc959f4d5de8fe1dd57f58a922112cd8323bcbac9711e0aecda93f5a3c` |
| `combat_transition_near_full_escape_pathb_r2.native` | `b9188de03ed6cc0611094c108f607a8770a5d5c5f367c157851bc6af91f8d9cf` |
| `combat_transition_deepsets_pathb_a20_lizard.native` | `ae785ec2e28ceb3755fb63a71534f873ed61a069a6c2e107ef4131a788af7b6b` |
| `combat_transition_near_full_escape_pathb_a20.native` | `e338506ddf14177bec27cfe174670bd9dcac333c26b30416b9f0c76717392b0d` |

## Frozen replay qualification

Original `heartoutcomegen 1 SEED STATES on` ran through the historical repository seed guard, OMP_NUM_THREADS=1, fixed simulations/settings from each original receipt. All STS_/OMP_ settings were inherited from that receipt after removing ambient overrides; only trace destinations and the existing paired public trace/target were added. Local HOME/PATH are host plumbing. Exact invocations, environment, model hashes, source archive and receipt bindings appear in each replay-*.json. No setting correction or retry was needed.

Before seed execution, [PROTOCOL.md](PROTOCOL.md) and [frozen-prefixes.json](frozen-prefixes.json) fixed all comparison prefixes. Full producer header, every public state object and every OOC trace object were compared recursively and exactly, including ordered deck/upgrades, relic IDs/counters, HP/max HP, gold, potions, keys, act/floor/room/screen, maps/path, offers and decisions wherever historically recorded. Historical misc values and engine RNG states were not recorded and cannot be invented. State checkpoints 0 and 65/134/52 were included, along with the full target fight and the following public state.

| Seed | Ingredient / target / post-fight state | Matched state objects | Matched trace objects | Runtime / fidelity | First divergence | Wall / CPU seconds |
|---|---|---:|---:|---|---|---:|
| 111101032 | 65 / 66 / 67 | 68 | 67 | HASH_IDENTICAL / CHECKPOINT_IDENTICAL | none | 125.564 / 120.331 |
| 111101326 | 134 / 135 / 136 | 137 | 136 | HASH_IDENTICAL / CHECKPOINT_IDENTICAL | none | 385.254 / 376.594 |
| 111101512 | 52 / 55 / 56 | 57 | 56 | HASH_IDENTICAL / CHECKPOINT_IDENTICAL | none | 65.458 / 64.770 |

Each owned process group was intentionally stopped only after its exact target-battle post trace and following state were flushed and verified. These are qualified prefixes, not claims of complete-run replays. The 1,800-second per-run wall limit was never reached. All source/checkpoint selection was independent of run outcomes. Paired combat capture was quarantined until each fidelity gate passed; no oracle result was read before qualification.

## Captures and root selection

| Seed / ingredients | Target fight | Captured / ordinary roots | Tier 1 / Tier 2 | Active range | Frozen selected decisions (active count) |
|---|---|---:|---:|---:|---|
| 111101032 / two Dropkicks + Bash + Pommel Strike | act 2 floor 18 fight 11 SHELL_PARASITE | 19 / 18 | 0 / 18 | 16–18 | 9 (16), 16 (16), 17 (16), 18 (16) |
| 111101326 / two Flash of Steel + Corruption + Dark Embrace | act 3 floor 37 fight 19 THREE_DARKLINGS | 18 / 17 | 0 / 17 | 30–33 | 8 (30), 11 (30), 12 (30), 18 (30) |
| 111101512 / Sundial + Pommel Strike + Shrug It Off | act 1 floor 14 fight 8 TWO_FUNGI_BEASTS | 8 / 8 | 0 / 8 | 19–20 | 1 (19), 2 (19), 3 (19), 4 (19) |

45 public records comprise 43 ordinary PLAYER_NORMAL roots and two card-selection decisions outside the adapter domain. The latter were retained and explicitly excluded, not labeled negative. All 43 ordinary roots meet the strong ingredient Tier 2 screen; none meets Tier 1. The 12 selected roots are the deterministic four per fight, ranked within the selection hierarchy by lower active count, stronger frozen ingredient class, then earlier decision. No weak Headbutt-only filler was added. Each selected input hash and full public card/relic summary was frozen in selection-SEED.json before its sole oracle invocation.

Complete relic inventories from the same executed OOC trace establish no Prismatic Shard in each target fight. Replay receipts bind the public/OOC/state files, binary, models and run/fight identities. No new capture schema or public_run_relics field was required. Only public wires plus the proven no-Shard assertion entered the adapter; run seed and observed-generation metadata were cleared. Sample seeds were independently revalidated as public-root-hash-derived, and sampled physical card multisets match the public piles. Historical hidden draw order/RNG were never supplied as teacher input.

## Unchanged K=4 annotation

Existing reviewed adapter source/CMake/executable unchanged; executable SHA256 `28e942c218cbaeef29f3a58a3301873d2fca012f6205379445e4e23ffef0ebe9`. Three seed-guarded commands, timeout 30s each, one invocation per frozen fight, no retries. Bounds unchanged: depth 24, nodes 2,000, candidates 16, replay periods 128, actions/candidate 1,024, replay actions total 4,096. All commands exited 0, stderr empty.

12 eligible roots /48 supported worlds. All48 classifications NONE; certified/candidate fractions 0.0 for each root, minimum reach depth and representative witness null. No damaging candidates, certified kills, witness replay actions or repetitions exist. Node caps: 1/48 (2.083%), at seed111101326 decision11; that world is inconclusive. No depth/candidate cap hit. Total nodes 10,846; maximum search depth 5. Oracle CPU total 31.710ms across48 worlds. Different sampled draw orders occur at 12/12 roots; classification disagreement at 0/12. Different diagnostics are visible in raw worlds, including the single capped sample.

Per-root classification, nodes/depth, CPU, fractions, caps and witness fields: [MATRIX.md](MATRIX.md), [expanded-sidecars.json](expanded-sidecars.json). All four sampled worlds for every selected root, sampled piles, candidates and raw oracle diagnostics are retained in oracle-SEED.jsonl. [witnesses.json](witnesses.json) is empty. Input/output hashes and timings are in the matching oracle receipts.

## Interpretation and stopping decision

**EXACT_RUNTIME_RECOVERED.** The historical-runtime blocker is resolved for these three Heart leads, and frozen-checkpoint replay fidelity passed through all three ingredient-bearing fights. No behaviorally approximate runtime claim is needed.

**NO_NEAR_INFINITY_STATE_OBSERVED (Case D, within the three predeclared fights).** Ingredients are present, but the smallest observed active pools are 16, 30 and 19, with no Tier-1 compression. The 31-card Flash of Steel deck even grows to33 active cards in this fight; possessing Corruption/Dark Embrace did not establish a functioning compressed draw engine. The Sundial deck retains at least19 active cards. A two-Dropkick deck is likewise not automatically a repeating combat state. These are ingredient observations, not demonstrated near-infinities.

NONE is not a proof of absence or a negative training label. One node-capped world remains inconclusive. These bounded historical fights do not estimate natural prevalence, demonstrate current-policy positive signal, or isolate an oracle recall limitation. No new positive exists to trace backward or independently replay. This task stops here; no AZ lead, later fight, collection extension, higher budget, model probe or training follows.

The next useful question is whether a tiny targeted OOC/counterfactual generation can produce actual compression and a playable engine from such ingredients. That is a proposed next experiment, not authorization to launch it. More oracle engineering is not supported by these observations.

## Revalidation and scope

`python3 analyze.py --check` revalidates retained compressed raw bytes against receipts, exact header/all-prefix states/traces, no-Shard same-run join, selected public wires, independent K=4 seeds/physical multisets/caps, output custody and byte-identical generated reports without executing seeds or sampling worlds. `freeze_roots.py SEED --check` also rebuilds each selection from the retained local run files. `replay.py` and `annotate.py` refuse to overwrite prior runs/batches. Raw focused command output is in verification.txt.

Changed production code: none. This change consists of research evidence scripts/artifacts plus the experiment ledger and maintained research status. Original four unsupported native8 roots and their null fractions, older A0 Champ pilot, constructed fixture verdicts, oracle normalization and all bounds remain unchanged. Broad tests and earlier gameplay fixtures were not rerun. Linux GCC CI remains authoritative before merge; the known account billing/spending-limit failure is not an implementation failure or a pass, and no manual redispatch was requested. New reconstruction evidence awaits independent PR review; prior reviews remain tied to their earlier SHAs.

Knowledge impact: current research status and chronological experimental evidence; no runtime/default/model promotion.
