# Rollout prior, playout role: candidate V as G16 + mb4's prior-playout policy only, whole-run gate against §775's G16 + mb4 (pre-registration)

**Authorization.** Philipp 2026-11-16 10:51 CET, decision card in the thread for issue #1053 ("Soll das Gate „V nur
als Playout-Policy" gegen G16 laufen, und wann?"): "Nach der Fabrik (ab ca. 15:30)", i.e. after prior-factory batch 2
ends, on its 32 workers. The gate reuses §775's seeds (no new seeds).

## Question

§808 swapped all four g7f_E roles for V and lost 3.42 pp [−6.26, −0.59]; it cannot say which role. §807 scored V as
playout policy against a g7f_E-playout reference tree and found it worse, with that reference's bias as the stated
caveat. The offline playout test of 2026-11-16 (`one_combat playoutvaluebench`, 30,118 held-out factory boss /
Act-4 roots, 64 playouts each, common random numbers, reference = the played fight's recorded score) says the
opposite: V's playout values miss the actual outcome by less (MSE 1,019 vs 1,217, −199 [−252, −146]; Brier −0.015
[−0.019, −0.011]; greedy 2,973 as the sanity arm). Does G16 + mb4 win more Heart kills when V plays its prior
playouts and g7f_E keeps the root prior, the tree prior and the rollout root table?

## Arms (`run_unit.sh`)

Both arms: §775's environment as in §808 (`rollout_prior_wholerun_20261115/run_unit.sh`) on code 432bfae4 = §775's
code ba705ab4 plus the research option `STS_SILVER_PLAYOUT_POLICY` (default off; with it unset the code path is
ba705ab4's).

| arm | prior playouts | root prior, tree prior, rollout root table | games |
|---|---|---|---|
| G16 | g7f_E | g7f_E | §775; 32 sentinel seeds rerun here |
| GP | V (`students/rp_V.txt`, sha256 b366f6af…, §804) via `STS_SILVER_PLAYOUT_POLICY` | g7f_E | this campaign |

Prior playouts run in boss rooms and at Shield and Spear (ADR-0050 / 0060); they take the argmax of the playout
model every step. `run_unit.sh` checks §808's lines (with g7f_E as root prior and table in both arms) plus the
`[silver] playout policy model (research): <V>` line in GP and its absence in G16.

## Seeds and units

§775's seeds 111378256-111379279 (1,024, used; replays) in ascending order. `units.txt`: first the 32 sentinel units
`SEED G16` for 111378256-111378287 (lines 1-32), then 1,024 units `SEED GP`. One game per unit. `run_unit.sh` refuses
any seed outside the block.

## Sentinel and control reuse (ADR-0064)

As §799: the 32 sentinel games replay §775's G16 games with binary 97aec5b5 (§799's sentinel: 32/32 identical).
**32 of 32 identical = REUSE_VALID**: §775's 1,024 G16 games are the controls. Anything else: CONTROL_INVALID, no
verdict; a G16 rerun needs Philipp's go.

## Primary (`analyze.py`, frozen with this file; §799's with the arm GP and the two prior-path env keys; `--self-test` passes)

d = Heart kill GP − G16 per seed. A seed counts if both games finished rc 0 with all log checks and an env matching
the arm (a combat abort is a counted loss); dropped seeds are listed, never imputed; more than 20 = INCOMPLETE.

`tools/sprt_gate.py`, alpha 0.05, beta 0.05, look 64, cap = analysed seeds (≤ 1,024), seeds gap-free in ascending
order; both variants are computed by `analyze.py`:
- **gainer** (H0 0, H1 +2 pp): accepting H1 = **GAIN**.
- **nonregression** (H0 −1.5 pp, H1 0): accepting H1 = **NOT_WORSE**; accepting H0 = **WORSE**. At CAP the
  one-sided 95% seed bootstrap bounds (10,000 resamples, seed 20261116) decide: NOT_WORSE_3PP if the lower bound
  > −3 pp, WORSE if the upper bound < 0, else INCONCLUSIVE.

Verdict: GAIN if the gainer accepts H1 (or, at CAP, the lower one-sided 95% bound of mean d is above 0); otherwise
the nonregression label. The 95% CI is always reported.

**Cost (co-primary, with 95% seed bootstrap CIs):** CPU seconds per run GP / G16, also corrected for machine speed by
the sentinel; Gumbel simulations per run; CPU quantiles. V's native kernel cost per call is about g7f_E's (8.4 vs
8.0 µs per root, §804); the tree and playouts can still take other paths, so the ratio is measured.

**Expectation (inference).** The offline playout test says V's playouts estimate boss and Act-4 values better than
g7f_E's (MSE −16%); §807 (biased reference tree) says worse; §808 lost with V in all four roles, which this gate
splits. Prior playouts touch only boss rooms and Shield and Spear, so even a real effect is probably small: a result
between −3 and +3 pp is the most likely, and the gate will probably reach CAP.

## Secondary (not gates)

As §799: the other SPRT variant; GP − D (§775); per arm Heart kill, Act-4 reach (final floor ≥ 52), mean floor, CPU
per run, games over 1 h; Act-4 conversion (Heart kills per Act-4 arrival, and paired on seeds where both arms reach
Act 4); the contrast on the budget curve's first 512 seeds. Descriptive: where GP loses or gains (act of death).

## Decision

No default change on this result alone (a default change is Philipp's call).
- GAIN: V becomes the playout-policy candidate; next a CPU check and a default proposal; the offline playout test
  is then calibrated against a whole-run result and can rank further playout candidates (factory data).
- NOT_WORSE / NOT_WORSE_3PP / INCONCLUSIVE: no change; the offline test's ranking is not confirmed at game level.
- WORSE: the offline playout test does not predict game strength either; §808's loss is then at least partly the
  playout role.

## Cost and schedule

About 1,024 × ~600 s + 32 × 520 s ≈ 175 lane-hours (V's playouts cost more per call than g7f_E's; the smoke game took
1.5× CPU on the development binary with the pick cache in the control, about 1.1-1.3× expected here, where both arms
call the full prior); 32 workers × 4 lanes, queue, about 1.5-2 h plus the slowest game. Share: about 4,300 new files (unit tars and claim dirs),
about 60 MB.

## Smoke (local, this binary)

`results/smoke.txt`: the sentinel G16 game 111378256 is identical to §775's; GP on 111378263 passes all log checks
(Heart kill, 721 s CPU against §775's 675 s on a loaded machine).
