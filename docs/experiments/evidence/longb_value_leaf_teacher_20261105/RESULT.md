# LONG_B critic as a Silver combat leaf: teacher check (B2 rerun) result

Pre-registration: [README.md](README.md) (commit `6e8a78c6`, pushed before any score was read). Offline only: no
seeds, no game runs, no GPU, nothing on the PC. One 4-core cloud container, 2026-11-05 ~15:00-17:45 CET. The LONG_B
run (paused at update 208) was only read: its net and trajectory refs with `git fetch`.

## Provenance

| item | value |
| --- | --- |
| net | LONG_B `net-0208`, sha256 `8c2d7daf27367ab057c28a527fc6d6b65480ed7c95c9d7cadd7d6fe5260ea410` |
| control (descriptive) | heart1 `/mnt/project-files/a20-ppo/heart1.bin`, sha256 `1e92f2a6…` |
| scorer | `one_combat heart1score`, linux-gcc-release-x86-64-v3 from `23738b84`; binary sha256 `78849fcf768f6e84…`, identical to LONG_B's post-pause actor binary |
| parity | net-0207 on the iteration-208 base records (behaviour net-0207) and net-0208 on the iteration-209 base records (behaviour net-0208) reproduce the actors' logged `value` exactly: max abs diff 0.0 on 8,977 and 9,388 states |
| states | 78 trajectory parts (`traj-0208-p*`, `traj-0209-p*`), 1,040 games; `build_states_traj.py` → 18,365 states, 237,814 records; `meta.json` sha256 `0e5934cf…` |
| scores | `/mnt/project-files/longb-value-leaf-teacher/` (`meta.json.gz`, `values_net0208.jsonl.gz` sha256 of uncompressed `b314714e…`, `values_heart1.jsonl.gz` `ff3bee7e…`) |
| gates | §747 `gates.py`, unchanged → `gates_net0208.json`, `gates_heart1.json`; `describe.py` → `describe_*.json` |

Primary set: 18,054 post-fight states in acts 1-3 (11,500 hallway, 5,195 elite, 1,359 boss). 16,473 of 17,707
states with a 12-HP secant have a positive secant.

## Gates (primary set, sigmoid as pre-registered; raw gives the same verdicts)

| # | gate | net-0208 | pass | heart1 on the same states | heart1 §747 |
| --- | --- | --- | --- | --- | --- |
| T1 | −3 HP lowers V in ≥ 95% | **79.2%** | **FAIL** | 86.2% | 82.7% |
| T2 | max HP +5 raises V in ≥ 90% | 96.0% | pass | 93.5% | 92.6% |
| T3 | Fairy ≥ 30 HP | 50.3 HP | pass | 30.5 | 35.0 |
| T4 | per-type r ≥ 0.5 with §510 | 0.776 | pass | 0.743 | 0.755 |
| T5 | median abs(1-HP price − 1) ≤ ⅓ | **1.57** | **FAIL** | 1.30 | 1.50 |

**Verdict: FAIL (T1, T5).** Per the decision rule there is no LONG_B leaf and no B3.

## Detail

- **HP resolution is again the failure, and it is worse than heart1's on the same states.** −1/−3/−6/−12/−24 HP
  lowers V in 67/79/89/93/95% of states (heart1: 69/86/94/97/98). The 1-HP price in secant units has median 1.13 but
  p10 −3.2, p90 +4.6. Per room T1 is 81% hallway, 79% elite, 64% boss; per act 84/74/75%. It is worst at bosses and
  late acts, where Silver's leaf decisions matter most.
- **The critic is a much better outcome predictor than heart1.** AUC of base V vs the game's Heart kill on these
  post-fight states: 0.77 (act 1 0.67, act 2 0.80, act 3 0.84; Act-4 elites 0.87) vs heart1's 0.56 (0.64/0.72/0.69).
  Mean V 0.28 vs realised Heart rate 0.30. Training on 1{Heart} taught levels; it did not teach 1-3 HP differences.
- **Prices it gets right:** Fairy 50 HP (§510: 44), max HP +2.5 HP per point (heart1 +1.5), non-Fairy potions median
  6.7 HP (p10 +1.1, p90 19.0; §510 7.8, formula 11), per-type order r 0.78.
- **Act-4 elites (descriptive, 311 states):** T1 77.8%, T2 72.7%, T5 1.43.

## Mid-combat states

Not scored, by construction (README): the heart1-format record has no combat fields (monster HP, intents, powers,
hand, energy, turn), and the critic never saw a BATTLE screen. Silver does not need a mid-combat value, since every
playout runs to the end of the fight and the leaf prices the terminal state. That end-state pricing is what failed.

## Reading

- Two PPO critics with different rewards (heart1: floor shaping; LONG_B: 1{Heart}) fail the same two gates. More
  PPO training improved the level (AUC 0.56 → 0.77) and the potion prices, while HP resolution got worse. This
  matches the literature page's (B): critics fit levels, not sibling differences.
- **Inference:** a usable leaf from a run critic would need a target that resolves small HP differences (e.g.
  paired/CRN continuations), not more PPO updates. The potion prices (Fairy ≈ 45-50 HP, per-type order) remain the
  one useful content, as after §747; a per-type potion term is untested in play.
