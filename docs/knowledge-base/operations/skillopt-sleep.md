# SkillOpt-Sleep pilot

Last verified: 2026-08-31 against the current working tree.

## Purpose

Provide a small, on-demand pilot for proposing evidence-backed procedural
improvements to `.agents/skills/codex-implementation/SKILL.md`. SkillOpt is
preview software; proposals remain staged until independent repository
evaluation and human review pass.

## Current implementation

Use `microsoft/SkillOpt` pinned at commit
`db46cd9ae7ce12f1dbd73c945185816aa738751d`. Do not vendor, fork, copy, or add
it as a submodule. The example configuration is
`tools/agent/skillopt_sleep_config.example.json`; replace its absolute target
path only in a local ignored copy.

At this pin, `skillopt_sleep.config.load_config()` reads user configuration
from `~/.skillopt-sleep/config.json` (with YAML fallbacks when JSON is absent).
Create the reproducible pilot setup from the repository root:

```bash
git clone https://github.com/microsoft/SkillOpt.git .skillopt-sleep/SkillOpt
git -C .skillopt-sleep/SkillOpt checkout --detach db46cd9ae7ce12f1dbd73c945185816aa738751d
mkdir -p ~/.skillopt-sleep
cp tools/agent/skillopt_sleep_config.example.json ~/.skillopt-sleep/config.json
# Edit target_skill_path in ~/.skillopt-sleep/config.json to the absolute path
# of this worktree's .agents/skills/codex-implementation/SKILL.md.
```

Run the source-pinned engine from its checkout, using the Python module
entrypoint so Windows does not depend on shell-runner Python discovery:

```bash
cd .skillopt-sleep/SkillOpt
python -m skillopt_sleep status --project /ABSOLUTE/PATH/TO/sts_ai --json
python -m skillopt_sleep dry-run --project /ABSOLUTE/PATH/TO/sts_ai \
  --source codex --scope invoked --backend mock --max-sessions 5 --max-tasks 6 \
  --target-skill-path /ABSOLUTE/PATH/TO/sts_ai/.agents/skills/codex-implementation/SKILL.md \
  --json
```

Verify that the pin loaded the intended effective user configuration before a
run:

```bash
python - <<'PY'
from pathlib import Path
from skillopt_sleep.config import load_config

cfg = load_config()
target = Path("/ABSOLUTE/PATH/TO/sts_ai/.agents/skills/codex-implementation/SKILL.md").resolve()
assert cfg.transcript_source == "codex"
assert cfg.backend == "codex"
assert cfg.gate_mode == "on" and cfg.gate_no_regression is True
assert cfg.evolve_memory is False and cfg.evolve_skill is True
assert cfg.edit_budget == 1 and cfg.auto_adopt is False
assert cfg.recall_k == 0 and cfg.dream_factor == 0
assert Path(cfg.managed_skill_path()).resolve() == target
assert "staged diff outside that section must be rejected" in cfg.preferences
print("SkillOpt effective config: pilot constraints loaded")
PY
```

The pinned `plugins/run-sleep.sh` did not discover this host's Windows Python
3.13 installation when invoked through Git Bash (`need Python >= 3.10 (found
none)`). The `python -m skillopt_sleep` commands above work and are the
documented Windows path for this pilot.

The pilot is on demand:

```text
3–5 substantial Codex sessions
        ↓
harvest archived Codex sessions
        ↓
inspect and redact mined tasks
        ↓
mock dry-run
        ↓
real Codex-backed SkillOpt run
        ↓
staged skill proposal
        ↓
sts_ai evaluator comparison
        ↓
human review and normal PR
```

There is no cron, hook, session-end trigger, scheduler, or automatic adoption.
Never send unreviewed transcript-derived tasks to a provider-backed run. Keep
the complete staging area and evidence log under ignored local directories
because they can contain transcript-derived content. If useful archived Codex
sessions are unavailable, do not build a harvester: use SkillOpt's reviewed
task-file route or defer the real run.

## Configuration rationale

- `evolve_memory=false` prevents generic `CLAUDE.md` memory creation or edits.
- `edit_budget=1` makes each cycle one attributable procedural proposal.
- `gate_no_regression=true` rejects validation regressions.
- `test_fraction=0.17` supplies diagnostic evidence, not adoption authority.
- `auto_adopt=false` is mandatory for this pilot.
- `recall_k=0` avoids retrieval complexity initially.
- `dream_factor=0` leaves dream augmentation disabled.

The configuration preference asks SkillOpt to propose at most one edit inside
`## Learned guidance`; it is not a mechanical output sandbox. Human review
must reject any staged diff that changes content outside that section. The
tracked KB remains authoritative project truth, and staged changes to
`AGENTS.md`, the KB, or other skills are rejected.

## Independent evaluation

Follow the two-arm comparison in
[`coding-agent-evals.md`](../evaluation/coding-agent-evals.md). The evaluator
overlays each selected skill into a disposable candidate baseline, removes
hidden `evals/`, and grades repository outcomes independently. The existing
four tasks are only a no-regression smoke.

A proposal is adoptable only when SkillOpt internal validation accepted, the
`sts_ai` evaluator did not regress, human diff review passed, and the change
enters through the normal branch, draft PR, and CI workflow. No KB edit or
skill edit is automatic.

## Known limitations

The pilot does not establish that SkillOpt improves coding quality. Transcript
availability, official Codex integration behavior, provider cost, and the
representativeness of four evaluator tasks remain operational uncertainties.

## Relevant code

- `.agents/skills/codex-implementation/SKILL.md`
- `tools/agent/skillopt_sleep_config.example.json`
- `tools/agent/eval.py`
- `tests/agent/test_agent_eval.py`
- `docs/knowledge-base/evaluation/coding-agent-evals.md`
