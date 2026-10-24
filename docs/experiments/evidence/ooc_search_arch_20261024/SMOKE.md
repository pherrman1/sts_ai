# Pre-launch checks (2026-10-24, cloud container, code febd4814, local release build)

Seeds used: smokes 111309990, 111309991; root replay 111309995 (all from the reserved 111309990–999).

## Unit tests
`ctest -R ooc_particle_planner` (toy models): 29 checks pass (replay, CRN gap = true gap, P = 1 = particle 0's
published streams, beam(1,1) = particle choice, non-anticipativity with hidden rewards, pruning/abort, horizon).

## Default and `mcts` mode reproduce main
Seed 111309991, arm-A config (`/home/user/flagoff`, not kept): main `413e85d6` binary vs this binary without the new
variables vs this binary with `STS_OOC_MCTS_SEARCH_MODE=mcts` + `STS_OOC_MCTS_SEARCH_TRACE`. All 371 game-record rows
are identical (timing, paths and hashes stripped) and the CTM row files match. The only difference is the header's
recorded search specification (`environment.STS_OOC_MCTS_SEARCH_MODE = mcts`). Outcome: died at floor 56 (act 4).

## One game per arm (seed 111309990, campaign `run_unit.sh` with ARMS_OVERRIDE, 4 games sharing 4 CPUs)
| arm | rc | wall | result | searched roots | planning CPU / root |
|---|---|---|---|---|---|
| A mcts | 0 | 769 s | Heart killed (floor 56) | 111 | ~0.6–24 s (learned stop) |
| B particle | 0 | 136 s | died act 3 (floor 51) | 99 | ~1 s |
| C particle_beam | 0 | 663 s | died act 3 (floor 51) | 102 | ~9 s |
Banners show the arm's planner (`search_mode=particle particles=64 horizon_combats=3`,
`search_mode=particle_beam particles=64 beam=8:2:3 horizon_combats=3`, none for A), the same leaf
(`leaf_heart1_value=…sr_crn_r2_s2_ep20.bin leaf_heart1_value_weight=0.100000 leaf_calibration=-2.5384,…`), the same
CTM (fine-tune table `8c226f23…`) and student_sel. (One smoke-only artifact: running three arms of one unit in parallel
let B's final `gzip` compress A's and C's open files; those two were rerun in their own directories. The campaign runs
the arms of a unit in sequence.)

## Root replay (seed 111309995, A plays, B and C plus checks on fresh models at every searched root)
`roots.py` on the trace (`root_replay_111309995.json`; trace on the share `ooc-search-arch/smoke/`): 53 searched roots
(24 card rewards, 12 maps, 6 rest, 5 events, 4 shops, 1 boss relic, 1 card select).
- Every check passes at all 53 roots: identical candidate sets for all planners; two hidden-future resamples of the
  root differ in hidden state but give identical candidates and prior (53/53); P = 1 equals the manual single
  continuation exactly (max |diff| 0); beam(1,1) keeps B's pick (53/53); B's root stage on a fresh model equals C's
  (53/53, replay).
- **CRN is real:** median correlation of the top two actions' particle values 0.90. B's top-vs-runner-up gap has
  paired z > 2 at 43% of roots (median z 1.4).
- **Disagreement:** B ≠ A at 21/53 roots, C ≠ A 22/53, C ≠ B 17/53. A picked the prior argmax at all 53 roots;
  B and C never look at the prior at the root. Disagreement is concentrated in rewards (9/24), maps (4–5/12),
  rest sites (4–5/6) and shops (3–4/4).
- CPU per root: A 8.0 s (this game had many full-budget roots), B 1.8 s, C 10.1 s.

Examples (prior; A visits/Q; B mean ± se; C final):
- Floor 6 rest, 75/75 HP: A upgrades Perfected Strike (prior 1.0, 4079 visits, Q 0.124); B and C upgrade Battle Trance
  (B 0.139 vs 0.135; A's own Q for Battle Trance was 0.142 on 4 visits).
- Floor 14 card reward: A takes Uppercut (prior 1.0); B/C take Flame Barrier (B 0.140 vs 0.131, prior 0.20).
- Floor 15 rest at 49/75: A upgrades Uppercut (prior 0.96); B/C upgrade Inflame (B 0.132 vs 0.113).
- Floor 18 card reward: A and C skip; B takes Thunderclap by 0.001 (a noise-level gap: 0.207 vs 0.206).
- Floor 17 act-2 map: A and B go to (0,0) (prior 1.0, B 0.193 vs 0.155); C prefers (5,0) on its plan score
  (0.188 vs 0.182) although its root stage agrees with A.
Judgement: B and C make plausible, value-driven distinctions (upgrades of scaling cards, Flame Barrier over Uppercut
at low HP); some B picks are inside the noise (gaps ~0.001 against se ~0.014), which is expected without a prior.
