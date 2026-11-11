# Gumbel only in hard fights, whole-run gate: GHARD against §775's G16 + mb4 (pre-registration)

**Authorization.** Philipp, 2026-11-10 16:04 CET in the roadmap thread ("Yes let's try 1."), on the proposal to
search with the Gumbel teacher only in elites, bosses and Act 4 and with the A20 default combat elsewhere. The gate
reuses §775's seeds (no new seeds). The worker count is Philipp's (default proposal: 40, his cap); the coordinator
starts the workers after the independent prelaunch review, queued behind Test 3 (#1028).

## Question

§782 traced where §775's G16 + mb4 gains its +9.6 pp Heart kills over the A20 default combat D: Act 1-2 elites, the
Act 2 boss, Shield and Spear and the Heart; deaths in normal fights changed by less than 0.3 pp per fight (all
intervals include 0). Normal and event fights hold about 44% of the fight turns (§782 `battles.csv.gz`: G16 42.1%
normal, 2.4% event). Does G16 + mb4 in elite and boss rooms only, with D in every other fight, keep G16's Heart kill
rate at less CPU? A cost test: the hoped result is "not worse at lower cost".

## The flag (code commit, default off)

`STS_SILVER_GUMBEL_ROOT_ROOMS=<list>` limits the whole-run Gumbel root (with its max backup and tree constants) to
fights whose room is in the comma list of `normal`, `elite`, `boss`, `event`; a fight in any other room searches
exactly as without `STS_SILVER_GUMBEL_ROOT` (here: D's learned stop, Act 4 strong). `STS_SILVER_GUMBEL_ROOT_SIMS=N`
gives the Gumbel fights their own flat budget (Act 4 strong's fights: the larger of N and their own budget, as
before with the agent's count). Unset = every room at the agent's simulation count, the old behaviour. Act 4's
Shield and Spear is an elite room and the Heart a boss room, so both stay Gumbel. Event fights (Colosseum, Dead
Adventurer, Mind Bloom, ...) are `event` rooms and play D here.

## Arms (`run_unit.sh`)

Both arms: §775's environment (`gumbel_wholerun_20261108/run_unit.sh`): net-0420 (sha 8c0bd16c) as the whole
out-of-combat policy (temperature 0, no OOC MCTS), learned Silver stop model gbt-0cac7cc64364, g7f_E root and tree
prior, boss-only prior playouts, Act 4 strong.

| arm | combat | command | games |
|---|---|---|---|
| G16 | Gumbel root k 16 + max backup (min 4 visits) at a flat 16,000 in every fight; Act 4 at max(16k, Act 4 strong's budget): Shield and Spear 16k, Heart 40k | `bestbench 16000 1 20 SEED` | §775 (code 5665d5ae, binary 0eabb014); 32 sentinel seeds rerun here |
| GHARD | as G16 in elite and boss rooms (`STS_SILVER_GUMBEL_ROOT_ROOMS=elite,boss STS_SILVER_GUMBEL_ROOT_SIMS=16000`); D (learned stop, 10,000 checkpoints) in normal and event fights | `bestbench 10000 1 20 SEED` | this campaign |

So GHARD's elite and boss fights get the same search as G16's (Shield and Spear 16k, Heart 40k), and its other fights
the same as D's.

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order; smokes on 111379280-111379289 (§775's
smoke block, used; not analysed). `units.txt`: first the 32 sentinel units `SEED G16` for 111378256-111378287 (lines
1-32), then 1,024 units `SEED GHARD`. One game per unit.

## Sentinel and control reuse (§742)

The 32 sentinel games replay §775's G16 games with this binary (new flags unset). A game's fingerprint: rc, abort
flag, the whole .log except the BEST line's timing fields, and the .err lines `[heart1_ppo] seed=` and `[silver]
whole-run Gumbel roots= sims=`. **32 of 32 identical = REUSE_VALID**: §775's 1,024 G16 games (and its D games for the
secondary) are the controls. Anything else = REUSE_INVALID: no verdict (CONTROL_INVALID); a G16 rerun on all seeds
(about 146 lane-hours) needs Philipp's go.

## Primary (`analyze.py`, frozen with this file; a copy of §783's with only the arm, its env keys and simulation count changed)

d = Heart kill GHARD − G16 per seed. A seed counts if both games finished rc 0 with all log checks and an env matching
the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more than 20 = INCOMPLETE.
Universe: seeds whose GHARD unit was claimed (unit directory or claims snapshot).

Gate `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0), alpha 0.05, beta 0.05, look 64, cap = analysed seeds
(≤ 1,024), seeds gap-free in ascending order. NOT_WORSE = **NOT_WORSE**; WORSE = **WORSE**. At CAP the one-sided 95%
seed bootstrap bounds of mean d decide (10,000 resamples, seed 20261110): **NOT_WORSE_3PP** if the lower bound
> −3 pp, **WORSE** if the upper bound < 0, else **INCONCLUSIVE**. The 95% CI is always reported.

**Cost (co-primary, reported with 95% seed bootstrap CIs):** CPU seconds per run and Gumbel simulations per run,
GHARD / G16, also corrected for machine speed by the sentinel (this campaign's G16 CPU over §775's on the 32 sentinel
seeds).

**Expectation (inference, written before any campaign game).** CPU: if per-turn cost scales with the budget, about
0.56 × 512 + 0.44 × 252 ≈ 400 CPU s per run, about **0.75-0.8× G16** (≈ 1.6× D); the learned stop's §783 saving was
0.76×. Heart: §782's G16 saved 5.2 HP per run in normal fights; at D's −0.24 to −0.51 pp per entry HP at bosses that is
worth roughly 1 pp, so a small loss (≤ 1-2 pp) is plausible and not resolvable at this size.

**Power (inference).** Paired games share the seed until the first different pick, which here is the first normal
fight (act 1 floor 1-3): GHARD diverges from G16 early in almost every seed, so discordance will be higher than
§783's (208 of 1,024). The SPRT will probably reach CAP and the fixed-sample rule with its 3 pp margin decides. A true
loss of 1 pp is not resolvable.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

The primary's sprt_gate gainer (+2 pp); GHARD − D (§775's games) with 95% CI; per arm Heart kill, act-4 reach (final
floor ≥ 52), mean floor, CPU sec per run, games over 1 h.

## Decision

No default change on this result. NOT_WORSE or NOT_WORSE_3PP with a CPU ratio below 0.9: GHARD becomes the cheaper
teacher configuration (AZ data generation, PPO actor combat), and combining it with a stricter learned stop is the next
question for Philipp. WORSE: normal fights matter more than §782's death counts show (HP carried into hard fights),
GHARD is dropped. INCONCLUSIVE: report, Philipp decides.

## Cost and schedule

About 0.78 × 146 ≈ 115 lane-hours plus 5 for the sentinel; 40 workers × 4 lanes, queue schedule, about 1 h. Share:
about 1,100 new files (tars, claims), about 50 MB.

## Smoke (local, this binary)

See `results/smoke.txt`: the flags unset replay §775's G16 game; GHARD with all four rooms listed (at bestbench
10000 with `STS_SILVER_GUMBEL_ROOT_SIMS=16000`) plays the same game as G16; GHARD runs a smoke seed with its banner
and Gumbel roots only in elite and boss fights.
