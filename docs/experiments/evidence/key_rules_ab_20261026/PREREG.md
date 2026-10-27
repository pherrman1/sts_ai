# Key rules A/B at A20: rigid ADR-0041 key rules vs flexible keys, student_sel alone (pre-registration)

Written 2026-10-26 before any campaign game ran. Origin: experiment 1 of the 2026-10-26 deep-research report
("find what caused the jump from 17.6% to ~24%"). Design doc: https://claude.ai/artifact/3qD8tZKFLEeWUtvZQe3jPM.

**Authorization:** Philipp, 2026-10-26 22:16Z: "okay lets go on 16 workers". 1,024 paired A20 seeds x 2 arms on 16
cloud workers, launched by the coordinator after an independent pre-launch review passes this RUN_COMMIT.

## Question
§566 (rigid keys, OOC MCTS, 2026-10-19) killed the Heart in 17.6% of A20 runs; §569 (one day later, flexible keys plus
other changes) killed it in 25.8% with search and 23.4% with student_sel alone. Main still defaults to the rigid
ADR-0041 key rules (`src/sim/search/RunGoal.cpp`), while every campaign since §569 sets the flexible flags. The key
rules were never A/B tested (the PR #611 Stage-1 key A/B was dropped on 2026-10-17). Every other §569 change is now a
default. How many Heart kills do the flexible key rules add, on today's stack?

## Arms (`run_unit.sh` is the source of truth)
Only the three key flags differ.
- **R (rigid):** no `STS_KEY_*` set = ADR-0041: Sapphire at the first chest offering it, Ruby Recall at the first
  Act-3 campfire, first legal edge reaching the burning elite on the Act-3 map.
- **F (flexible):** `STS_KEY_SAPPHIRE=policy STS_KEY_RUBY=policy STS_KEY_EMERALD=mask`, as in §569 and every campaign
  since. Backstops stay: Sapphire by the Act-3 treasure row, Recall by the pre-boss campfire, Act-3 Emerald mask.

Both arms are the §683 OFF arm on today's main: `heartoutcomegen` with `STS_OOC_MCTS_SCREENS=none` (no OOC root is
searched; the rule chain, then student_sel `cf6bf7fb…` decides), real combats with the learned Silver stop and exact
root budgets, Act 4 strong (ADR-0060, unset = on), g7f_E root table + prior, boss-only prior playouts, default CTM
(§679), Wing Boots counter on, engine fixes explicit. Banner checks per arm: student_sel loaded, `screens=none`, and the
key-rule line (`heart_key_rules sapphire=2 ruby=2 ruby_min_hp=0.600 emerald=1` in F, absent in R).

Deviation from the design doc: the doc said `bestbench`; `heartoutcomegen` with `SCREENS=none` plays the same
student_sel-alone policy, writes state/decision rows (for the key-timing and first-divergence readouts), and reuses the
§683 harness and analyzer.

## Seeds and scale
- Campaign: **111382000–111383023** (1,024 seeds), smokes **111383024–111383027**; assigned by the coordinator from the
  free block 111381000–111389989; no repo record uses them. One unit = one seed, R and F in sequence (order rotated by
  seed % 2) on one lane.
- Cost (`SMOKE.md`): ~300–450 s per game under Act 4 strong (a Heart run 1,300–1,550 s), ~170–260 core-hours,
  ~3–4 h on 16 workers x 4 lanes plus a Heart-run tail. (The design doc's ~120 core-hours predates the smoke.) Peak memory: one Heart search ~2.3 GB RSS; 4 lanes fit in 15 GB.

## Endpoints
- **Primary:** Heart kills, F − R, paired: exact discordance counts (exact McNemar p) and a 95% seed-bootstrap CI of
  the paired difference.
- **Secondary:** Act-4 arrival F − R; kills per Act-4 arrival; mean final floor; deaths by act; wall per arm.
- **Key timing (descriptive, per arm):** floor and act where each key is first held; HP fraction at Ruby Recall;
  relics held at the start of Act 2.
- **Mechanism:** first-divergence attribution (act, screen, deciders), with Heart and Act-4 deltas per class.

## Decision rule (frozen)
- **KEYS_EXPLAIN:** F − R Heart kills ≥ +4.0 pp and the 95% CI above 0. The key rules carry most of the §566 → §569
  jump; the follow-up is a separate PR proposing flexible keys as the A20 default (Philipp's call; "=first restores"),
  and checking the live advisor's key flags.
- **KEYS_MINOR:** the 95% CI upper bound < +3.0 pp. The jump came mostly from the combat stack, fixes and parity work.
- **PARTIAL:** anything else. Report the point estimate and CI; no default change from this run.

## Known limitations
- The A/B measures key rules under student_sel alone on today's stack; it does not replay §566's code, so the rest of
  the jump stays an unpaired remainder. With OOC MCTS on, the search would also choose key timing; not tested here.
- 1,024 pairs resolve about ±3 pp on Heart kills (paired, 22–30% discordance).
- Key rules first act at the Act-1 chest, so most pairs diverge after it; the first-divergence readout is descriptive.
