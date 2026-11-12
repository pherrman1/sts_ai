# Plan commitment, whole runs: play the inherited plan at chance-free continuation roots, always (PCH) or at a 90% visit share (PCS), on A4P (pre-registration)

**Authorization.** Philipp, 2026-11-12 10:39 CET in the cheap-combat roadmap thread. He tapped the decision card
"Plan-Weiterspielen als Ganzlauf-Gate gegen A4P testen?" and chose "Ja, hart + weich (0,9)", meaning two arms against
A4P on §775's seeds with 40 workers, about 80-120 lane-hours. The idea is his, from 2026-11-12 08:33 CET: "can we maybe
play out cards until the next chance nodes? I.e. gumbel does not only decide the root, but also the x next actions with
highest value until we hit a chance node". The campaign reuses §775's seeds, so no new seeds are needed. The
coordinator starts the 40 workers after the independent prelaunch review.

## Question

A whole-run Gumbel search (§775's G16 + mb4, here A4P of §792: prior playouts in Act 4 only, 37.30% Heart kills at
297 s per run) searches every root afresh with 16,000 simulations, even when the previous root's search already
planned the move.

A root is a **chance-free continuation** when two things hold:
- the previous root's chosen edge leads in the tree to a decision node, not a chance node;
- that node is the new root, so no draw or other randomness happened in between.

At such a root the reused tree already holds a plan: the edge with the most inherited visits.

The offline check (`results/offline.txt`) used 32 A4P runs that reached the Heart (§792's seeds, recorder
`endgamerootgen` with pre-search edges). It approximated continuation roots as the same turn with one card fewer in
hand:
- These roots hold about 50% of the elite, boss and Heart simulations.
- The plan equals the searched choice at 61% of Heart roots, 70% of boss roots and 74% of elite roots.
- Where the two differ, the final root values are nearly tied: median Q gap 0, mean 0.1-0.3, against a Q range of about 8 at the Heart.
- When the plan edge holds at least 90% of the inherited visits, the agreement is 88-92%.

Offline agreement cannot show whether the disagreements cost Heart kills; only whole runs can. Does A4P keep its
Heart kill rate when it plays the inherited plan without a search, and how much CPU does that save?

## The flag (new, default off, defaults unchanged)

`STS_SILVER_PLAN_COMMIT=hard|S` lives in `NativeSilverBackend.cpp`, is listed in `one_combat`'s environment allowlist
and is documented in `docs/knowledge-base/operations/environment-variables.md`. It needs `STS_SILVER_GUMBEL_ROOT`.
- **Where it acts.** In a whole-run Gumbel fight, after each decision the backend keeps the tree's child of the chosen
  root edge if that child is a decision node.
- **Which roots are eligible.** At the next root, the root is a chance-free continuation if `findNode` on the new root
  returns that child (checked before the reroot). It is eligible if, in addition, it has more than one legal action
  and inherited visits.
- **What it plays.** An eligible root plays the edge with the most inherited visits, without a search. Ties go to the
  higher mean value, then to the first edge. The play goes through `SilverSearcher::commitRootEdge`, so
  `bestAction()` returns that edge.
- **`hard` and S.** `hard` commits at every eligible root. A share S in (0, 1] commits only when the plan edge holds
  at least S of the root's inherited edge visits; otherwise the root searches as without the flag.
- **The chain.** A committed root's chosen edge is again followed, so a plan plays out until the next chance node,
  for example an end of turn or a draw.
- **Printed lines.** The flag prints `[silver] research search: plan commit hard` or `... plan commit min share S`,
  and at exit `[silver] plan commit: eligible=E commits=C unspent_sims=U`.

The same code commit adds `preEdges` to `one_combat endgamerootgen` rows (the root edges with visits and mean value
before the search). That field is observer only and was used for the offline check.

Code commit 3c85fb26 is origin/main d25db011 plus the flag and the recorder field. The binary sha is
ca8d9d0bdf6f690de19d0e6e6e4b693a3b90f58ca46a9cd82ad53e6a2335b689 (preset linux-gcc-release-x86-64-v3).

## Arms (`run_unit.sh`)

All arms use §792's A4P environment: §775's G16 + mb4 with `STS_SILVER_PRIOR_PLAYOUT_ACTS=4`, net-0420 (sha
8c0bd16c) as the whole out-of-combat policy at temperature 0, learned Silver stop gbt-0cac7cc64364, the g7f_E root and
tree prior (weight 400, K = 8), Act 4 strong, rollout root table g7f_E, and Gumbel root k 16 + max backup with 16,000
simulations per root.

| arm | combat | games |
|---|---|---|
| A4P | as §792 (flag unset) | §792 (code 4c4e42eb, binary e60e2614); 32 sentinel seeds are rerun here |
| PCH | A4P + `STS_SILVER_PLAN_COMMIT=hard` | this campaign |
| PCS | A4P + `STS_SILVER_PLAN_COMMIT=0.9` | this campaign |

