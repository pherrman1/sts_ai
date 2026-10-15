# Experimental DeepSets survival: Stage A

## Boundary

Awaiting independent user review of the exact draft-PR GitHub SHA. No reviewed
SHA is frozen and **no speed/gameplay experiment result exists**. Baseline:
`589a7a73c40e5b89e96df1ffec6a00b08c2ea9ba` (merged #217). The user authorized
reuse of the untouched app-managed worktree after updating it from main.
Only survival representation/head changes; no fitting, width-96, TEST inference,
support expansion, search/profile change, or default promotion.

## Preserved evidence

`parity.json`, `fixtures.jsonl`, `control.jsonl`, and `candidate.jsonl` are
byte-identical copies from `/tmp/deepset-online-stage-a-02/`. Originals remain
untouched. Original parity receipt SHA256:
`8fc4cc9f311c9266a47c1ce87b93e066bf9da4bcab889c11c5c938ace516f5f1`.
`handoff.json` records all original artifact hashes, the executable hash, and
the four implementation/test source hashes. Candidate native bytes remain at
`/tmp/deepset-online-stage-a-02/candidate.native`; checkpoint provenance is #217's
tracked sweep receipt and the external strong-WD checkpoint named below.

The receipt deliberately retains baseline `sourceSha` and `sourceDirty:true`:
Stage A was collected before commit, not on a clean or reviewed frozen SHA.
Source hashes bind the implementation to this handoff. Packaging changed no
implementation and did not rerun Stage A. The review candidate SHA is recorded
in the draft PR rather than self-referentially inside this commit.

## Observed results

- Exact checkpoint verified; 196 non-survival tensor byte strings unchanged.
- 24 non-TEST fixtures: 12 TRAIN/VALIDATION states and 12 unsupported HP-envelope
  variants. Support/reason decisions match; fallback consumes no planner RNG.
- Maximum Python/native candidate survival error `8.940696716308594e-08`, below
  `1e-4`. Other native maxHP, conditional HP, and downstream diagnostics match.
- Corpus and source-disjoint split hashes verified before fixture selection;
  `testInferenceRows=0`. Existing TEST-derived parity fixtures were not run.
- Release configure/build succeeded for native probe and `one_combat`.
  Existing Silver non-void-return and serial-LTO warnings were observed.
- Loader checks: 12 rejection cases PASS. Seed-free live startup: 16 cases PASS
  per arm. Its inherited label “qualified artifact” does not qualify DeepSets.
- `git diff --check` and worktree check PASS.

## Commands already executed

```bash
cmake --preset linux-gcc-release-ccache
cmake --build --preset linux-gcc-release-ccache-build --target combat_transition_runtime_probe one_combat -j 6
python3 tests/check_combat_transition_runtime_loader.py build/linux-gcc-release-ccache/combat_transition_runtime_probe
python3 tools/verify/ooc_mcts_live_startup.py build/linux-gcc-release-ccache/one_combat --artifact selfplay/models/combat_transition_near_full_except_smoke_v2.native
python3 tools/verify/ooc_mcts_live_startup.py build/linux-gcc-release-ccache/one_combat --artifact /tmp/deepset-online-stage-a-01/candidate.native
python3 -m tools.check_combat_transition_survival_deepset --control selfplay/models/combat_transition_near_full_except_smoke_v2.native --checkpoint /home/philippherrmann/sts_sweep/runs/survival-specific-deepset-sweep-20260917-final/strongWd/selected.pt --evidence docs/experiments/evidence/survival_deepset_sweep_2026-09-17.json --corpus /home/philippherrmann/sts_sweep/runs/combat-transition-runtime-25k/combat-transition-25k.jsonl --split /home/philippherrmann/sts_sweep/runs/combat-transition-model-v1/split_manifest.json --probe build/linux-gcc-release-ccache/combat_transition_runtime_probe --output /tmp/deepset-online-stage-a-02
python3 tools/agent/worktree.py check .
git diff --check
```

Startup uses `tools/seed_guard.sh` internally and drives no gameplay seeds.
Stage-A-01 and Stage-A-02 candidate native hashes match. Prior build logs remain
at `/tmp/deepset-online-configure.log` and `/tmp/deepset-online-build.log`.
Results above summarize observed command output, not newly created raw logs;
native JSONL output is preserved verbatim.

## Limits and next step

This is bounded integration evidence, not whole-domain support proof. All 12
unsupported variants test the HP envelope. Supported fixtures use `draws=0`, so
no supported sampled-trajectory/RNG parity was collected here. Control/Python
parity was not rerun; the comparison is candidate survival versus its exact
Python checkpoint and other native outputs across arms.

The loader follows V2 metadata/shape binding, not independent tensor-payload
hashing. Export and evidence bind actual bytes. The candidate retains the
control qualification metadata for the unchanged V2 support contract and adds
`experimentalSurvival.qualified=false`; no statistical qualification transfers.

No full local CTest, timing, 16-seed smoke, or 64-pair run was performed. Linux
GCC CI is the clean-repository gate; its status is recorded in the PR. Review
must pass before freezing a SHA and running Stage B. The gameplay gate requires
at least 10% lower median end-to-end CPU/run, then first 16 of a frozen 64-seed
cohort. Stage A supports neither STOP/PROMISING nor equivalence claims.

Knowledge impact: experimental runtime interface and evidence availability;
the maintained runtime page documents the opt-in selector. No baseline or
scientific conclusion changes.
