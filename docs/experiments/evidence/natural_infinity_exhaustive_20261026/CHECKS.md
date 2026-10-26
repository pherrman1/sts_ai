# Local verification and review handoff

Scientific evidence commit: `c369705ee` (baseline
`8cce22b4d5d54733330e323b3065ca687fbcbfc5`). The subsequent metadata commit adds
this check record and the successful ledger dry-run only; it does not change
scripts, inputs, raw observations, interpretation or production code.

- `python3 tools/agent/worktree.py preflight .`: app-managed, detached initial
  HEAD, intended origin; external Git metadata writable.
- `python3 tools/agent/worktree.py check .`: PASS, pinned json/pybind11 correct.
- Remote-main verification before execution and publication: exact baseline
  `8cce22b4d5d54733330e323b3065ca687fbcbfc5` both times.
- `python3 docs/experiments/evidence/natural_infinity_exhaustive_20261026/verify.py`:
  PASS, raw output in verification.json. No game or oracle execution. It checks
  the unchanged historical source/binary/eight models, frozen inputs, raw
  archive/receipt hashes, full deterministic prefixes, all ordinary roots,
  all generated matrices/results, only the five original interventions and
  no fourth combat entry/completion. It compiles only the seed-free burden
  helper against historical headers.
- `python3 -m py_compile docs/experiments/evidence/natural_infinity_exhaustive_20261026/*.py`:
  PASS.
- Seed-free burden helper against the 14-card Shell Parasite deck: PASS,
  recurring mass 8 using the unchanged #863 definition.
- `git diff --cached --check` and baseline-to-candidate `git diff --check`:
  PASS. Changed-path audit: evidence folder, ledger, maintained research page
  only; no production/build/model changes.
- `python3 tools/repo_health.py --baseline 8cce22b4d5d54733330e323b3065ca687fbcbfc5 --json`:
  PASS, no hard failures or warnings; raw output in repo-health.json.
- `python3 tools/ledger_assign.py assign --dry-run --base origin/main`: PASS
  after the scientific evidence commit; `§TBD -> §686`. Placeholder remains
  unassigned until merge. The tool initially refused to run before commit,
  as required by its clean-tree precondition; no numbering was modified.

No full production configure/build/CTest, fresh oracle fixtures, training,
additional seed, adaptive bound, fourth combat, manual CI dispatch or merge.
The historical binary and adapter were reused by exact hash. Independent
implementation/scientific review is pending at the draft-PR handoff; no review
PASS or GitHub CI PASS is claimed by these local results.

Knowledge impact: experiment ledger plus maintained current-research status;
no production-default or model promotion. #844 and #863 were read only.
