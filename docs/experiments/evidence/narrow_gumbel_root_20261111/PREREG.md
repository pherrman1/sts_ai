# Narrow Gumbel root: k 4 without Gumbel noise at 8,000 simulations, prior or net candidates, whole-run gate against §775's G16 + mb4 (pre-registration)

**Authorization.** Philipp, 2026-11-11 22:59 CET in the cheap-combat roadmap thread ("jo lets go. was du gesagt
hast. aber lass auch schmale wurzel probieren, vllt reichen ja 92%. mach das nacheinander, je auf 40 workern. du
hast mein go für beides"): Track 1 of
the cheap combat roadmap (`docs/knowledge-base/research/combat-search/cheap-combat-roadmap.md`, PR #1034), after the
greedy-playout campaign (`greedy_playouts_g16_20261111`, PR #1035, "E0"). Reuses
§775's seeds (no new seeds). 40 workers; the coordinator starts them after the independent prelaunch review.

**Amendment before launch (2026-11-11 23:50 CET).** The first version used E0's GP16 as base and control. E0 ended
WORSE (GP16 −5.47 pp [−8.11, −2.93] against §775's G16 at 0.27× the CPU), and Philipp chose the base on a decision
card (23:47 CET: "G16 mit Prior-Playouts"): the control is §775's G16 + mb4 and P4 and N4 keep its prior playouts.
No campaign game had run; the review of the first version is void and this version is reviewed again.

## Question

Step 0b (evidence `cheap_combat_step0_20261111/README.md`, PR #1034) measured on T1's 310k validation roots (mean 6.3
legal actions) how often the Gumbel teacher's chosen action is among the prior's top k: k 4 = 88.6% for g7f_E and
91.9% for T1's distilled net (P-V_f1), k 6 = 96.1% / 97.5%. With Gumbel noise (as the whole-run root samples its
candidates today) the net's top-4 coverage falls to 82.4%. Can a k 4 root with the prior's deterministic top 4 and
half of G16's simulations keep G16 + mb4's Heart kill rate, and does the net's top 4 do better than g7f_E's?

## The flag (new, `STS_SILVER_GUMBEL_ROOT_NOISE`)

`NativeSilverBackend.cpp`: the whole-run Gumbel root's noise scale (default 1 = today's search, bit for bit; range
0-10, needs `STS_SILVER_GUMBEL_ROOT`). 0 sets g = 0 in both the candidate selection (top k of logit + g) and the
sequential halving score (logit + g + σ(q)); the Gumbel draws are still taken, so other random streams do not
shift. A value other than 1 adds ", noise X" to the banner ("k=4 max backup=4 (all acts, noise 0)"). Code commit
5fc8f890 (= origin/main d68cc984 + this flag), binary 5dcf3125 (preset linux-gcc-release-x86-64-v3).

## Arms (`run_unit.sh`)

All arms: §775's G16 environment (`gumbel_wholerun_20261108/run_unit.sh`, as E0's G16): net-0420 (sha 8c0bd16c) as
the whole out-of-combat policy (temperature 0, no OOC MCTS), learned Silver stop gbt-0cac7cc64364 (only gates Act 4
strong), g7f_E root and tree prior (weight 400, K = 8), Act 4 strong (Shield and Spear 10k, Heart 40k), rollout root
table g7f_E, prior playouts in boss rooms and at Shield and Spear (ADR-0050/0060), greedy elsewhere.

| arm | combat | games |
|---|---|---|
| G16 | Gumbel root k 16 + max backup (min 4 visits), noise 1, 16,000 per root | §775 (code 5665d5ae, binary 0eabb014); 32 sentinel seeds rerun here |
| P4 | Gumbel root k 4 + max backup 4, noise 0, 8,000 per root; candidates = g7f_E's top 4 | this campaign |
| N4 | P4 with T1's P-V_f1 net (`/mnt/project-files/gumbel-distill/t2/nets/pv_f1.ctn`, sha ac5fce0e) as root prior at every root (`STS_SILVER_COMBATNET_PRIOR=1`); candidates = the net's top 4 | this campaign |

N4's net prior is T2's mechanism (§788) at the root only; the tree prior below the root stays g7f_E. Its forward pass
costs about 2.5 ms per root, about 0.3% of an 8,000-simulation root.

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order. `units.txt`: first 32 sentinel units
`SEED G16` for 111378256-111378287 (lines 1-32), then for each seed `SEED P4` and `SEED N4` (2,048 units, 2,080 in
all). `run_unit.sh` refuses any seed outside the block. Smoke on seed 111378263 (part of the block; the smoke games
are not used).

## Sentinel and control reuse (ADR-0064)

The 32 sentinel G16 games replay §775's G16 games on the same seeds with this binary (the flag unset reproduces
today's search; E0's sentinel replayed them 32 of 32 with binary 7f2800f0). Fingerprint as in E0: rc, abort flag, the whole .log except the BEST line's timing fields, and the
.err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots= sims=`. **32 of 32 identical = REUSE_VALID**:
§775's 1,024 G16 games are the controls. Anything else = REUSE_INVALID: no verdict (CONTROL_INVALID).

## Primary (`analyze.py`, frozen with this file; a copy of E0's with the arms, the env key and per-arm alpha; `--self-test` passes)

For each arm A in (P4, N4): d = Heart kill A − G16 per seed. A seed counts if both games finished rc 0 with all log
checks and an env matching the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed;
more than 20 per arm = INCOMPLETE. Universe: seeds whose A unit was claimed (unit directory or claims snapshot).

Gate `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0), alpha **0.025 per arm** (two arms, Bonferroni),
beta 0.05, look 64, cap = analysed seeds (≤ 1,024), seeds gap-free in ascending order. H1 = **NOT_WORSE**; H0 =
**WORSE**. At CAP the one-sided 97.5% seed bootstrap bounds of mean d (10,000 resamples, seed 20261111) decide:
**NOT_WORSE_3PP** if the lower bound > −3 pp, **WORSE** if the upper bound < 0, else **INCONCLUSIVE**. The 95% CI is
always reported.

