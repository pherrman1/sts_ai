# Per-encounter budget, whole runs: fewer hallway simulations (H4) and prior playouts only in Act 4 (A4P) on GP16 (pre-registration)

**Authorization.** Philipp, 2026-11-11 23:43 CET in the cheap-combat roadmap thread ("Ja, für Bosse, elites,
eigentlich alle encounter. Dafür hast du mein go") and 23:48 CET ("Du darfst für das budget pro encounter später 40
worker nehmen"): the per-encounter simulation budget of the cheap combat roadmap
(`docs/knowledge-base/research/combat-search/cheap-combat-roadmap.md`), after E0 (§790) and E1 (§791). Reuses §775's
seeds (no new seeds). 40 workers; the coordinator starts them after the independent prelaunch review.

## Question

E0 (§790) took G16 + mb4's prior playouts out (GP16): 35.74% Heart kills against 41.21% at 0.27× the CPU (143 s per
run). E1 (§791) showed that halving every root's simulations costs 7-8 pp. Two cheap places remain where the budget
can be moved by encounter type instead of everywhere:

1. **Hallway fights** (Act 1-3 rooms other than elites and bosses) are about 80 s of GP16's 143 s (step 0's CPU map:
   7-19 µs per simulation but most of the roots). Does GP16 keep its Heart kill rate with 4,000 simulations per root
   in those fights (H4)?
2. **Prior playouts in Act 4 only.** Prior playouts were worth 5.5 pp at about 370 s per run; E0's losses grew most
   in Act 4 (Act-4 deaths 82 → 108 of 1,024) while Act 1-3 bosses, where most of the prior-playout CPU sits, gave
   up less. Does GP16 with prior playouts back only at Shield and Spear and the Heart (A4P) gain Heart kills, and at
   what CPU?

## The flags (new, default off, defaults unchanged)

Both in `NativeSilverBackend.cpp`, both listed in `one_combat`'s environment allowlist and in
`docs/knowledge-base/operations/environment-variables.md`:

- `STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY=N` (1-10,000,000; needs `STS_SILVER_GUMBEL_ROOT`): in a whole-run Gumbel
  search, every root in Act 1-3 whose room is neither an elite nor a boss gets N simulations instead of the flat
  budget (`STS_SILVER_GUMBEL_ROOT_SIMS`). Act 4 and elite and boss rooms are unchanged. Adds ", hallway sims N" to
  the banner.
- `STS_SILVER_PRIOR_PLAYOUT_ACTS=LIST` (comma list of distinct acts 1-4; needs
  `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE` on): prior playouts (ADR-0050's boss rooms, ADR-0060's Shield and Spear) only
  in the listed acts; greedy playouts elsewhere. The full list 1,2,3,4 equals unset. Prints
  `[silver] research search: prior playouts only in acts LIST`.

Code commit: this PR's commit (origin/main 46ca86f8 + the two flags), binary sha
e60e2614bb1cc15a3a9c6fc43cbe90c6146b173a6ab60b869d527b45691978c8 (preset linux-gcc-release-x86-64-v3).

## Arms (`run_unit.sh`)

All arms: §775's G16 environment as in E0 (net-0420, sha 8c0bd16c, as the whole out-of-combat policy at temperature
0; learned Silver stop gbt-0cac7cc64364; g7f_E root and tree prior, weight 400, K = 8; Act 4 strong; rollout root
table g7f_E; Gumbel root k 16 + max backup, min 4 visits, 16,000 per root).

| arm | combat | games |
|---|---|---|
| GP16 | G16 with `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0` (greedy playouts everywhere) | E0 (§790, code 966de5f7, binary 7f2800f0); 32 sentinel seeds rerun here |
| H4 | GP16 + `STS_SILVER_GUMBEL_ROOT_SIMS_HALLWAY=4000` | this campaign |
| A4P | G16 + `STS_SILVER_PRIOR_PLAYOUT_ACTS=4` (prior playouts at Shield and Spear and the Heart, greedy in Act 1-3) | this campaign |

`run_unit.sh` exits 79 if A4P's `.err` lacks the "prior playouts only in acts 4" line and 77 if another arm has it.

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order. `units.txt`: first 32 sentinel units
`SEED GP16` for 111378256-111378287 (lines 1-32), then for each seed `SEED H4` and `SEED A4P` (2,048 units, 2,080 in
all). `run_unit.sh` refuses any seed outside the block. Smoke on seed 111378263 (part of the block; the smoke games
are not used).

