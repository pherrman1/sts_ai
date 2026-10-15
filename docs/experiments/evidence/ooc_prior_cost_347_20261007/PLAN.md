# #347 prior cost on the R seeds: root choice by Q and uniform prior (plan, 2026-10-07)

Status: frozen after independent pre-run review (clear, no blocking findings;
its non-blocking notes are folded in below). Philipp approved the
direction in the PR #429 thread (14:23 UTC, "yes lets go") after the §390
addendum showed that the leaf value prices chest relics near zero.

## Question and decision

§389 found that OOC MCTS follows the V4 policy prior over its own values: at
the treasure roots `OPEN_CHEST` had the higher mean Q at 8 of 11, and at 14 of
27 campfire roots another action had a higher mean Q than the chosen one. The
search used visit-count root selection with the 1,025-visit early-stop lock.
This run asks how much the prior costs on the same entries, with two existing
live knobs and no code change:

- **C** (frozen, ledger §390): OOC MCTS + chest rule, #417 `mcts` arm.
- **CQ**: C with `STS_OOC_MCTS_ROOT_SELECTION=q` (final root choice by mean
  Q over visited actions; PUCT tree selection unchanged; this also disables the
  early-stop lock, `OocMctsPlanner.cpp:232`, so every root spends 2,048 sims).
- **CU**: C with `STS_OOC_MCTS_PRIOR=uniform` at every node (roughly the limit
  of raising the prior temperature; not exactly, since the policy path also
  divides by primitive multiplicity and some C nodes are already uniform where
  V4 does not cover the screen). Visit-count selection and early stop as in C.

All three arms force every chest open, so the §389 chest-opening Q gap is not
tested here. What the knobs can change is relic pickup on reward screens
(where the §390 addendum found the leaf prices chest relics near zero, so CQ is
not expected to recover them), campfires and all other roots.

Primary comparisons, each on its own: CQ vs C and CU vs C, paired by run seed
and planner rep (shared planner seeds, `boss-prep-347-planner-v1`).

Decision rule (per comparison, fixed before the run, as §390):

- `SIGNAL`: net arm-only minus C-only wins >= +8 of 32 and at least 3 of 4
  seeds net positive. Next: a fresh-seed paired full-run pilot of that knob
  (53M range, size proposed then), after its own plan and review.
- `HARM`: net <= -8 and at least 3 of 4 seeds negative.
- Otherwise `INCONCLUSIVE`: that knob is not shown to matter at this scale.

If neither signals, the prior is not shown to be what costs MCTS these
entries, and a new prior over all OOC decisions has no support from this
evidence. Same caveats as §390: four failure-enriched seeds, one deterministic
OOC trajectory per arm and seed (effective n four entries per arm; the 8 reps
replicate only boss-combat planner noise), a pre-boss death moves the net by 8,
and trajectories diverge in RNG after the first changed decision. CQ has no
minimum-visit threshold: every root action gets at least one visit, so a
one-visit action with a lucky Q can be chosen. A CQ `HARM` can reflect noisy Q
rather than a correct prior.

## Baseline and provenance

- Branch `claude/ooc-divergence-347-x32yu5` (PR #429).
- Binary: the §390 diagnostic build `1911f044`, SHA-256
  `6fa4bf5c14a6bb3184707c75fd512276c99d169b1c356f64185452ad5ff51677`, so C is
  the frozen §390 rows and CQ/CU differ only in the exported knob. This build
  predates the keys-off filter (`824ff96`); MCTS can still take keys in all
  three arms. The decision trace does not record keys, so key pickups are not
  counted (a sapphire key taken looks like a relic left).
- Arm env: `arm_env.sh` at #417 ref `10e56bd8` (hash-checked), `mcts`, plus
  `STS_347_CHEST_RULE=1`, plus the spec's `mctsEnv`.
- Models, `STS_FAIR=1`, Ironclad A0, keys off, `STS_STOP_AFTER_ACT=3`,
  native flat exact 10,000 Silver per root, reuse cap 32768: exactly as §390.

## Implementation

None in C++. `selection.json` uses the §390 cf schema with one extra field
per spec, `mctsEnv`, which the binary ignores; `run.sh` (the §390 runner plus
one export) sets it after the arm env. `analyze.py` refuses a source whose
logged OOC MCTS config line does not show the arm's `prior` and
`root_selection`, whose chest rule did not fire at every chest without Cursed
Key, whose planner seeds differ from C, or whose binary SHA-256 or git SHA differs
from the §390 build.

## Run and cost

`run.sh BIN 6fa4bf5c14a6bb3184707c75fd512276c99d169b1c356f64185452ad5ff51677
1911f044f397edffa92361f59ecd78a9b34db87a OUT SEL` (absolute paths) over 8 sources on one 4-CPU
container, four workers. CU runs like C (~3.5 min per run reconstruction);
CQ spends the full 2,048 sims at every root, roughly 2x. Plus 8 boss replays
each. About 30 minutes. Then
`analyze.py OUT ../ooc_counterfactual_347_20261007/run --out report.json`.
Validity: every source `VALID` (control parity, repeats identical, budgets
spent), config and chest checks above.
