# Narrow Gumbel root: k 4 without Gumbel noise at 8,000 simulations, prior or net candidates, whole-run gate against GP16 (pre-registration)

**Authorization.** Philipp, 2026-11-11 22:59 CET in the cheap-combat roadmap thread ("jo lets go. was du gesagt
hast. aber lass auch schmale wurzel probieren, vllt reichen ja 92%. mach das nacheinander, je auf 40 workern. du
hast mein go für beides"): Track 1 of
the cheap combat roadmap (`docs/knowledge-base/research/combat-search/cheap-combat-roadmap.md`, PR #1034), after the
greedy-playout campaign (`greedy_playouts_g16_20261111`, PR #1035, "E0"). Reuses
§775's seeds (no new seeds). 40 workers; the coordinator starts them after the independent prelaunch review and
after E0's last game.

## Question

Step 0b (evidence `cheap_combat_step0_20261111/README.md`, PR #1034) measured on T1's 310k validation roots (mean 6.3
legal actions) how often the Gumbel teacher's chosen action is among the prior's top k: k 4 = 88.6% for g7f_E and
91.9% for T1's distilled net (P-V_f1), k 6 = 96.1% / 97.5%. With Gumbel noise (as the whole-run root samples its
candidates today) the net's top-4 coverage falls to 82.4%. Can a k 4 root with the prior's deterministic top 4 and
half of G16's simulations keep GP16's Heart kill rate, and does the net's top 4 do better than g7f_E's?

## The flag (new, `STS_SILVER_GUMBEL_ROOT_NOISE`)

`NativeSilverBackend.cpp`: the whole-run Gumbel root's noise scale (default 1 = today's search, bit for bit; range
0-10, needs `STS_SILVER_GUMBEL_ROOT`). 0 sets g = 0 in both the candidate selection (top k of logit + g) and the
sequential halving score (logit + g + σ(q)); the Gumbel draws are still taken, so other random streams do not
shift. A value other than 1 adds ", noise X" to the banner ("k=4 max backup=4 (all acts, noise 0)"). Code commit
5fc8f890 (= origin/main d68cc984 + this flag), binary 5dcf3125 (preset linux-gcc-release-x86-64-v3).

## Arms (`run_unit.sh`)

All arms: E0's GP16 environment (§775's, with `STS_SILVER_PRIOR_PLAYOUT_BOSS_ELITE=0`): net-0420 (sha 8c0bd16c) as
the whole out-of-combat policy (temperature 0, no OOC MCTS), learned Silver stop gbt-0cac7cc64364 (only gates Act 4
strong), g7f_E root and tree prior (weight 400, K = 8), Act 4 strong (Shield and Spear 10k, Heart 40k), rollout root
table g7f_E, greedy playouts everywhere.

| arm | combat | games |
|---|---|---|
| GP16 | Gumbel root k 16 + max backup (min 4 visits), noise 1, 16,000 per root | E0 (code 966de5f7, binary 7f2800f0); 32 sentinel seeds rerun here |
| P4 | Gumbel root k 4 + max backup 4, noise 0, 8,000 per root; candidates = g7f_E's top 4 | this campaign |
| N4 | P4 with T1's P-V_f1 net (`/mnt/project-files/gumbel-distill/t2/nets/pv_f1.ctn`, sha ac5fce0e) as root prior at every root (`STS_SILVER_COMBATNET_PRIOR=1`); candidates = the net's top 4 | this campaign |

N4's net prior is T2's mechanism (§788) at the root only; the tree prior below the root stays g7f_E. Its forward pass
costs about 2.5 ms per root, about 0.3% of an 8,000-simulation root.

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order. `units.txt`: first 32 sentinel units
`SEED GP16` for 111378256-111378287 (lines 1-32), then for each seed `SEED P4` and `SEED N4` (2,048 units, 2,080 in
all). `run_unit.sh` refuses any seed outside the block. Smoke on seed 111378263 (part of the block; the smoke games
are not used).

