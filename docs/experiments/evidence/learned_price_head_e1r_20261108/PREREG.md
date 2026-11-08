# E1-R of the learned price head: potion prices from reward luck (pre-registration)

Written 2026-11-08 01:20 CET, before any E1-R row existed beyond a 4-seed smoke (seeds 111780000-111780003, checked
only for identity with E1's source rows and for roll consistency; no outcome was set against its rolls).
Design doc (German): https://claude.ai/artifact/PzKavVUBmYiitvHLFhg7qp.

## Question

Philipp, 2026-11-08 00:40 CET: follow the E1 luck approach for prices (the P1 gate was dropped). 00:46 CET: the gold
price matters for Silver only at Hand of Greed kills, so gold is left out. 00:58 CET, the go for this run: "Jo nutz
fürs Logging später 4 workers, wenn die anderen 4 workers dann sind, hast meine Erlaubnis".

Under E1's policy and games (net-0420 as the whole out-of-combat policy, combat B; §764), what is a reward potion
worth in pp of Heart kill, and how much more is a Fairy in a Bottle worth than any other potion? Silver's leaf values
every potion at 11 HP plus a Fairy death save of 0.3 max HP; the pilot's CRN prices (leaf stage 4, P1) say about
3.7 HP for a non-Fairy potion and much more for a Fairy; E1's fight luck priced potions only coarsely
(1.9 ± 0.8 / −0.9 ± 0.9 / 1.5 ± 1.1 pp in acts 1-3).

## Setup

- `one_combat fightendpairgen 16 FIRST 1000 20 OUT n=0,ooc=ppo,rewards=1 -` (`run_unit.sh`), code `cf9237a5`
  (binary `767a44b2…`), E1's environment and E1's 512 units of 16 seeds (111780000-111788191; no new seeds). No forks,
  no fight replays: these are E1's source runs again, with every combat reward's potion roll logged (KB
  `research/fight-end-pairs.md` point 6).
- 4 cloud workers × 4 lanes, queue. About 47 core-h (8,192 runs at E1's 20.6 s), about 3 h wall.
- Smoke (frozen code, binary `767a44b2…`, seeds 111780000-111780003): the source rows equal E1's (E1's G1 fields
  and Silver simulations), 60 rolls, 0 inconsistent. `run_unit.sh` end to end on unit 111780000 (16 seeds): rc 0 in
  4.2 min, 16 of 16 source rows equal E1's, 253 rolls (17 at act 1-2 bosses, 4 at act 4's elite), 0 inconsistent.
  The full self-test passes (rows unchanged by the log; every roll agrees with the engine).

## Gates

- **G1 same games:** the source rows equal E1's on every seed both have (E1's G1 fields and Silver simulations). A
  mismatch does not void the potion estimates (they need no E1 row) but voids the HP-unit conversion.
- **G2 rolls agree with the engine:** at most 0.1% of the rolls inconsistent, else VOID.
- **G3 completeness:** at least 98% of the units count (the queue retries a failed unit up to four attempts).

## Analysis (`analyze.py`; synthetic check `selftest_analyze.py`)

Per logged roll r: u_r = dropped − chance/100. Given a drop, the type is drawn independently of the drop chance, so
f_r = dropped × (Fairy − q) (q = the Fairy share of all drops) is a second, independent draw. Game-level OLS of
heartKill on the per-game sums by roll class (act 1-2 boss rewards; act 4's elite reward; mid-act rolls of acts 1, 2,
3) and of f_r, HC1 SEs. No ×2 factor: the chance is the exact expectation of the drop.

Why the classes: potionChance moves by +10 after a roll without a drop and by −10 after a drop, and resets to 0 at
every act transition. A drop at the boss reward (or at act 4's elite reward) changes no later drop chance, so its
coefficient is the value of the potion. A mid-act drop lowers the act's later chances (about −(1 − 0.8^K) later drops
for K later rolls in the act), so its coefficient is attenuated towards 0 and is descriptive only (synthetic check:
0.54 ± 0.37 pp against a true 3.0 for K >= 6). The Fairy contrast is clean at every roll.

**Primary:**
- V_boss: the value of a reward potion at the act 1-2 boss reward (pp per potion), pooled over both acts.
- C_Fairy: the value of a Fairy drop minus that of any other drop (pp), all rolls.

**Decision (a measurement, no default change):** USABLE if both 95% CIs exclude 0, PARTIAL if one does, UNRESOLVED
if neither. A price table built from luck prices needs its own gate against Silver's default (Philipp's go).

**Descriptive:** V_boss per act; act 4's elite reward (Shield and Spear, the potion goes into the Heart); the mid-act
coefficients per act and by later rolls in the act (0, 1-2, 3-5, 6+); free vs full slots at the boss and act-4
rewards; potion types with at least 500 drops (each against the rest); V_boss in HP at E1's 0.155 pp per HP; the
comparison with Silver's leaf, P1 and E1's fight luck.

Rough power before the run (counts only, from the 16-seed unit test below): about 1.1 boss rolls and 16 rolls (about
6 drops) per game, so SE(V_boss) about 0.9 pp and, with a Fairy in about 1% of the drops, SE(C_Fairy) about 1.8 pp.
V_boss may end unresolved at this size.

## Commands

```
python3 -I docs/experiments/evidence/learned_price_head_e1r_20261108/selftest_analyze.py 20000
python3 -I docs/experiments/evidence/learned_price_head_e1r_20261108/analyze.py SNAP/e1runits SNAP/e1units e1r_result.json
```

## Amendment (2026-11-08 01:33 CET, after the prelaunch review K, before any row of the run existed)

- **G3:** fewer than 502 of the 512 units count → decision INCOMPLETE; the estimates are then descriptive
  (`decision_ci` keeps the CI rule).
- **G1:** a source row that differs from E1's, or no seed to compare, voids only the HP conversion
  (`boss_hp_units` = null, with the reason); the potion estimates need no E1 row.
- **G2 in practice:** `run_unit.sh` fails a unit at its first inconsistent roll (rc 88). The queue retries it, the
  run is deterministic, so it fails again and is dropped. G2's 0.1% tolerance therefore never applies to the units
  that count, and a systematic inconsistency shows up as unit loss under G3. `analyze.py` lists such units as
  `G2_rc88_units`.
- **Descriptive additions:** V_boss split by Sozu (with Sozu a dropped potion cannot be taken, so those drops
  attenuate the pooled V_boss), and the implied value of a non-Fairy drop, V_boss − q × C_Fairy.
- **Correction of the synthetic check's label:** the boss coefficient is the value of an average drop, the Fairy
  share included: V + W × q, in the check 3.0 + 10 × 0.06 = 3.6 pp, not 3.0. The check's estimate 3.05 ± 0.52 is
  within 1.1 SE of that, and eight further seeds average 3.49 (sd 0.40). So V_boss is the value of a reward potion of
  random type, as defined above.
