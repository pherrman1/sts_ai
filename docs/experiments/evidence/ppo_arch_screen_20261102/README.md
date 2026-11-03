# PPO architecture screen, design B (prepared 2026-11-03, not launched)

Pre-registration: [PREREG.md](PREREG.md) ("Binding under B" governs). Arms: [arms.txt](arms.txt). Freeze:
[make_arms.sh](make_arms.sh). Learner check: [learner_check.py](learner_check.py). Analysis: [analyze.py](analyze.py).

Nothing here runs before screen 2 (`ppo_reward_screen_20261103`) is SERVE_DONE and Philipp has given his typed go
(seeds, worker count). The learner shares the one PC GPU with screen 2.

Launch order (author; `S2=~/ppo-screen2`, screen 2's serve directory, kept with `--keep-state 30`):
1. **P1 binary.** Build branch from `defaa930` (the commit behind binary `71cfd280…`) with only P1's C++ diff
   (`apps/one_combat/heart1_policy.{h,cpp}`, `apps/one_combat.cpp`, PR #978) applied; build `one_combat`
   (`linux-gcc-release-x86-64-v3`, as the bin cache); copy it to `/mnt/project-files/bin-cache/one_combat-<sha>`.
2. **Run commit.** Main (with #977, #978 and this PR) with the build inputs of the step-1 branch
   (`git checkout <build branch> -- apps src include extern cmake CMakeLists.txt CMakePresets.json json pybind11 models selfplay/models`),
   so `ppo_cloud_worker.sh setup` accepts it. `screen.manifest`: `code_commit` = the build-branch commit,
   `binary_sha256 71cfd280e121811f394ec8e6c285a1aca5368e100e2f6ae005d94442a6f922d1`,
   `binary_sha256:IN_DECK <P1 sha>`, `store git:https://github.com/pherrman1/sts_ai#ppo-xfer/arch`, plus the fork
   point's sha256 (`$S2/BASE/state-0030.pt`, `net-0030.bin`, the four iteration-30 parts) and the cost numbers.
3. **Cost rule** (before launch): for each arm's start net (`$S2/ARM/net-0030.bin` after step 5, BASE =
   `$S2/BASE/net-0030.bin`), `one_combat heart1logitscheck` on `ppo_s0_smoke_20261101/cov8.jsonl.gz`, 3 runs, one
   thread, same container; ms/record into the manifest.
4. **Learner check** (PC GPU): `python3 learner_check.py $S2 ~/arch-learner-check --micro-batch 192` must print
   `LEARNER_CHECK_OK` (the flags-off fork's net-0031 = BASE's, bit for bit). A FAIL stops the screen.
5. **Freeze:** `bash make_arms.sh git:https://github.com/pherrman1/sts_ai#ppo-xfer/arch $S2 71cfd280e121811f394ec8e6c285a1aca5368e100e2f6ae005d94442a6f922d1 <P1 sha>`
   (`DRY=1` first). Each arm's learner directory appears as `$S2/ARM`.
6. **Sentinel (IN_DECK):** the P1 binary replays 32 of BASE's iteration-30 seeds with `$S2/BASE/net-0029.bin`, as
   stored and with `ppo_model.py addinputs net-0029.bin x.bin x3_deck`; every trajectory line and outcome must equal
   BASE's kept iteration-30 parts. A failure holds IN_DECK only.
7. **Learner:** `python3 tools/heart1/ppo_cloud.py serve --micro-batch 192 git:https://github.com/pherrman1/sts_ai#ppo-xfer/arch $S2 $(awk '!/^#/{print $1}' arms.txt)`.
   Each arm first trains iteration 30 on the reused parts, then waits for its actors.
8. **Workers** W=1..20 (count with Philipp's go): `bash tools/heart1/ppo_cloud_worker.sh setup|start|wait docs/experiments/evidence/ppo_arch_screen_20261102 W`.
9. **Analysis:** copy `$S2/{IN_DECK,DEPTH6,CRITIC_SEP,AUX,VAL_SPARSE}` and screen 2's `$S2/{BASE,BASE_S1}`
   (games-*.csv, stalled_seeds.txt, loop.json), then `python3 analyze.py ARCH SCREEN2 result.json --critic CRIT`.
10. **Critic secondary:** rebuild the §747 states (`heart1_value_leaf_teacher_20261102/build_states.py`, check
    `meta.json` sha256 `03b0838c…`), then per arm in BASE, CRITIC_SEP, AUX, VAL_SPARSE:
    `python3 tools/heart1/ppo_train.py score $S2/ARM/state.pt records.jsonl CRIT/ARM/values.jsonl --device cuda` and
    `python3 docs/experiments/evidence/heart1_value_leaf_teacher_20261102/gates.py meta.json CRIT/ARM/values.jsonl docs/experiments/evidence/potion_price_probe_20261017/analysis.json CRIT/ARM/gates.json`.
    BASE's critic is screen 2's final BASE `state.pt`.
