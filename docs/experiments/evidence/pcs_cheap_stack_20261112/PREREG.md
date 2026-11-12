# Plan commitment on the cheap stack: H4 with §793's PCS rule (HPS) against §792's H4, whole runs (pre-registration)

**Authorization.** Philipp, 2026-11-12 17:29 CET in the cheap-combat roadmap thread: "okay lets try", in answer to the
proposal to combine PCS with H4 on GP16 (the cheapest stack). The campaign reuses §775's seeds, so no new seeds are
needed. Worker count: "go 40" (17:35 CET). The coordinator starts the 40 workers after the independent prelaunch review.

## Question

§793 showed that A4P keeps its Heart rate when it plays the inherited plan edge at chance-free continuation roots
whenever that edge holds at least 90% of the inherited visits (PCS): −0.20 pp [−2.83, +2.54] at 0.81× CPU.
§792's H4 (E0's GP16 with 4,000 simulations in Act 1-3 hallway fights) is the cheapest stack so far: 36.13% Heart
kills at 116.8 s per run. Does H4 keep its Heart rate with the same rule (HPS), and how much CPU does it save?

The two cuts overlap: H4 already cut the hallway simulations, and committed roots are often cheap ones. The saving on
H4 can therefore be smaller than the 19% on A4P (inference).

## The flag (exists on main, default off)

`STS_SILVER_PLAN_COMMIT=0.9` (#1038, §793; documented in `environment-variables.md`). No code change: code commit
3c85fb26 and binary ca8d9d0b (sha ca8d9d0bdf6f690de19d0e6e6e4b693a3b90f58ca46a9cd82ad53e6a2335b689, preset
linux-gcc-release-x86-64-v3) are §793's, and origin/main 18b67085 has the same build inputs.

## Arms (`run_unit.sh`)

All arms use §792's H4 environment:
- §775's G16 + mb4 with `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0` (E0's GP16) and
  `STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY=4000`;
- net-0420 (sha 8c0bd16c) as the whole out-of-combat policy at temperature 0;
- learned Silver stop gbt-0cac7cc64364, the g7f_E root and tree prior (weight 400, K = 8), Act 4 strong, and
  rollout root table g7f_E;
- Gumbel root k 16 + max backup with 16,000 simulations per root, 4,000 in Act 1-3 hallway fights.

| arm | combat | games |
|---|---|---|
| H4 | as §792 (flag unset) | §792 (code 4c4e42eb, binary e60e2614); 32 sentinel seeds are rerun here |
| HPS | H4 + `STS_SILVER_PLAN_COMMIT=0.9` | this campaign |

`run_unit.sh` checks the banners:
- exit 79 if any arm prints a "prior playouts only in acts" line;
- exit 76 or 75 if HPS lacks its plan-commit banner or its exit counters;
- exit 77 if H4 prints any "plan commit" line.

The hallway banner `k=16 max backup=4 (all acts, hallway sims 4000)` is required in both arms (rc 87).

## Seeds and units

§775's seeds 111378256-111379279 (1,024 seeds, already used; these are replays) run in ascending order. `units.txt`
lists:
- lines 1-32: the sentinel units `SEED H4` for 111378256-111378287;
- then `SEED HPS` for each seed (1,056 units in all).

`run_unit.sh` refuses any seed outside the block. The smoke ran on seeds 111378263 and 111378259, both in the block;
the smoke games are not used.

## Sentinel and control reuse (ADR-0064)

The 32 sentinel H4 games replay §792's H4 games on the same seeds with this binary (flag unset). The fingerprint is
the same as in §790-§793:
- rc and the abort flag;
- the whole .log except the BEST line's timing fields;
- the .err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots= sims=`.

**32 of 32 identical = REUSE_VALID**, and §792's 1,024 H4 games are the controls. Anything else is REUSE_INVALID and
gives no verdict (CONTROL_INVALID).

## Primary (`analyze.py`, frozen with this file; `--self-test` passes)

`analyze.py` is a copy of §793's with the arms, the sentinel arm (H4) and one gated arm.
- **The contrast.** d = Heart kill of HPS − Heart kill of H4, per seed.
- **Which seeds count.** A seed counts if both games finished with rc 0, passed all log checks and had an env matching
  the arm. A combat abort is a counted loss.
- **Drops.** Dropped seeds are listed, never imputed; more than 20 makes the arm INCOMPLETE.
- **Universe.** The seeds whose HPS unit was claimed (a unit directory or the claims snapshot).
- **Test settings.** Alpha 0.05 (one gated arm), beta 0.05, look 64, cap = analysed seeds (at most 1,024), with the
  seeds taken gap-free in ascending order.
- **Bounds.** The one-sided 95% seed bootstrap bounds of mean d use 10,000 resamples with seed 20261111. The 95% CI is
  always reported.

The gate is `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0): H1 is **NOT_WORSE**, H0 is **WORSE**. At CAP:
- **NOT_WORSE_3PP** if the lower bound > −3 pp;
- **WORSE** if the upper bound < 0;
- else **INCONCLUSIVE**.

**Cost (co-primary, with 95% seed bootstrap CIs):**
- CPU seconds per run, HPS / H4, also corrected for machine speed by the sentinel;
- Gumbel simulations and searched roots per run;
- plan-eligible roots and commits per run;
- CPU per run quantiles (median, p90, p99, max).

**Expectation (inference, before any campaign game).**
- **Cost.** 0.80-0.90× H4's CPU, about 95-105 s per run.
- **Effect.** 0 to −1 pp, as PCS on A4P.

**Power (inference).** As in §790-§793: a true 0 resolves NOT_WORSE, and a true −3 pp or worse resolves WORSE.

**Stopping.** Every seed runs; "crossed at" is reported. A single game still running more than 1 h after every
other unit is done is dropped (listed; Philipp, 2026-11-12 17:06 CET, "just drop it").

## Secondary (not gates)

- The gainer SPRT;
- HPS − A4P (§792) and HPS − GP16 (§790, E0's tree, `gp16_contrast.py`), same contrast code;
- Heart kill, Act-4 reach (final floor ≥ 52), Act-4 conversion, mean floor, losses by final floor, games over 1 h.

## Decision

No default change on this result.
- **NOT_WORSE / NOT_WORSE_3PP.** HPS becomes the cheap-combat candidate at its CPU. The next step is a cheap addition
  that buys Heart kills: Act-4 prior playouts at the Heart only, or Act 1-3 boss prior playouts at a lower budget,
  paid by the savings.
- **WORSE or INCONCLUSIVE.** Report. H4 stays the candidate; plan commitment stays an A4P-only result.

## Cost and schedule

About 1,024 × 95-120 s + 32 × 117 s ≈ 28-36 lane-hours. On 40 workers × 4 lanes on a queue schedule that is about
15-20 min plus the slowest single game. The share takes about 1,100 tars and 1,056 claim directories (about 3,200 files,
about 40 MB); the inode count is checked before launch.

## Smoke (local, this binary)

`results/smoke.txt`:
- H4 with the flag unset against §792's campaign game on 111378263 (identity);
- HPS on 111378263 and 111378259 (cost and outcome).