## Sentinel and control reuse (ADR-0064)

The 32 sentinel GP16 games replay E0's GP16 games on the same seeds with this binary (the flag unset reproduces
today's search). Fingerprint as in E0: rc, abort flag, the whole .log except the BEST line's timing fields, and the
.err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots= sims=`. **32 of 32 identical = REUSE_VALID**:
E0's 1,024 GP16 games are the controls. Anything else = REUSE_INVALID: no verdict (CONTROL_INVALID).

**Base arm condition.** This campaign launches against GP16 only if E0 ends NOT_WORSE or NOT_WORSE_3PP. If E0 ends
WORSE or INCONCLUSIVE, this file is amended before launch (control = §775's G16, P4 and N4 with prior playouts as
G16) and reviewed again.

## Primary (`analyze.py`, frozen with this file; a copy of E0's with the arms, the env key and per-arm alpha; `--self-test` passes)

For each arm A in (P4, N4): d = Heart kill A − GP16 per seed. A seed counts if both games finished rc 0 with all log
checks and an env matching the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed;
more than 20 per arm = INCOMPLETE. Universe: seeds whose A unit was claimed (unit directory or claims snapshot).

Gate `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0), alpha **0.025 per arm** (two arms, Bonferroni),
beta 0.05, look 64, cap = analysed seeds (≤ 1,024), seeds gap-free in ascending order. H1 = **NOT_WORSE**; H0 =
**WORSE**. At CAP the one-sided 97.5% seed bootstrap bounds of mean d (10,000 resamples, seed 20261111) decide:
**NOT_WORSE_3PP** if the lower bound > −3 pp, **WORSE** if the upper bound < 0, else **INCONCLUSIVE**. The 95% CI is
always reported.

**Cost (co-primary, with 95% seed bootstrap CIs):** CPU seconds per run, A / GP16, also corrected for machine speed
by the sentinel; Gumbel simulations per run; CPU per run quantiles (median, p90, p99, max) per arm.

**Expectation (inference, before any campaign game).** Cost: about 0.55-0.7× GP16 (hallway fights and Act 4 strong
do not halve; the smoke on seed 111378263: GP16 171 s, P4 106 s, N4 100 s, all three killed the Heart). Effect: the
teacher's pick is outside the top 4 at about 8-11% of roots, and half the simulations deepen the rest; a drop of
1-4 pp is plausible, N4 ≥ P4 by up to 1-2 pp.

**Context for reading the control.** E0's GP16 games are the control; how E0 compared with §775 is reported there.

**Power (inference).** As E0: true 0 resolves NOT_WORSE, true ≤ −3 pp resolves WORSE, −1 to −2 pp probably reaches CAP.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

N4 − P4 with 95% CI (does the net's top 4 beat the prior's?); each arm's gainer SPRT (+2 pp); per arm Heart kill,
act-4 reach (final floor ≥ 52), mean floor, CPU sec per run, games over 1 h.

## Decision

No default change on this result.
- An arm NOT_WORSE or NOT_WORSE_3PP at ≤ 0.7× GP16's CPU: it replaces GP16 as the cheap-combat candidate; Act 4's
  budget (Track 2) is tuned on top of the cheaper arm (N4 if both pass and N4 − P4 ≥ 0, else P4).
- Both WORSE or INCONCLUSIVE: report; candidate follow-up (Philipp's call) k 6 (97.5% coverage) or k 4 at 16,000.

## Cost and schedule

About 2,048 × 80-150 s + 32 × 200 s ≈ 50-90 lane-hours; 40 workers × 4 lanes, queue schedule, about 30-60 min plus
the slowest single game. Share: about 2,100 new files (tars, claims), about 80 MB.

## Smoke (local, this binary)

`results/smoke.txt`: seed 111378263, G16 with the flag unset against §775's game (identity of the default), GP16
against E0's smoke and campaign game, P4 and N4 (cost and outcome).
