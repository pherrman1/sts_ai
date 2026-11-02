# PPO cost arms and start-net check G0 (pre-registration, 2026-11-01)

Philipp, 2026-11-01 22:12Z (card "Wo soll der Rezept-Screen laufen?": "PC + Cloud für Kosten-Arme"), 22:11Z
"du kriegst dann actually 40 worker", 22:17Z "masch einfach alles go, ich approve den ganzen run". Plan:
[a20-ppo-plan.md](../../../knowledge-base/research/a20-ppo-plan.md), sections "Cost per game and training recipe" and G0.

**Questions.**
1. Cost arms: which cheaper Silver settings for PPO self-play keep an out-of-combat policy effect intact?
2. G0: does heart1 (silverbot's released PPO net) alone play A20 at least as well as student_sel alone in our engine
   at Silver 1,000? This picks the start weights of the PPO net.

**Runner.** X1's (§739, `cheap_combat_proxy_20261031/run_unit.sh`): `bestbench 1000 1 20 SEED`, binary
`d39c2b9895fc6070` (main `6c96c25`, the binary of X1's six arms), `STS_OOC_MCTS=0`, the OOC net alone after the key
rules. Base combat B = X1's flat Silver 1,000 (learned stop off, Act 4 strong off, g7f_E root and tree prior, boss prior
playouts). Every flag in `run_unit.sh`; key flags explicit in every arm.

**Cost arms** (vs B): K1 `STS_SIMS_NORMAL=200` (hallway and event fights 200 sims, elites and bosses 1,000); K4 no
boss prior playouts; K5 no learned Silver prior at all (no root/tree prior, rollout root table off, no prior playouts;
the original's Silver); K15 = K1 + K5.
Dropped before launch (amendment after review K and the smoke, no campaign game played): the plan's K2/K3 (learned
stop "at 1,000"). This binary's learned stop searches its fixed checkpoints up to 10k whatever the base budget, so it
is no cheaper than B: smoke seed 111386992, 335 s vs 42 s per game. K6 (fork-resume cost) is not a combat setting and
is measured inside the PPO loop instead.
Per arm the §691 key contrast: R (`STS_KEY_*=first`) vs F (`policy/policy/mask`) with student_sel `cf6bf7fb`, on X1's
1,024 seeds 111382000-111383023 (USED, replays). Each unit also replays FB (= X1's F1000) as a same-container cost
reference and a determinism check against X1's F1000 games.

**G0.** F keys, base combat B, student_sel (GS) vs heart1 (GH, `heart1.bin` `1e92f2a6`, exported from silverbot
`heart1.pt` `deaba59d` with `tools/heart1/export_heart1_weights.py`, as §486), paired on 2,048 new seeds
111372000-111374047 (reserved and unused per §661's entry; seed guard checked).

Smokes: 111386992 (K layout) and 111386993 (G0 layout), local, before launch; not analysed.

**Primary metrics and decisions** (`analyze.py`, 95% seed bootstrap, 10,000 resamples; a seed counts for an arm only
if both of its games finished rc 0; missing games reported, not imputed):
- Cost arm K: D_K = Heart kill F − R. As X1: **VALID** if CI lower bound > 0 and D_K in [0.5 P, 1.5 P] with
  P = §691's +6.05 pp, i.e. [+3.03, +9.08]; INVALID if CI upper bound < +3.03; else INCONCLUSIVE.
  Cost_K = Σ(cpu F_K + cpu R_K) / (2 Σ cpu FB) over the seeds with all three games, CPU seconds from the `BEST` line, same container. **Admitted** = VALID.
  PPO self-play uses the admitted arm with the lowest Cost_K; if none is admitted, B (X1: VALID).
- G0: D = Heart kill GH − GS. **HEART1** (start from heart1's weights) unless the CI upper bound < 0, then
  **STUDENT_SEL** (distil student_sel into the d256 net first). Secondary: Act-3 clears, mean floor.

**Secondary (descriptive).** Per arm Heart and Act-3 rates; DiD (F_K − R_K) − (F1000 − R1000) vs X1's games.csv on
the same seeds; FB vs X1's F1000 per seed (identical outcomes expected; differences reported).

**Cost.** K units: 9 games × ~15-20 s ≈ 2.5 min per seed → ~45 core-h; G0: 2 × ~20 s per seed → ~23 core-h.
24 workers × 4 lanes (`campaign.manifest`), ~1 h. Seeds new: 111372000-111374047 (G0), smokes 111386992-993.
