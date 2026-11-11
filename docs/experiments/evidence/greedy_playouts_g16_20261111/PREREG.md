# Greedy playouts in G16: §775's G16 + mb4 without prior playouts, whole-run gate against §775's G16 + mb4 (pre-registration)

**Authorization.** Philipp, 2026-11-11 22:59 CET in the cheap-combat roadmap thread ("jo lets go. was du gesagt
hast. aber lass auch schmale wurzel probieren, vllt reichen ja 92%. mach das nacheinander, je auf 40 workern. du
hast mein go für beides"), on the Track 0 plan of
[the cheap combat roadmap](../../../knowledge-base/research/combat-search/cheap-combat-roadmap.md). The gate reuses
§775's seeds (no new seeds). 40 workers; the coordinator starts them after the independent prelaunch review. The
narrow-root test (Track 1) is a separate campaign after this one.

## Question

The roadmap's step 0 ([evidence](../cheap_combat_step0_20261111/README.md)) found 86% of G16 + mb4's CPU in boss
rooms and Act 4, where a simulation costs 74-172 µs against 7-19 µs in hallway fights: those rooms play prior
playouts (ADR-0050 bosses, ADR-0060 Shield and Spear), which call the g7f_E MLP at every playout step. Their
evidence was fight-level at 10,000 simulations with the gen-6 prior (§541: bosses +12.55 score [−0.87, +26.57], 7.29×
CPU per fight); the whole-run effect was never gated. Does G16 + mb4 with greedy playouts in every room keep its
Heart kill rate at a fraction of the CPU?

## The flag (existing, no code change)

`STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0` (ADR-0050's "=0 restores"): greedy playouts in every room, Shield and Spear
included (`NativeSilverBackend.cpp`, ADR-0060's condition reads the same option). The startup banner of `one_combat`
still prints "Act 4 strong (S&S 10k prior playouts, Heart 40k)": that text is static (`apps/one_combat.cpp`,
`nativeSilverAct4Strong()` only), not a sign that prior playouts are on. The arm is identified by its `.env` and the
smoke's CPU drop.

## Arms (`run_unit.sh`)

Both arms: §775's environment (`gumbel_wholerun_20261108/run_unit.sh`, as T2's `run_unit.sh`): net-0420 (sha
8c0bd16c) as the whole out-of-combat policy (temperature 0, no OOC MCTS), learned Silver stop gbt-0cac7cc64364
(only gates Act 4 strong here), g7f_E root and tree prior (weight 400, K = 8), Act 4 strong, rollout root table g7f_E.

| arm | combat | games |
|---|---|---|
| G16 | Gumbel root k 16 + max backup (min 4 visits) at a flat 16,000 in every fight (Act 4 strong's budgets in Act 4), boss-only prior playouts + Shield and Spear | §775 (code 5665d5ae, binary 0eabb014); 32 sentinel seeds rerun here |
| GP16 | G16 with `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0` | this campaign |

Code commit 966de5f7 and binary 7f2800f0 are T2's (§788; its sentinel replayed §775's G16 games 32 of 32); main has
no build-input change since (checked `git diff 966de5f7 origin/main` over src, include, apps, CMakeLists, cmake,
models: empty).

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order. `units.txt`: first the 32 sentinel units
`SEED G16` for 111378256-111378287 (lines 1-32), then 1,024 units `SEED GP16`. One game per unit. `run_unit.sh`
refuses any seed outside 111378256-111379279. Smokes on §775's seeds 111378261, 111378263, 111378267, 111378268 (part
of the gated block: the campaign plays them again; the smoke games are not used).

## Sentinel and control reuse (ADR-0064)

The 32 sentinel games replay §775's G16 games with this binary. Fingerprint: rc, abort flag, the whole .log except
the BEST line's timing fields, and the .err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots= sims=`.
**32 of 32 identical = REUSE_VALID**: §775's 1,024 G16 games are the controls. Anything else = REUSE_INVALID: no
verdict (CONTROL_INVALID); a G16 rerun needs Philipp's go.

## Primary (`analyze.py`, frozen with this file; a copy of T2's with the arm, its env keys and §783's nonregression gate; `--self-test` passes)

d = Heart kill GP16 − G16 per seed. A seed counts if both games finished rc 0 with all log checks and an env matching
the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more than 20 = INCOMPLETE.
Universe: seeds whose GP16 unit was claimed (unit directory or claims snapshot).

Gate `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0), alpha 0.05, beta 0.05, look 64, cap = analysed seeds
(≤ 1,024), seeds gap-free in ascending order. H1 = **NOT_WORSE**; H0 = **WORSE**. At CAP the one-sided 95% seed
bootstrap bounds of mean d (10,000 resamples, seed 20261111) decide: **NOT_WORSE_3PP** if the lower bound > −3 pp,
**WORSE** if the upper bound < 0, else **INCONCLUSIVE**. The 95% CI is always reported.

**Cost (co-primary, with 95% seed bootstrap CIs):** CPU seconds per run, GP16 / G16, also corrected for machine speed
by the sentinel; Gumbel simulations per run (should be about equal: the budget does not change); CPU per run
quantiles (median, p90, p99, max) per arm, for the PPO loop's longest-game constraint.

**Expectation (inference, before any campaign game).** Cost: about 0.25-0.4× G16's CPU (step 0 estimate 130-200 s
per run; the first smoke game, seed 111378263, took 177 s against §775's 675 s and still killed the Heart). Effect:
prior playouts were worth a few HP per boss fight at 10k in §541; at 16k with the Gumbel root, unknown. A drop of
1-4 pp is plausible; a gain is possible (greedy playouts are less biased toward the prior's own line).

**Context for reading the control.** Four earlier whole-run arms against the same G16 games (§777, §780, §783,
§785) all came out 2.3-4.7 pp below it, and G16 on fresh seeds scored 41.6% (§783's data campaign); §775's G16
draw may be on the high side. This does not change the gate; it is reported with the result.

**Power (inference).** GP16 diverges from G16 at the first boss decision whose search changes, so most seeds that
reach a boss are discordant. With §775's 41% Heart rate, the SPRT resolves a true 0 (NOT_WORSE) and a true ≤ −3 pp
(WORSE); −1 to −2 pp will probably reach CAP.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

The primary's gainer SPRT (+2 pp); GP16 − D (§775's games) with 95% CI; per arm Heart kill, act-4 reach (final floor
≥ 52), mean floor, CPU sec per run, games over 1 h.

## Decision

No default change on this result.
- NOT_WORSE or NOT_WORSE_3PP at ≤ 0.5× CPU: GP16 is the cheap-combat candidate for the PPO actors (roadmap Track 0),
  and Act 4's budget (Track 2) is tuned on top of it.
- WORSE or INCONCLUSIVE: report; candidate follow-ups (Philipp's call) are GP16 with the saved CPU spent as boss and
  Act 4 budget, or prior playouts only at the Heart.
- The narrow-root campaign (Track 1) follows either way; its base arm is GP16 if GP16 is NOT_WORSE or NOT_WORSE_3PP,
  else G16.

## Cost and schedule

About 1,024 × 150-250 s + 32 × 600 s ≈ 50-80 lane-hours; 40 workers × 4 lanes, queue schedule, about 30-60 min plus
the slowest single game. Share: about 1,100 new files (tars, claims), about 40 MB.

## Smoke (local, this binary)

`results/smoke.txt`: GP16 on four of §775's Heart-kill seeds, CPU and outcome against §775's G16 games.
