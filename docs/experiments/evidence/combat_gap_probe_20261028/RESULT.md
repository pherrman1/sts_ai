# Combat gap vs Baalorlord: diagnosis and paired probes (exploratory, §TBD)

Follow-up to §711 (`../expert_fight_replay_20261028`). Philipp, 2026-10-28 19:37Z: "start an investigation thread on
why we are worse than baalorlord combatwise, that thread should also propose on how to fix it, maybe we need some
small experiments". Exploratory: the probes were not pre-registered and ran in one 4-core cloud container. Seeds:
only the external Baalorlord run seeds of §694/§711. No new 111xxxxxx block.

## 1. Offline reading of the §711 records (no runs)

Scripts `pot.py`, `turns.py`, `cards.py` on §711's 329 `*.fights.json` (share `expert-fight-replay/units`). Outputs
are in `results/offline_*.txt`. Bot = per copy, expert = his logged floor. Everything here is descriptive and
conditions on post-treatment variables.

- **Potions at entry.** On act-2 elites the bot enters with no potion in 31% of copies (472/1,500). There the gap is
  **+9.6 HP** (bot 16.5 vs expert 6.9; expert drank 0.53). With at least one potion held it is **+4.0**. Act-1
  elites: +5.5 with none held vs +0.9 with one; act-1 boss +5.8 vs +0.7. The bot reaches those fights without potions
  because of its own earlier drinking (§711: it holds 1.25 vs 1.65 at acts-1-2 elite/boss entry and drinks 0.89 vs
  0.47 in act-1 bosses).
- **Equal potion use** (copies where the bot drinks as many potions as he did): act-1 elites +0.7 to +1.3, act-1
  bosses −0.1 to +2.7, act-2 elites **+4.2 to +5.1** (Book of Stabbing, Gremlin Leader, Slavers). So act 2 keeps a
  tactical gap even at the same potion count.
- **Turns.** The bot's winning copies take 0.7-2.6 turns fewer than his logged count on every encounter, a
  near-constant offset. That is consistent with a counting difference in the log, not with a slower bot. Nothing is
  read into it.
- **Cards.** The within-room gap against approximate deck contents (card rewards and shop buys before the floor),
  for 72 Ironclad cards: no card's CI excludes 0 by much. The largest positive is Dual Wield +3.6 [−1.3, +8.9]. The
  only CIs that exclude 0 are negative (Limit Break −2.8, Spot Weakness −1.7, Bloodletting −1.7), and with 72 tests
  that is expected by chance. The gap is not one misplayed card.
- **Search time.** Act-1/2 elite copies use 0.3-1.5 CPU-s (learned stop). Act-2 bosses use 19-33 s and Awakened One
  84 s.

## 2. Paired probe design

The research flag `STS_EXPERT_FIGHTS_ARMS` (code commits `69571e5`, `8cd9712`; default off) adds arms to
`one_combat expertfights`. In the target rooms (`STS_EXPERT_FIGHTS_ARM_ROOMS`), copies 0..K−1 are played under
production and under each arm, on the same copy seeds (battle streams and agent RNG). The fight state is identical
(deck, relics, HP and the bot's own potions), so the difference is paired. Every other copy is played only until the
first win. The main line continues from the first winning production copy, as in §711, so it is unchanged.

- Arms: `pp` (prior playouts in elite rooms, thread override of `STS_SILVER_PRIOR_PLAYOUT_ELITE`), `flat<N>` (flat N
  simulations at every root, no learned stop) and `potw<W>` (held-potion leaf weight W instead of 11).
- **Check.** With arms off, runs 1675881103 and 1663440811 reproduce §711's fights, replicates and end floor
  bit-exactly (cpu excepted). With arms on, the main line of 1675881103 is the same as §711 at all 13 fights.
- Environment: §711's `run_unit.sh` (A20 default, learned stop, g7f_E root table and prior, boss-only prior
  playouts), copied as `run_probe.sh` plus the arm variables. `queue.sh` runs 4 in parallel. Run lists: `pilot64.txt`
  (64 of the 175 runs with act-2 elites, shuffle seed 889) and `boss32.txt` (32 of 128 with an act-2 boss, seed
  890). Binaries: `69571e5` for the elite pilot and the boss check (sha256 `eba19d94…`), `8cd9712` for the potion
  check (`f790b204…`). The `STS_EXECUTABLE_GIT_SHA` field in the `.env` files records the repo HEAD at launch, not
  the binary. Raw files: `results/*_fights.tar.gz`. CIs: 95%, run-clustered bootstrap (4,000 resamples), `arms.py`.

## 3. Results (arm − production, HP lost per fight; lower is better)

**A. Act-2 elites, 64 runs, 131 fights × 4 copies** (`results/pilot_act2_elites.txt`). Production 11.72 vs expert
6.77 in this sample.

