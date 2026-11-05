# LONG_B critic as a Silver combat leaf: teacher check (B2 rerun), pre-registration

Philipp, 2026-11-05 15:54 CET: "können wir auf dem fast fertigen value head schauen, ob er geeignet ist um leafs für
den silver combat zu sein?" §747 (`../heart1_value_leaf_teacher_20261102/`) ran the B2 teacher check on heart1's
value head (FAIL on T1 and T5) and said to rerun it on the own A20 PPO critic. This is that rerun on LONG_B.

Offline only: no seeds, no game runs, no GPU, nothing on the PC. The LONG_B run (paused at update 208) is not touched:
its net and trajectory refs are read with `git fetch` only.

## Candidate

- Net: LONG_B `net-0208` (208 updates; ref `ppo-xfer/longb/LONG_B/net-0208`), sha256
  `8c2d7daf27367ab057c28a527fc6d6b65480ed7c95c9d7cadd7d6fe5260ea410`. Its value head is trained on 1{Heart kill}
  (Monte-Carlo warm-up, then PPO with λ 0.97; `../ppo_long_b_20261104/PREREG.md`), so V is roughly P(Heart).
- Scorer: `one_combat heart1score`, built (linux-gcc-release-x86-64-v3) from this branch (base `23738b84`).
  **Parity check before the gates:** `net-0207` on the base records must reproduce the actors' logged `value`
  (behaviour net of iteration 208 is net-0207, of 209 net-0208) to max abs diff ≤ 1e-4.

## Why a new state set

§747's states (§691 key-rules-ab records, §721 Heart entries) predate the v2 inputs (`obs.v2.run_counters`,
`obs.v2.fought`, `offer_prices`, #941/#946) that LONG_B's net reads. Scoring them would test the net off its input
distribution. **Primary set:** the post-fight states in the LONG_B trajectory parts still in the store when this
check started (iterations 208 and 209: 78 parts, 1,040 games, played by net-0207/0208 on combat B). Per game and
floor, the first REWARDS-screen decision; room from the map node at (mapX, mapY): MONSTER → NORMAL, ELITE → ELITE,
mapY 15 → BOSS; events, treasure and shops dropped (§747 kept event fights; there they did not change the verdict).
`build_states_traj.py` → acts 1-3: 18,054 states (11,500 hallway, 5,195 elite, 1,359 boss); plus 311 Act-4 elite
states (descriptive). net-0208 trained on iterations 0-207 only, so these games are
unseen by it but drawn from its own play distribution.

Perturbations and HP equivalents are §747's (`prices.py`, unchanged).

## Gates (unchanged from §747; fixed before any score is read)

| # | Gate | Pass if |
| --- | --- | --- |
| T1 | −3 HP lowers V | in ≥ 95% of states |
| T2 | max HP +5, HP fixed | V rises in ≥ 90% of states |
| T3 | Fairy (removed) | median ≥ 30 HP-eq |
| T4 | per-type potion prices (types with n ≥ 30 here and n ≥ 100 in §510) | Pearson r ≥ 0.5 with §510's `altFloor` HP-eq |
| T5 | 1-HP resolution | median over states of abs(ΔV(1 HP)/secant − 1) ≤ 1/3 |

`gates.py` of §747, unchanged (sigmoid primary, raw repeated). On the primary set (acts 1-3).

**Decision rule (as §747):** all five pass → propose B3 (a default-off Silver leaf flag that uses shrunk, clipped
critic prices at fight end, then a fight-level gate; any seeds and workers need Philipp's go). Any gate fails → no
LONG_B leaf; the negative result goes to the ledger.

**Descriptive, no gate:** heart1 on the same states (paired comparison with §747's numbers); per room and act;
Act-4 elites; AUC of base V vs the game's Heart kill per act.

## Mid-combat states (by construction, no score)

The heart1-format record (`recordToJson`, `apps/one_combat/heart1_policy.cpp`) carries run-level fields only: HP, max
HP, gold, deck, relics, potions, map, counters, screen. It has no monster HP, intents, powers, hand, energy or turn.
Inside a fight the critic therefore cannot tell a nearly won fight from a nearly lost one, and it was never trained on
BATTLE screens (PPO decides only out of combat). Silver does not need a mid-combat value: every playout runs to the end
of the fight (`rolloutToEnd`) and the leaf scores the terminal `BattleContext` (`evaluateEndState`). The only leaf
role the critic can play is pricing that end state, which is what T1-T5 test.
