# STS_SILVER_MAX_BACKUP=4 gate: whole A20 runs, net-0220 policy alone, flat Silver 1,000 (pre-registration, 2026-11-06)

**Authorization.** Philipp 2026-11-06: decision card "MAX_BACKUP=4 allein" (16:55 CET), setup "ohne learned
stopping", 1,000 sims, LONG_B eval setup (thread, 17:25 CET), typed go "Ja go mit 30 workern" (17:27 CET).

**Question.** Does `STS_SILVER_MAX_BACKUP=4` (ledger §624, §759: a Silver decision node's selection value is its best
child with at least 4 simulations; chance nodes keep the visit-weighted mean) raise the A20 Heart kill rate of whole
runs over Silver's default mean backup? Motivation: §759, where it ended all 16 known 420–500-turn stalemates of
LONG_B/LONG_C in 3–26 turns at equal or higher HP in 15/16. 16 hand-picked fights say nothing about win rate, and
§624's A20 A/B (max backup + block-first playout, OOC MCTS stack) was NOT_SHOWN.

**Setup.** LONG_B's evaluation runner (`../ppo_long_b_20261104/eval/run_unit.sh`) with one net: LONG_B's net-0220
(sha 408b2982…, the current PPO baseline, §756) as the whole out-of-combat policy, temperature 0, no OOC MCTS;
combat = Silver with an exact flat budget of 1,000 simulations per root, learned stop off, Act-4 strong off, g7f_E
root and tree prior (= combat B of LONG_B/LONG_C, where the stalemates occurred). `bestbench 1000 1 20 SEED`.
Engine: main c01bad53 (#997 merged: `one_combat` accepts `STS_SILVER_MAX_BACKUP`, strict parse, log line
`[silver] research search: max backup min visits=4`); every other default as on main, including the engine turn cap
500 (#996 default).

**Arms.** D = the default (mean backup). M = D + `STS_SILVER_MAX_BACKUP=4`. Both arms are played on every seed
(max backup changes every combat decision from turn 0, so no control reuse), in an order rotated by seed.
`run_unit.sh` checks per game: net and binary hashes, flat budget, root-prior banner, M's max-backup line, no
max-backup line in D and no research-leaf line in either.

**Seeds.** New block 111760000–111762047 (2,048 seeds, both arms); smokes 111769990–111769999. Checked unused in the
repository and project notes (2026-11-06).

**Primary.** d = Heart kill M − D per seed, seeds in ascending order, a seed counts if both games finished rc 0 with
all checks (a combat abort is a counted loss and listed); dropped seeds are listed, never imputed; more than 20
dropped = INCOMPLETE. SPRT per ADR-0064 (`tools/sprt_gate.py` at c01bad53, variant **gainer**: d0 = 0, d1 = +2 pp,
α = β = 0.05, look every 64 pairs, cap = analysed seeds ≤ 2,048). H1 → **GO**; H0 → **NOT_SHOWN**; CAP → 95% seed
bootstrap of mean d (10,000 resamples, seed 20261106): GO if lo > 0, STOP if mean ≤ 0, else INCONCLUSIVE. The mean d
and its CI are reported in every case. `analyze.py --self-test` covers drops, an abort and INCOMPLETE.

**Secondary reading (not a gate).** Same pairs through `sprt_gate.py --variant nonregression` (d0 = −1.5 pp) and
the bootstrap: NOT_WORSE if lo > −1.5 pp. Descriptive: Act-3 clears and final floor (M − D with CIs), cpu_sec/run per
arm and the M/D ratio (§624 measured ~+20% per simulation), combat aborts, games over 300 s wall, max wall per arm.

**Decision.** GO → max backup becomes a default candidate for combat B / the PPO loop (Philipp decides; own PR + ADR;
the learned stop, trained on mean-backup trees, would need its own check before any learned-stop configuration uses
it). NOT_SHOWN with NOT_WORSE → stays a research flag; Philipp may still choose it for its compute and stall effect.
Otherwise it stays off. Ledger entry either way.

**Cost.** 2 × 2,048 games at ~21–25 s (M ~+20%) ≈ 28 core-h; 30 workers × 4 lanes ≈ 15–20 min plus setup; the SPRT
is read after the full run (no early stop of the campaign).

**Smoke (author container, before launch).** 111769990–111769991, both arms rc 0 with all checks; see README.md.
