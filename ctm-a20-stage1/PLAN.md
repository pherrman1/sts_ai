# A20 CTM: plan (ledger §443, DRAFT, not frozen)

Requested by Philipp on 2026-10-12 ("Can we do the same for A20 ctm?", then "Plan it" on the card).
Seeds: everything stays inside 78000000–78999999 (block assigned by the coordinator).

## Why
- The production CTM (pathb-r2 + §435 Lizard header) is trained only on A0 (Path B, ascension 0). With
  `ascension=20` as input it predicts death 0 and full HP for every fight. §416 found this, and on 2026-10-12 it
  reproduced with `ctmscorerows` on the fixture rows: p_death 0, HP 80/80 at ASC 20 vs nonzero risk at ASC 0.
- `combat_predictor_input.cpp:60` passes `gc.ascension` straight into the CTM. **Inference:** every A20 OOC MCTS
  search so far (§425, §426, the A20 gold work) priced imagined combats as free wins.
- A20 corpus data also covers the A20-only states that abort today (max HP 23 < trained minimum 24, #369).

## Smoke (done, 2026-10-12)
`combattransitiongen 1 10000 20` at main `fcd253f1` (binary `c3c5e950…`), learned-stop Path B teacher, seeds
78009000–003: 4/4 rc=0, 28 rows, 2–16 s per seed. 26 of the 28 rows are act 1, because the generator's
out-of-combat policy (`agent.stepOutOfCombatPolicy`, the same as for A0 Path B) dies early at A20 (last floors 8–23).
Raw: `smoke-78009000-003.tgz` here.

## Stages and decision rules
**Stage 0: calibration check (cheap, one cloud thread, ~2 CPU-h).**
- Generate 1,000 A20 seeds (78100000–78100999) with the Path B generator.
- Score every row with the production CTM three ways: (a) ASC 20 as is, (b) ascension clamped to 0, and
  (c) the observed Silver outcome.
- Report survival NLL, bias by act and room class, and HP NLL.
- Decision:
  - If (b) has |survival bias| ≤ 0.01 overall and on elites/bosses, and HP bias within ±3 HP, the cheap fix is
    clamping the CTM's ascension input to 0 (one line, behind a flag, gated like any change). No retrain.
  - Otherwise go to Stage 1.
- Stage 0 also reports act coverage, which decides G0.

**G0: generator policy (decided from Stage 0).** If acts 2–3 hold under 25% of the rows, switch the A20 corpus to
the deployed OOC step (`deployedOocPolicyStep`, §431) so later acts and bosses are covered. That is a small code change
with its own review, and it shifts the out-of-combat distribution relative to the A0 corpus.

**Stage 1: A20 corpus (multi-worker, your worker count).**
- Main corpus: 78200000–78299999, sized to roughly the A0 union (537k rows), generated with
  `STS_CTM_GEN_DEPLOYED_OOC=1` (G0, PR #498). G0 smoke: 17.4 rows and ~10.6 CPU-s per seed, so ~31k seeds and
  ~92 CPU-h, ~100 CPU-h with the forced slices (Inference, from 40 seeds).
- Forced slices as for A0: `lizard_fairy` 78300000–78300599, `lizard_brew` 78301000–78301599, `ritual_writhing`
  78302000–78302399, `high_maxhp` 78303000–78303099.
- Smokes: 78009000–78009099.
- Same scripts as A0 Path B (`ctm-pathb/PLAN.md`: `make_teacher.py`, `units.py`, `run_worker.sh`, `run_part.sh`)
  with ASC=20. One tar plus a DONE file per worker. Frozen SHA and binary are recorded before launch.

**Stage 2: A20 artifact (Philipp's GPU via RC, like #418).**
- A separate A20 stack, warm-started from pathb-r2 and refit on the A20 union. A0 stays byte-identical, so no A0
  requalification is needed.
- Its own declared HP domain, with the max-HP floor below 24 (`ctm_hp_domain.py`).
- Escape and Lizard Fairy/Brew are refit from the A20 forced slices.
- Runtime: the automatic OOC MCTS stack picks the A20 artifact when ascension ≥ 20, behind a flag that is off by
  default until the gates below pass. This is a new C++ change with tests and review.
- Known gaps in the #418 chain (`ctm-pathb/RUNBOOK-MAP.md` G1–G22) apply again. Some were fixed for #418; the rest
  are reviewed before the run.

**Stage 3: gates (pre-registered before Stage 2 runs).**
- Offline: candidate vs production at ASC 0 (clamped) on A20 TEST rows. Source-seed bootstrap of survival and HP NLL,
  with the same guards as the §412 runbook. PASS requires the survival NLL upper CI < 0 and |bias| ≤ 0.01.
- Live: rollout3 at A20 on the §419/§432 gold decisions (regret vs heuristic, as in §425/§426), A20 stack vs clamped
  production. Gate seeds 78500000+.
- From the #498 review (to settle before Stage 2 runs): the offline |bias| ≤ 0.01 bar applies per room class
  (normal, elite, boss) as well as overall, plus an HP-bias bound as in Stage 0; the live gate needs its seed count,
  effect size and decision rule written down; the runtime switch to the A20 model at ascension ≥ 20 needs a test that
  A0 play stays byte-identical.

## Costs (Inference)
- Stage 0: ~2 CPU-h.
- Stage 1: ~100 CPU-h with the deployed step. At 4 CPUs per cloud worker: 8 workers ~3 h, 16 ~1.5 h, 25 ~1 h wall.
- Stage 2: a day or two of GPU chain on Philipp's machine. The #418 chain took several sessions, mostly closing
  pipeline gaps.

## Not decided yet
- The worker count for Stage 1 (Philipp).
- G0: decided 2026-10-12 (FAILS at 19.7%; deployed step, see ledger §443).