`run_unit.sh` checks the plan-commit lines:
- exit 79 if any arm lacks the "prior playouts only in acts 4" line;
- exit 76 or 75 if PCH or PCS lacks its banner or its exit counters;
- exit 77 if A4P prints any "plan commit" line.

## Seeds and units

§775's seeds 111378256-111379279 (1,024 seeds, already used; these are replays) run in ascending order. `units.txt`
lists:
- lines 1-32: the sentinel units `SEED A4P` for 111378256-111378287;
- then, for each seed, `SEED PCH` and `SEED PCS` (2,048 units, 2,080 in all).

`run_unit.sh` refuses any seed outside the block. The smoke ran on seeds 111378263 and 111378259, both in the block;
the smoke games are not used.

## Sentinel and control reuse (ADR-0064)

The 32 sentinel A4P games replay §792's A4P games on the same seeds with this binary (flag unset). The fingerprint is
the same as in §790-§792:
- rc and the abort flag;
- the whole .log except the BEST line's timing fields;
- the .err lines `[heart1_ppo] seed=` and `[silver] whole-run Gumbel roots= sims=`.

**32 of 32 identical = REUSE_VALID**, and §792's 1,024 A4P games are the controls. Anything else is REUSE_INVALID and
gives no verdict (CONTROL_INVALID).

## Primary (`analyze.py`, frozen with this file; `--self-test` passes)

`analyze.py` is a copy of §792's with the arms, the env keys, the sentinel arm and both gates as nonregression gates.
- **The contrast.** For each arm A in (PCH, PCS), d = Heart kill of A − Heart kill of A4P, per seed.
- **Which seeds count.** A seed counts if both games finished with rc 0, passed all log checks and had an env matching
  the arm. A combat abort is a counted loss.
- **Drops.** Dropped seeds are listed, never imputed; more than 20 per arm makes the arm INCOMPLETE.
- **Universe.** The seeds whose unit for A was claimed (a unit directory or the claims snapshot).
- **Test settings.** Alpha 0.025 per arm (two arms, Bonferroni), beta 0.05, look 64, cap = analysed seeds (at most
  1,024), with the seeds taken gap-free in ascending order.
- **Bounds.** The one-sided 97.5% seed bootstrap bounds of mean d use 10,000 resamples with seed 20261111. The 95% CI
  is always reported.

Both arms are cost cuts and must not lose. The gate is `tools/sprt_gate.py` **nonregression** (H0 −1.5 pp, H1 0): H1
is **NOT_WORSE**, H0 is **WORSE**. At CAP:
- **NOT_WORSE_3PP** if the lower bound > −3 pp;
- **WORSE** if the upper bound < 0;
- else **INCONCLUSIVE**.

**Cost (co-primary, with 95% seed bootstrap CIs):**
- CPU seconds per run, A / A4P, also corrected for machine speed by the sentinel;
- Gumbel simulations per run;
- plan commits per run;
- CPU per run quantiles (median, p90, p99, max) per arm.

**Expectation (inference, before any campaign game).**
- **Cost.** From the smoke: PCH about 0.4-0.6× A4P's CPU (about 120-180 s per run), PCS about 0.6-0.8×.
- **Effect.** PCH 0 to −4 pp: about 30-40% of eligible roots would have chosen differently after a search; the values
  are nearly tied, but a near tie at the root can still matter later in the fight. PCS 0 to −2 pp.

**Power (inference).** As in §790-§792: a true 0 resolves NOT_WORSE, and a true −3 pp or worse resolves WORSE.

**Stopping.** Every seed runs; "crossed at" is reported.

## Secondary (not gates)

- PCS − PCH, with 95% CI;
- each arm's gainer SPRT;
- per arm: Heart kill, Act-4 reach (final floor ≥ 52), mean floor, CPU seconds per run, plan eligible roots and
  commits per run, and games over 1 h.
- In RESULT: each arm − GP16 against §790's GP16 games (same seeds, same contrast code), because GP16 is the cheap
  stack's reference at 143 s.

## Decision

No default changes on this result.
- **PCH or PCS NOT_WORSE / NOT_WORSE_3PP.** Plan commitment joins the cheap-combat stack at its CPU; the cheaper
  passing arm is preferred. The next step is a combined arm with H4, or with plan commitment on G16 (prior playouts in
  Act 1-3 back, paid for by the savings).
- **Both WORSE or INCONCLUSIVE.** Report. A higher share (0.95) or a committed plan only within a turn's first k
  actions are follow-ups.

## Cost and schedule

About 1,024 × 120-180 s (PCH) + 1,024 × 180-240 s (PCS) + 32 × 300 s ≈ 95-130 lane-hours. That is 40 workers × 4
lanes on a queue schedule, about 40-55 min plus the slowest single game. The share takes about 2,100 new files (tars and
claims), about 80 MB.

## Smoke (local, this binary)

`results/smoke.txt`:
- A4P with the flag unset against §792's campaign game on 111378263 (identity);
- PCH and PCS on 111378263 and PCH on 111378259 (cost and outcome).
