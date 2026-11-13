# G12 / Heart 24k: §775's G16 + mb4 at 12,000 simulations with the Heart at 24,000, whole-run gate against §775's G16 + mb4 (pre-registration)

**Authorization.** Philipp, 2026-11-13 22:02 CET: "Können wir mal 12k überall probieren außer heart mit 24k? 40 worker
go", after the budget curve 1k-16k (§778, §779, §781). The gate reuses §775's seeds (no new seeds). 40 workers; the
coordinator starts them after the independent prelaunch review.

## Question

The budget curve with Act 4 strong rises from 34.4% Heart at 8,000 simulations (G8S, §781) to 40.4% at 16,000 (G16 +
mb4, §775) on the curve's 512 seeds, and is flat above 16,000. Does 12,000 simulations in every fight, with the Heart
at 24,000 instead of Act 4 strong's 40,000, keep G16 + mb4's Heart kill rate at less CPU?

## The option (new, research, default unchanged)

`STS_SILVER_ACT4_HEART_BUDGET=N` (code commits bf8b4cfa and ba705ab4, `NativeSilverBackend.cpp`, `one_combat`'s list of accepted Silver options): the Heart's flat budget under Act 4
strong; unset = 40,000 (`kAct4HeartBudget`), so default play does not change. In a whole-run Gumbel fight the Heart
searches max(N, the Gumbel budget). The option prints `[silver] research act4 heart budget N`, and the startup banner
names the Heart budget ("Act 4 strong (S&S 10k prior playouts, Heart 24k)"; unchanged "Heart 40k" text without the
option). The A20 real-learned-stop path and `wholecombatgen` refuse any other value than 40,000.

## Arms (`run_unit.sh`)

Both arms: §775's environment (`gumbel_wholerun_20261108/run_unit.sh`, as `greedy_playouts_g16_20261111/run_unit.sh`):
net-0420 (sha 8c0bd16c) as the whole out-of-combat policy (temperature 0, no OOC MCTS), learned Silver stop
gbt-0cac7cc64364 (only gates Act 4 strong here), g7f_E root and tree prior (weight 400, K = 8), Act 4 strong, rollout
root table g7f_E, boss-only prior playouts (ADR-0050) plus Shield and Spear (ADR-0060).

| arm | combat | games |
|---|---|---|
| G16 | Gumbel root k 16 + max backup (min 4 visits) at a flat 16,000 in every fight of acts 1-3 and at Shield and Spear (max(10,000, 16,000)), the Heart at 40,000 with the 262,144-node reuse cap | §775 (binary 0eabb014); 32 sentinel seeds rerun here |
| G12H24 | the same root at a flat 12,000 (`bestbench 12000`), Shield and Spear at max(10,000, 12,000) = 12,000, the Heart at max(24,000, 12,000) = 24,000 (`STS_SILVER_ACT4_HEART_BUDGET=24000`) with the same reuse cap | this campaign |

`run_unit.sh` checks each arm's log lines: the sims line, the Gumbel banner, the Act-4 banner with the arm's Heart
budget, and for G12H24 the option line (for G16 its absence), besides the checks of the greedy-playout gate.

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order. `units.txt`: first the 32 sentinel units
`SEED G16` for 111378256-111378287 (lines 1-32), then 1,024 units `SEED G12H24`. One game per unit. `run_unit.sh`
refuses any seed outside 111378256-111379279. All 1,024 seeds rather than the curve's 512: the primary is against
G16, which exists on all 1,024 (±2.7 pp instead of ±3.9 pp at 95%); the curve's 512 are reported separately.

## Sentinel and control reuse (ADR-0064)

The 32 sentinel games replay §775's G16 games with this binary. Fingerprint: rc, abort flag, the whole .log except
the BEST line's timing fields, and the .err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots= sims=`.
**32 of 32 identical = REUSE_VALID**: §775's 1,024 G16 games are the controls. Anything else = REUSE_INVALID: no
verdict (CONTROL_INVALID); a G16 rerun needs Philipp's go.

## Primary (`analyze.py`, frozen with this file; a copy of the greedy-playout gate's with the arm, its sims, the env key `STS_SILVER_ACT4_HEART_BUDGET` and two descriptive blocks; `--self-test` passes)

d = Heart kill G12H24 − G16 per seed. A seed counts if both games finished rc 0 with all log checks and an env
matching the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more than 20 =
INCOMPLETE. Universe: seeds whose G12H24 unit was claimed (unit directory or claims snapshot).

Gate `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0), alpha 0.05, beta 0.05, look 64, cap = analysed seeds
(≤ 1,024), seeds gap-free in ascending order. H1 = **NOT_WORSE**; H0 = **WORSE**. At CAP the one-sided 95% seed
bootstrap bounds of mean d (10,000 resamples, seed 20261113) decide: **NOT_WORSE_3PP** if the lower bound > −3 pp,
**WORSE** if the upper bound < 0, else **INCONCLUSIVE**. The 95% CI is always reported.

**Cost (co-primary, with 95% seed bootstrap CIs):** CPU seconds per run, G12H24 / G16, also corrected for machine
speed by the sentinel; Gumbel simulations per run; CPU per run quantiles (median, p90, p99, max) per arm.

**Expectation (inference, before any campaign game).** Cost: about 0.75-0.8× G16's CPU (between G8S's 315 s and
G16's 509 s per run, less about 15-25 s for the cheaper Heart). Effect: the curve's 8k → 16k step was +6.05 pp, nearly
all of it Act-4 reach (acts 1-3); a smooth curve puts 12k about 2-3 pp below 16k in acts 1-3. The Heart at 24k instead
of 40k: unknown; kills per Heart arrival were 80-83% for every Act-4-strong arm from 1k to 64k, with Shield and Spear at
10k-64k and the Heart at 40k-64k. A drop of 1-4 pp is plausible.

**Context for reading the control.** The four whole-run arms against the same G16 games in §777, §780, §783 and §785
all came out 2.3-4.7 pp below it; §785 could not tell whether the cap's 32,768 default is an optimum or G16's draw on
these seeds is favourable (G16 on fresh seeds 41.6%, §775's G32 40.8% on these seeds). This does not change the gate;
it is reported with the result.

**Power (inference).** The arms differ from the first root, so nearly every seed is an independent pair of runs
(§785: about 200 discordant seeds). The SPRT resolves a true 0 (NOT_WORSE) and a true ≤ −3 pp (WORSE); −1 to −2 pp
will probably reach CAP.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

The primary's gainer SPRT (+2 pp); G12H24 − D (§775's games) with 95% CI; per arm Heart kill, act-4 reach (final
floor ≥ 52), mean floor, CPU sec per run, games over 1 h; Act-4 conversion: Heart kills per Act-4 arrival per arm, and
on the seeds where both arms reached Act 4 the paired difference with its 95% CI (the Heart budget's share, together
with Shield and Spear at 12k); the primary contrast and per-arm rates on the budget curve's 512 seeds
111378256-111378767, next to §781's G8S (34.38%) and §775's G16 (40.43%) there.

## Decision

No default change on this result.
- NOT_WORSE or NOT_WORSE_3PP at ≤ 0.85× G16's CPU: G12H24 is a cheaper teacher or actor candidate (Philipp's call).
- WORSE or INCONCLUSIVE: report, with the Act-4 conversion split; follow-ups (for example 12k with the Heart at
  40k, or 16k with the Heart at 24k) are Philipp's call.

## Cost and schedule

About 1,024 × 380-420 s + 32 × 520 s ≈ 110-125 lane-hours; 40 workers × 4 lanes, queue schedule, about 50-70 min
plus the slowest single game. Share: about 2,100 new files (tars, claims), about 60 MB.

## Smoke (local, this binary)

`results/smoke.txt`: G12H24 on two of §775's seeds and one sentinel G16 game against §775's.