## Sentinel and control reuse (ADR-0064)

The 32 sentinel GP16 games replay E0's GP16 games on the same seeds with this binary (both flags unset). Fingerprint
as in E0 and E1: rc, abort flag, the whole .log except the BEST line's timing fields, and the .err lines
`[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots= sims=`. **32 of 32 identical = REUSE_VALID**: E0's 1,024
GP16 games are the controls. Anything else = REUSE_INVALID: no verdict (CONTROL_INVALID).

## Primary (`analyze.py`, frozen with this file; a copy of E1's first version with the arms, the env keys and A4P's gainer gate; `--self-test` passes)

For each arm A in (H4, A4P): d = Heart kill A − GP16 per seed. A seed counts if both games finished rc 0 with all log
checks and an env matching the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more
than 20 per arm = INCOMPLETE. Universe: seeds whose A unit was claimed (unit directory or claims snapshot). Alpha
**0.025 per arm** (two arms, Bonferroni), beta 0.05, look 64, cap = analysed seeds (≤ 1,024), seeds gap-free in
ascending order; one-sided 97.5% seed bootstrap bounds of mean d (10,000 resamples, seed 20261111). The 95% CI is
always reported.

- **H4** (a cost cut: must not lose): `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0). H1 = **NOT_WORSE**,
  H0 = **WORSE**. At CAP: **NOT_WORSE_3PP** if the lower bound > −3 pp, **WORSE** if the upper bound < 0, else
  **INCONCLUSIVE**.
- **A4P** (a cost add: must gain): **gainer** (H0 0, H1 +2 pp). H1 = **PASS**, H0 = **NOT_SHOWN**. At CAP: **PASS**
  if the lower bound > 0, else **NOT_SHOWN**.

**Cost (co-primary, with 95% seed bootstrap CIs):** CPU seconds per run, A / GP16, also corrected for machine speed
by the sentinel; Gumbel simulations per run; CPU per run quantiles (median, p90, p99, max) per arm.

**Expectation (inference, before any campaign game).** H4: CPU about 0.6-0.9× GP16 (the smoke: see
`results/smoke.txt`); effect 0 to −3 pp (hallway fights cost HP that later bosses need; §779's budget curve is flat
above 16k but steep below 8k). A4P: CPU about 1.5-2.5× GP16 (Act 4 strong's budgets with prior playouts, §781:
350-415 s per Act-4 run); effect +1 to +4 pp (half of E0's loss was in Act 4).

**Context for reading the control.** E0's GP16 draw shares §775's seeds; G16 on them may be on the high side
(five arms 2.3-5.5 pp below it). This does not change the gate.

**Power (inference).** As E0 and E1: a true 0 resolves H4 NOT_WORSE, a true ≤ −3 pp resolves WORSE; a true +3 pp
resolves A4P PASS, +1 to +2 pp probably reaches CAP.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

A4P − H4 with 95% CI; each arm's other SPRT variant; per arm Heart kill, act-4 reach (final floor ≥ 52), mean floor,
CPU sec per run, games over 1 h. In RESULT: A4P − G16 against §775's G16 games (same contrast code, sentinel of E0)
with 95% CI, to read how much of E0's 5.5 pp A4P recovers.

## Decision

No default change on this result.
- H4 NOT_WORSE or NOT_WORSE_3PP: hallway sims 4,000 joins the cheap-combat stack; a lower hallway budget (2,000) and
  elite budgets are the next step.
- A4P PASS: Act-4-only prior playouts join the stack at their CPU; combined with H4 if both pass (a combined arm is a
  new campaign, Philipp's go for compute is given for per-encounter budgets).
- Both fail: report; the next candidates are the proven-win stop (Heart CPU) and Act 4 budgets (Track 2).

## Cost and schedule

About 1,024 × 120-150 s (H4) + 1,024 × 250-400 s (A4P) + 32 × 150 s ≈ 110-160 lane-hours; 40 workers × 4 lanes, queue
schedule, about 45-75 min plus the slowest single game. Share: about 2,100 new files (tars, claims), about 80 MB.

## Smoke (local, this binary)

`results/smoke.txt`, seed 111378263: GP16 with both flags unset against E0's campaign game (identity of the default);
H4 and A4P (cost and outcome).