| arm | Δ HP | potions/fight | CPU/copy |
|---|---|---|---|
| flat 10k | −0.02 [−0.52, +0.48] | 0.43 (prod 0.43) | 3.1 s (prod 1.3 s) |
| flat 100k | +0.13 [−0.52, +0.79] | 0.44 | 33.4 s |
| elite prior playouts | −0.72 [−1.53, +0.06] | 0.37 | 6.4 s |

By encounter, prior playouts help Gremlin Leader −2.1 [−3.5, −0.8] and do nothing on Slavers (+0.4) or Book of
Stabbing (−0.7, CI spans 0).

**B. Act-2 bosses, 32 runs, 32 fights × 2 copies, flat 40k** (`results/boss_act2_flat40k.txt`). Production 14.14 vs
expert 11.91. **−3.25 [−6.81, +0.27]**, deaths 0.141 → 0.094, CPU 27 → 202 s per copy (7.4×). Automaton −1.5,
Champ −4.3, Collector −4.6 (n 9-13, all CIs span 0).

**C. Potion leaf weight, the 64 pilot runs, act-1 bosses (64 fights) + act-2 elites (131), 4 copies**
(`results/potion_weight.txt`). Production weight 11.

| | arm | Δ HP | potions/fight (prod) | HP per potion |
|---|---|---|---|---|
| act-2 elites | weight 5 | −0.58 [−1.14, −0.02] | 0.64 (0.43) | ≈ 2.8 saved per extra potion |
| act-2 elites | weight 22 | +1.40 [+0.70, +2.20] | 0.29 (0.43) | ≈ 10 lost per potion kept |
| act-1 bosses | weight 5 | −0.29 [−1.22, +0.61] | 1.10 (0.93) | ≈ 1.7 |
| act-1 bosses | weight 22 | +0.52 [−0.45, +1.50] | 0.80 (0.93) | ≈ 4 |

Within a fight, the potions production drinks are worth about their price (≈ 10 HP each against the leaf's 11).
The extra potions a cheaper price would add save only about 2-3 HP each. So in-fight potion timing is roughly
calibrated. Drinking like the expert would not close the gap. This probe does not measure how potions carry into
later fights: the main line stays production.

## 4. Diagnosis

1. **Elite fights are not budget-limited.** Ten and a hundred times today's simulations change nothing on act-2
   elites. More search converges to the same plays, so the act-2 elite gap (≈ +4 HP at equal potions) is a bias of
   the evaluation (leaf value and playout policy), not noise. Better playouts (the prior) move it a little, mostly
   in Gremlin Leader.
2. **Bosses are partly budget-limited.** Flat 40k cuts act-2 boss HP loss by about 3 HP (CI just includes 0) at 7×
   the CPU. That fits §706: the tree sees about one round, and long boss fights depend on deeper search or
   playouts.
3. **Potions.** In-fight potion timing is roughly calibrated (C). A third of act-2 elite entries have no potion left,
   and the gap there is twice the gap with potions. That is descriptive and may be selection (runs whose earlier
   fights went badly). The cross-fight allocation question stays open.
4. **Not one card, and not counting.** No card explains it, and the turn offset is constant.
5. **Open:** engine fidelity for Slavers / Book / Gremlin Leader (the Java parity canary is stopped).

## 5. Ranked fix proposals

1. **Boss budget (largest measured effect, cheapest to test).** Pre-register a paired probe of flat 40k (and the
   existing `STS_SILVER_LEARNED_STOP_BOSS_MAX=40000` extension, which only continues roots that did not stop) on all
   §711 act-1/2/3 boss states (≈ 500 fights). Decision rule: upper CI < 0 HP → whole-run A/B candidate; then a
   paired whole-run A20 A/B at matched CPU, per the AZ-loop rule. Cost ≈ 50-70 CPU-h at K=2 (flat 40k ≈ 200 s per act-2 boss copy): cloud workers, so it
   needs Philipp's go.
2. **Elite playout quality.** Budget is not the lever for elites, so the evaluation is. Candidates, in order of
   cost: (a) re-enable elite prior playouts (`STS_SILVER_PRIOR_PLAYOUT_ELITE=1`, ADR-0056 removed them ungated):
   −0.7 HP here, ≈ 5× elite CPU; gate it with a whole-run A/B. (b) A stronger rollout policy (a prior trained on
   searched elite fights) and a probe of that arm on the same states.
3. **Potion carry-over.** Measure it with arms that keep the main line in the arm (a second, non-paired probe mode),
   or at the OOC level. Not urgent: in-fight timing is calibrated.
4. **Engine fidelity** for Slavers / Book of Stabbing / Gremlin Leader: one canary pass on the live game, if
   Philipp resumes the canary.
5. **Stop:** more simulations for elites (no effect at 10× or 100×); a potion-weight change (in-fight calibrated).
