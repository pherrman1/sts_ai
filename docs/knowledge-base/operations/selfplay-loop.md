# Self-play loop

Last verified: 2026-07-31 against commit `67320b3` and the current working tree.

## Purpose

Document the resumable self-play, retraining, and paired-gating implementation,
its checked-in snapshots, and the discrepancies that currently prevent a valid
launch or meta promotion.

## Current implementation

`selfplay/loop.sh` is the authoritative controller. It creates local buffer,
model, candidate, log, current, and gate directories; resumes from
`selfplay/state.env`; generates run/combat/policy/rest data; retrains due arms;
and performs adaptive paired gates.

Implemented arms are independent:

- meta: V_win and optional paired rest action model;
- combat value: candidate value with the loop's current policy;
- combat policy: candidate policy with the loop's current value.

If value and policy qualify together, policy promotion is deferred so it can be
tested against the new value baseline. This contradicts the stale script header
that describes whole-agent, all-or-nothing promotion
(`selfplay/loop.sh`, independent promotion block).

Runtime defaults include 1,000 runs/iteration, 400 live-policy simulations, 300
meta simulations, 1,000 teacher simulations, 600 gate simulations, two-iteration
meta/value/policy cadence, and a 500-seed adaptive cap. The checked-in
`selfplay/config.env` is only a partial snapshot: it records iteration-era
values but omits several current script variables such as `POLICY_SIMS` and
`VALUE_RETRAIN_EVERY`.

## Important data flow

1. On a true first run, the script copies initial win/value/policy artifacts
   into `selfplay/current/` and creates `state.env`/history.
2. Meta generation writes run outcomes; combat generation uses the stronger
   `POLICY_SIMS` teacher and aligned value/policy callbacks; a subset of meta
   runs can emit paired rest-vs-smith continuations.
3. Replay windows are assembled by arm. Meta, combat, rest, and policy have
   separate window sizes.
4. Trainers create candidates under `selfplay/cand/` and model history under
   `selfplay/models/`.
5. `run_gate_batch` invokes `./one_combat.elf bestbench` on common held-out
   seeds and appends per-seed CSVs.
6. `gate_stats` compares `floor + 100*WIN_WEIGHT*won` and calculates
   `mean ± GATE_Z*SE`.
7. Qualifying artifacts are copied through temporary names into
   `selfplay/current/`; state/history advance only after successful phases.
8. `selfplay/status.sh` reads snapshots, markers, and gate progress for a
   dashboard.

Resume markers store a target and collision-free next seed; interrupted CSVs
are counted by distinct seed and resumed beyond the observed maximum
(`selfplay/loop.sh::done_for_target`, `marker_next_seed`, `seed_stats`).

## Invariants and assumptions

- Candidate and baseline arms use common seeds and the same gate budget.
- Equality at the configured margin does not promote. The checked-in negative
  value margin can nevertheless qualify a sufficiently precise zero-delta
  value candidate. A hard-cap inconclusive candidate is rejected.
- Repeated adaptive looks use nominal normal-theory intervals without a
  sequential correction.
- Candidate validity requires arm-specific model loading and branch use.
- Generated buffers may be ignored, large, append/resume-safe, and expensive;
  absence from git is not authorization to delete them.
- `selfplay/config.env` and `state.env` describe snapshots, not universal
  defaults or proof of a running process.
- Exact PIDs are used when stopping the Python server; broad process patterns
  are unsafe.

## Blocking discrepancies

### Meta arm bypass

`FLOOR_POLICY_ENV`/`WIN_POLICY_ENV` do not set `STS_NATIVE_OOC=0`.
`start_server` launches the candidate V_win/rest models, but `one_combat`
defaults native OOC on and uses fixed `build/v_rich_trees.txt` and
`build/v_win_trees.txt`; native paired-rest queries return without using the
server. The current meta gate therefore does not demonstrate candidate use
(`selfplay/loop.sh::start_server`, `run_gate_batch`;
`apps/one_combat.cpp::main`, `vQueryRestCounterfactual`).

No meta gate or promotion should be treated as valid until startup/trace
evidence proves the candidate model owns each intended decision.

### Non-runnable checked-in snapshot

`selfplay/state.env` records iteration 10, seed offset 1008002, and 8002 runs,
but this checkout lacks:

- `selfplay/current/`, core buffer/candidate/model/log/gate directories;
- `./one_combat.elf`;
- initialization sources `build/v_combat_fair_trees.txt` and
  `build/policy_fair_trees_c.txt`.

Because `state.env` exists, the first-run copy branch is skipped. The snapshot
cannot resume without a deliberate bootstrap repair.

### Baseline cache provenance

The cache hashes `one_combat.elf` and current loop models, but native OOC uses
fixed tracked floor/win trees that are not included in the key. If server-backed
inference is restored, the key also omits `v_server.py` and Python dependency
versions (`selfplay/loop.sh::baseline_cache_key`). The script comment that
baseline outcomes are deterministic is not a verified invariant.

## Known limitations

- `VALUE_MARGIN=-0.5` is applied to every value candidate in the checked-in
  snapshot even though comments describe it as latency-specific; code does not
  enforce a latency condition.
- `GATE_Z=2.58` is called safe over repeated looks in a comment, but no
  multiplicity adjustment exists.
- `POLICY_WINDOW=1` is the checked-in local snapshot. Historical memory-failure
  thresholds were not reproduced in this workspace.
- The loop depends on Bash, Python training packages, a runnable
  `one_combat.elf`, and an inference server even when some native paths bypass
  it; these preconditions are not validated up front.
- There is no checked-in end-to-end test for bootstrap, resume, candidate-use,
  or atomic multi-arm promotion.

## Open questions

- Should meta gates disable native OOC or export/load arm-specific native trees?
- What exact bootstrap policy should apply when `state.env` exists but current
  models/directories do not?
- Should gate intervals use a sequentially valid method?
- Which artifact/runtime inputs must enter the baseline cache key?
- Should `VALUE_MARGIN` be conditional on measured latency evidence?

## Relevant code

- `selfplay/loop.sh::start_server`, `cenv_files`, `gate_stats`,
  `baseline_cache_key`, `run_gate_batch`
- `selfplay/status.sh`
- `selfplay/config.env`; `selfplay/state.env`; `selfplay/meta_mode.env`
- `apps/one_combat.cpp::main`, `bestBench`, `runFullRunOOC`
- `train_winrate.py`, `train_rest_cf.py`, `train_value_combat.py`,
  `train_policy.py`
- `EXPERIMENTS.md` entries 37–55
