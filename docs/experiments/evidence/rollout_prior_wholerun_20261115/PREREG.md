# Rollout prior stage 3: candidate V in place of g7f_E in G16 + mb4, whole-run gate against §775's G16 + mb4 (pre-registration)

**Authorization.** Philipp, 2026-11-15 21:55 CET in the thread for issue #1053: "sollten wir nicht den trainierten
prior auch innerhalb des baumes verwenden? also um nach der root die nächsten züge zu berwerten? wie macht das og
gumbel paper das?"; 21:59 CET: "würde die root tabelle auch ändern. Die idee ist doch eigentlich: gumbel 16k spielt
sehr stark, ist ein guter teacher, daher wollen wir das ein prior möglichst nahe an gumbel rankommt. go auf 32 worker
daanach ahst du" (after the stage-2 run). 32 workers. The gate reuses §775's seeds (no new seeds).

## Question

Stage 1 (§804) trained V, a g7f_E-shaped MLP on G16 + mb4 visit shares, which picks better root moves than g7f_E on
every playout encounter (max-backed root regret 1.884 vs 2.449 in playout rooms, 1.364 vs 1.952 on all rooms).
Stage 2 (rollout_prior_stage2_20261115) swaps only the playout policy and scores picks against the g7f_E-playout tree,
a reference that favours g7f_E. In Gumbel MuZero one network serves the root and every node below it. Does G16 + mb4
win more Heart kills when V replaces g7f_E in every role?

## Arms (`run_unit.sh`)

Both arms: §775's environment as in §799 (`gumbel_g12_heart24_20261113/run_unit.sh`, code ba705ab4, binary
97aec5b5): net-0420 (sha 8c0bd16c) as the whole out-of-combat policy (temperature 0, no OOC MCTS), learned Silver stop
gbt-0cac7cc64364 (gates Act 4 strong only), Gumbel root k 16 + max backup (min 4 visits) at a flat 16,000 in every
fight of acts 1-3 and at Shield and Spear, the Heart at 40,000 with the 262,144-node reuse cap, prior weight 400,
tree prior K = 8, boss-only prior playouts (ADR-0050) plus Shield and Spear (ADR-0060).

| arm | prior model | games |
|---|---|---|
| G16 | g7f_E (`models/combat_policy_mlp_g7f_E.txt`) as `STS_SILVER_ROOT_PRIOR` and `STS_SILVER_ROLLOUT_ROOT_TABLE` | §775 (binary 0eabb014); 32 sentinel seeds rerun here |
| GV | V (`students/rp_V.txt`, sha256 b366f6af…, §804) as both | this campaign |

`STS_SILVER_ROOT_PRIOR` is the model of three roles: the root prior (Gumbel top-k and the improved-policy logits),
the tree prior below the root (K = 8) and the boss / Act-4 prior playouts (the playout prior is always the root-prior
model). `STS_SILVER_ROLLOUT_ROOT_TABLE` is the fourth: the per-root card table of the greedy playouts in all other
fights (ADR-0046 / 0049). GV swaps all four, so a result cannot say which role carries it. The two single-role arms
(tree + root only; playouts only) are follow-ups. No code change: both are existing options.

`run_unit.sh` checks for each arm the root-prior line and the root-table line with the arm's model path, V's sha256,
plus every check of §799 (the sims line, the Gumbel and Act-4 banners with Heart 40k, no research act4 heart budget).

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order. `units.txt`: first the 32 sentinel units
`SEED G16` for 111378256-111378287 (lines 1-32), then 1,024 units `SEED GV`. One game per unit. `run_unit.sh` refuses
any seed outside the block.

## Sentinel and control reuse (ADR-0064)

As §799: the 32 sentinel games replay §775's G16 games with binary 97aec5b5 (§799's sentinel: 32/32 identical).
**32 of 32 identical = REUSE_VALID**: §775's 1,024 G16 games are the controls. Anything else: CONTROL_INVALID, no
verdict; a G16 rerun needs Philipp's go.

## Primary (`analyze.py`, frozen with this file; §799's with the arm GV and the two prior-path env keys; `--self-test` passes)

d = Heart kill GV − G16 per seed. A seed counts if both games finished rc 0 with all log checks and an env matching
the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more than 20 = INCOMPLETE.

`tools/sprt_gate.py`, alpha 0.05, beta 0.05, look 64, cap = analysed seeds (≤ 1,024), seeds gap-free in ascending
order; both variants are computed by `analyze.py`:
- **gainer** (H0 0, H1 +2 pp): accepting H1 = **GAIN**.
- **nonregression** (H0 −1.5 pp, H1 0): accepting H1 = **NOT_WORSE**; accepting H0 = **WORSE**. At CAP the
  one-sided 95% seed bootstrap bounds (10,000 resamples, seed 20261115) decide: NOT_WORSE_3PP if the lower bound
  > −3 pp, WORSE if the upper bound < 0, else INCONCLUSIVE.

Verdict: GAIN if the gainer accepts H1 (or, at CAP, the lower one-sided 95% bound of mean d is above 0); otherwise
the nonregression label. The 95% CI is always reported.

**Cost (co-primary, with 95% seed bootstrap CIs):** CPU seconds per run GV / G16, also corrected for machine speed by
the sentinel; Gumbel simulations per run; CPU quantiles. V's native kernel cost per call is about g7f_E's (8.4 vs
8.0 µs per root, §804); the tree and playouts can still take other paths, so the ratio is measured.

**Expectation (inference).** Root regret says V is the better policy; stage 2's interim numbers (biased toward g7f_E)
say V is not a better playout policy. T2 (§788, distilled transformer as root and tree prior, playouts g7f_E): −1.37
pp NOT_SHOWN. A result between −3 and +3 pp is the most likely; this gate resolves a true +2 pp gain or a true −1.5 pp
loss, and smaller effects will probably reach CAP.

## Secondary (not gates)

As §799: the other SPRT variant; GV − D (§775); per arm Heart kill, Act-4 reach (final floor ≥ 52), mean floor, CPU
per run, games over 1 h; Act-4 conversion (Heart kills per Act-4 arrival, and paired on seeds where both arms reach
Act 4); the contrast on the budget curve's first 512 seeds. Descriptive: where GV loses or gains (act of death).

## Decision

No default change on this result alone (a default change is Philipp's call).
- GAIN: V is a candidate to replace g7f_E; next the single-role arms and a CPU check, then a default proposal.
- NOT_WORSE / NOT_WORSE_3PP / INCONCLUSIVE: no change; the single-role follow-ups say which role helps or hurts.
- WORSE: root-trained targets do not carry over; next is training on captured playout and tree states labelled by
  short searches (DAgger-style, PREREG stage 1 "Stage 3 and later").

## Cost and schedule

About 1,024 × ~520 s + 32 × 520 s ≈ 150 lane-hours; 32 workers × 4 lanes, queue schedule, about 1.5-2 h plus the
slowest game (≤ 1 h). Share: about 2,100 new files, about 60 MB.

## Smoke (local, this binary)

`results/smoke.txt`: GV on §775's seed 111378263 and the sentinel G16 game 111378256 against §775's.
