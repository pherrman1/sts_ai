# Simulation-balanced playout policy: candidate SBC instead of V as G16 + mb4's prior-playout policy, whole-run gate against §815's GP (pre-registration)

**Authorization.** Philipp 2026-11-16 20:33 CET in the thread for issue #1053 ("ja bau das offline maß. und ja zu
spiel test"), answering the proposal: the run-3 winner as playout policy against V, the same 1,024 seeds as the GP
gate (§815), about 6 h on 32 workers. No new seeds. Worker count raised to 40 by Philipp at 21:30 CET ("nimm 40
worker"), before launch.

## Question

§815 (GP: V only as prior-playout policy) gained +2.34 pp [−0.10, +4.79] over §775's G16 + mb4, the direction the
offline playout value-error test (§814, `one_combat playoutvaluebench`) predicted. That is one calibration point.
Since then a playout policy was trained directly on that error (simulation balancing, Silver & Tesauro 2009;
`tools/rollout_prior/sim_balance.py`). If lower playout value error means better playouts in search, the candidate
should beat V in whole runs. If it does not, the offline measure is optimizing the wrong thing. Either answer is the
second calibration point Philipp asked for.

## Candidate SBC (frozen before launch)

- Start: net C = `rp_W256pg` (GPU, 256/128, trained on the prior factory's playout-room states plus the old D2 roots,
  search-imitation loss; PC transfer commit f0e8be7).
- Simulation balancing, run 3: 40 rounds of 1,000 batch-2 factory roots × 16 sampled playouts (T = 0.1), traced
  steps at rate 0.25, Adam lr 1e-5, gradient (V̄₋ᵢ − V*)(zᵢ − b₋ᵢ) Σ ∇log π. Batch-2 roots are disjoint from the
  batch-1 validation roots below.
- Selection rule (Philipp 20:34 CET: choose the winner on a better measure than raw MSE): the checkpoint with the
  lowest **per-boss-debiased** argmax MSE, i.e. the MSE after subtracting each encounter's mean error, because a
  constant offset does not change how a search ranks sibling actions. On the 3,000-root selection set (val3k)
  rounds 10, 30 and 40 were within noise (640 / 646 / 647); all three were then scored on all 30,118 batch-1
  validation roots (64 playouts, common random numbers), and round 40 has the lowest debiased MSE there:

  | playout policy | raw MSE | debiased MSE | bias |
  |---|---|---|---|
  | g7f_E | 1,217 | 791 | −19.9 |
  | V | 1,019 | 688 | −17.2 |
  | C (start) | 941 | 660 | −15.8 |
  | SB round 10 | 884 | 627 | −15.0 |
  | SB round 30 | 877 | 641 | −14.4 |
  | **SB round 40 = SBC** | **853** | **617** | −14.5 |

  Paired against V (seed bootstrap): raw −166 [−247, −38], debiased −71 [−125, +20]; against round 10, debiased
  −11 [−25, +8]. The wide interval against V comes mostly from one Heart fight (seed 113200557, fight 33) whose
  roots V plays out to the recorded 188 and the C-based nets to about −20 to −50; SBC inherits this from C. So
  the offline evidence for SBC over V is about 10% lower debiased error with a heavy tail, not a clean separation;
  that is part of what this gate tests.
- The model file is `students/rp_SBC.txt` (run 3's model_040.txt), sha256 8037fd246fcceb22…. Argmax of the model every playout step (as GP).

## Arms (`run_unit.sh`)

Code 432bfae4 (§815's code; binary 85a6cf3e from the bin cache), §815's environment.

| arm | prior playouts | root prior, tree prior, rollout root table | games |
|---|---|---|---|
| GP | V (`rollout_prior_playout_20261116/students/rp_V.txt`, sha256 b366f6af…) | g7f_E | §815's; 32 sentinel seeds rerun here |
| GS | SBC (`students/rp_SBC.txt`) | g7f_E | this campaign |

`run_unit.sh` keeps all of §815's log checks and requires the line `[silver] playout policy model (research): <model>`
with the arm's model.

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays), as §815. `units.txt`: first the 32 sentinel units `SEED GP`
for 111378256-111378287 (lines 1-32), then 1,024 units `SEED GS`. One game per unit.

## Sentinel and control reuse (ADR-0064)

The 32 sentinel GP games must replay §815's GP games on the same binary 85a6cf3e (fingerprint as §815: rc, abort
flag, the whole .log except BEST timing, the .err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel
roots=`). **32 of 32 identical = REUSE_VALID**: §815's 1,024 GP games are the controls. Anything else:
CONTROL_INVALID, no verdict; a GP rerun needs Philipp's go.

## Primary (`analyze.py`, frozen with this file; §815's with the arms GP -> control, GS -> candidate; `--self-test` passes)

d = Heart kill GS − GP per seed (GP = §815's game). Counting, drops (more than 20 = INCOMPLETE), gap-free ascending
seeds and the two `tools/sprt_gate.py` variants (alpha 0.05, beta 0.05, look 64, cap = analysed seeds) exactly as
§815:
- **gainer** (H0 0, H1 +2 pp): accepting H1 = **GAIN**.
- **nonregression** (H0 −1.5 pp, H1 0): NOT_WORSE / WORSE; at CAP the one-sided 95% seed bootstrap bounds decide
  NOT_WORSE_3PP (lower > −3 pp), WORSE (upper < 0), else INCONCLUSIVE.

Verdict: GAIN if the gainer accepts H1 (or at CAP the lower one-sided 95% bound of mean d is above 0); otherwise the
nonregression label. The 95% CI is always reported.

**Cost (co-primary):** CPU seconds per run GS / GP with 95% CI, machine-corrected by the sentinel; Gumbel simulations
per run. SBC is a 256/128 network against V's 128/64, so each playout step costs more; this gate compares at equal
simulations, not equal CPU, and the cost is reported next to the verdict.

## Secondary (not gates)

GS − G16 (§775's games, read from §775's units); the primary on the first 512 seeds; per arm Heart kill, Act-4 reach,
mean floor, CPU per run, games over 1 h; Act-4 conversion GP / GS.

## Decision

No default change on this result alone (a default change is Philipp's call).
- GAIN: the playout value error (debiased) is confirmed as a selection measure at game level (two points in the
  same direction); next: simulation balancing as the regular training step of the playout policy, an equal-CPU
  check, and a default proposal.
- NOT_WORSE / NOT_WORSE_3PP / INCONCLUSIVE: the measure's further gain does not show in games at this size; the
  offline measure stays a pre-filter only.
- WORSE: lower playout value error does not mean better search playouts; the measure is not used to select.

## Cost and schedule

About 1,024 × ~850 s + 32 × 580 s ≈ 250 lane-hours (SBC's playouts cost more per step than V's); 40 workers × 4
lanes, queue, about 1.5-2 h plus the slowest game.
Share: about 4,300 new files (unit tars and claim dirs), about 60 MB.

## Smoke (local, this binary)

`results/smoke.txt`: the sentinel GP game 111378256 is identical to §815's (analyze.py fingerprint); GS on 111378263
passes all log checks (Heart kill, 1,173 s CPU against §815's GP 686 s on that seed, on a container running five
CPU-bound jobs on four vCPUs, so the ratio is inflated; SBC's 256/128 forward is still clearly costlier than V's).