**Cost (co-primary, with 95% seed bootstrap CIs):** CPU seconds per run, A / G16, also corrected for machine speed
by the sentinel; Gumbel simulations per run; CPU per run quantiles (median, p90, p99, max) per arm.

**Expectation (inference, before any campaign game).** Cost: about 0.5-0.7× G16 (hallway fights and Act 4 strong
do not halve; `results/smoke.txt`). Effect: the teacher's pick is outside the top 4 at about 8-11% of roots, and half
the simulations deepen the rest; §781's plain budget curve lost about 6 pp from 16k to 8k, so a drop of 2-6 pp is
plausible; N4 ≥ P4 by up to 1-2 pp.

**Context for reading the control.** Five earlier whole-run arms against the same G16 games (§777, §780, §783,
§785, E0) all came out 2.3-5.5 pp below it, and G16 on fresh seeds scored 41.6% (§783's data campaign); §775's G16
draw may be on the high side. This does not change the gate.

**Power (inference).** As E0: true 0 resolves NOT_WORSE, true ≤ −3 pp resolves WORSE, −1 to −2 pp probably reaches CAP.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

N4 − P4 with 95% CI (does the net's top 4 beat the prior's?); each arm's gainer SPRT (+2 pp); per arm Heart kill,
act-4 reach (final floor ≥ 52), mean floor, CPU sec per run, games over 1 h.

## Decision

No default change on this result.
- An arm NOT_WORSE or NOT_WORSE_3PP: it replaces G16 + mb4 as the teacher-strength candidate at its CPU, and the
  per-encounter budget work (Philipp's go, 2026-11-11 23:43 CET) starts from it (N4 if both pass and N4 − P4 ≥ 0,
  else P4).
- Both WORSE or INCONCLUSIVE: report; the per-encounter budget work starts from G16 + mb4 and GP16.

## Cost and schedule

About 2,048 × 200-300 s + 32 × 500 s ≈ 120-180 lane-hours; 40 workers × 4 lanes, queue schedule, about 1-1.5 h plus
the slowest single game. Share: about 2,100 new files (tars, claims), about 80 MB.

## Smoke (local, this binary)

`results/smoke.txt`, seed 111378263: G16 with the flag unset against §775's game (identity of the default); GP16
against E0's campaign game (identity, first version); P4 and N4 with prior playouts (cost and outcome); the first
version's P4 and N4 without prior playouts (cost only).
