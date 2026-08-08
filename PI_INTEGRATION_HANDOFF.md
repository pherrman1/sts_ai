# STS AI → Pi integration handoff

Date prepared: 2026-08-08

## Goal

Integrate the Pi coding-agent harness into `sts_ai` without losing the repository-specific safety, review, and experimental-discipline logic already implemented in `tools/ai_cycle.py`.

The migration is successful when Pi replaces OpenCode as the LLM/agent runtime while the existing STS-specific orchestration invariants remain deterministic and testable.

Do **not** delete or bypass `tools/ai_cycle.py` early. Migrate incrementally and keep the old OpenCode backend available until the Pi backend passes parity tests.

## Current repository facts to preserve

The repository already has:

- `AGENTS.md` as the authoritative project guidance for agents.
- `docs/knowledge-base/` for stable current technical knowledge.
- `EXPERIMENTS.md` for chronological experimental evidence.
- a decision log under `docs/knowledge-base/decision-log/`.
- `tools/ai_cycle.py`, currently the deterministic architect → implementer → reviewer orchestration layer.
- `tools/test_ai_cycle.py`, which should remain the primary regression suite for orchestration behavior.
- `tools/ai_inspect.py`, the restricted read-only artifact inspector.
- `.opencode/prompts/{architect,implementer,reviewer,reviewer-escalation}.md`.
- `opencode.json` with the current model routing.

Important constants already present in `tools/ai_cycle.py` include:

- `MAX_IMPLEMENTATION_RETRIES = 2`
- `MAX_REVIEW_ROUNDS = 2`
- `MAX_SOL_REVIEW_ROUNDS = 3`
- `MAX_EXPENSIVE_REPAIRS = 2`
- `MAX_CHEAP_TIMEOUT_SECONDS = 3600`
- `MAX_EXPENSIVE_TIMEOUT_SECONDS = 6 * 3600`
- `MAX_AUTOMATED_SEEDS = 128`

It also contains:

- known one_combat/Python seed-sweep argument positions;
- high-risk path/plan classification;
- protected workflow paths;
- candidate fingerprinting;
- clean-working-tree enforcement;
- verification allowlisting;
- cheap/expensive verification handling;
- escalation/recovery logic.

These rules are STS-specific policy. Pi must not replace them with prompt-only instructions.

## Desired architecture

```text
User
  |
  v
Pi interactive controller
  |
  +--------------------+
  |                    |
read-only subagents    normal interactive work
  |
  +--> investigator  (DeepSeek Flash)
  +--> architect     (DeepSeek Pro)
  +--> reviewer      (DeepSeek Flash)
  +--> reviewer-pro  (DeepSeek Pro/xhigh)
  +--> implementer   (DeepSeek Flash, writer)
  |
  v
tools/ai_cycle.py (during migration and initially after cutover)
  |
  +--> deterministic retry limits
  +--> protected workflow policy
  +--> verification execution
  +--> hard MAX_AUTOMATED_SEEDS=128
  +--> high-risk escalation
  +--> experiment/decision-log requirements
```

Long-term, generic orchestration code may be moved from `ai_cycle.py` into a Pi extension, but only after behavior is covered by tests and parity is demonstrated.

## Pi assumptions verified against current upstream

Pi:

- loads `AGENTS.md` automatically as a context file;
- auto-discovers project extensions in `.pi/extensions/`;
- auto-discovers prompt templates in `.pi/prompts/`;
- supports project-local subagent definitions in `.pi/agents/*.md` through the official reference subagent extension;
- does **not** load project agents through that subagent tool by default: calls must use `agentScope: "project"` or `"both"`;
- runs each reference subagent as a separate `pi --mode json -p --no-session` process;
- passes an agent Markdown `model:` value directly to Pi's `--model`;
- passes an agent Markdown `tools:` allowlist directly to Pi's `--tools`;
- supports model selectors with a provider prefix and optional thinking suffix, e.g. `deepseek/deepseek-v4-pro:high`;
- supports custom TypeScript extensions that can block `tool_call` events and register custom tools;
- has no built-in sandbox. Project trust is not a security sandbox.

Current direct DeepSeek IDs in Pi are:

- `deepseek/deepseek-v4-pro`
- `deepseek/deepseek-v4-flash`

Before relying on them, run:

```bash
pi update --models
pi --list-models deepseek
```

If the installed catalog differs, update only the `model:` lines in `.pi/agents/*.md`.

## Files supplied with this handoff

Copy the supplied starter files into the repository:

```text
.pi/
  agents/
    architect.md
    investigator.md
    implementer.md
    reviewer.md
    reviewer-pro.md
  extensions/
    sts-safety.ts
    sts-tools.ts
  prompts/
    sts-investigate.md
scripts/
  install_pi_subagent.sh
  check_pi_setup.sh
```

The official Pi subagent extension itself is intentionally **not reimplemented**. `scripts/install_pi_subagent.sh` vendors the upstream reference `index.ts` and `agents.ts` at a pinned Pi commit.

## Phase 1 — verify Pi and DeepSeek

Run from the repo root:

```bash
node --version
pi --version
pi update --models
pi --list-models deepseek
```

Node must satisfy the installed Pi package's requirement.

Verify the API:

```bash
export DEEPSEEK_API_KEY='sk-...'
pi --model deepseek/deepseek-v4-flash:high --tools read,grep,find,ls -p \
  "Read AGENTS.md and state the repository's maximum automated seed count."
```

Expected answer: 128.

Do not continue if DeepSeek tool use is broken.

## Phase 2 — install project Pi resources

Copy this starter kit into the repo and run:

```bash
bash scripts/install_pi_subagent.sh
bash scripts/check_pi_setup.sh
```

Then start Pi interactively from the repository root:

```bash
pi --model deepseek/deepseek-v4-flash:high
```

Approve/trust the project after reviewing `.pi/extensions/`.

Pi's trust mechanism enables project resources; it does not sandbox them.

## Phase 3 — validate the project agents

The official subagent reference only includes project-local `.pi/agents/*.md` when the subagent call explicitly uses:

```json
{"agentScope":"project"}
```

or:

```json
{"agentScope":"both"}
```

Test each agent from interactive Pi.

### Architect test

Ask the parent:

> Use the `architect` subagent with `agentScope: "project"` to explain one small current subsystem. Do not modify anything.

Success:

- project architect is found;
- model shown is DeepSeek Pro;
- agent has only `read`, `grep`, `find`, `ls`, `sts_git`, `sts_inspect`;
- no repository changes.

### Reviewer test

Make no changes and ask reviewer to review the empty diff.

Success:

- reviewer can obtain `git status` and `git diff` through `sts_git`;
- reviewer cannot invoke arbitrary Bash because `bash` is not in its tool allowlist.

### Implementer test

Use a disposable branch and a harmless comment-only task.

Success:

- implementer can edit;
- `git commit`, `git push`, destructive reset/clean/restore commands are blocked by `sts-safety.ts`;
- protected workflow files cannot be written/edited through Pi tools.

## Phase 4 — add a Pi backend to `tools/ai_cycle.py`

This is the core integration. Do this as a backend refactor, not a rewrite.

### Required design

Create a provider-neutral agent invocation abstraction inside or adjacent to `tools/ai_cycle.py`.

Conceptually:

```python
class AgentBackend:
    def run_architect(...): ...
    def run_implementer(...): ...
    def run_reviewer(...): ...
    def run_escalation_reviewer(...): ...
```

Retain the existing OpenCode implementation initially.

Add a Pi implementation that launches Pi non-interactively and parses JSONL:

```bash
pi --mode json -p --no-session --approve \
  --model <model> \
  --tools <allowlist> \
  --append-system-prompt <prompt-file> \
  "Task: ..."
```

Alternatively use Pi RPC mode if that materially simplifies lifecycle handling. Do not adopt RPC merely because it exists; JSON mode is acceptable if it preserves robust streaming, timeout, abort, and final-response parsing.

### Important: do not make `ai_cycle.py` depend on the reference subagent tool

`ai_cycle.py` should invoke Pi directly as an agent runtime. The reference subagent extension is for interactive Pi use.

This separation gives:

```text
interactive research -> Pi reference subagents
deterministic AI cycle -> Python orchestrator -> Pi child processes
```

Both use the same underlying Pi/DeepSeek runtime and the same prompts.

### Prompt reuse

Avoid duplicating prompt bodies.

Prefer one authoritative set. A good migration is:

1. Move/reuse the current prompt text into `.pi/agents/*.md`.
2. Add a small helper that extracts the Markdown body after YAML frontmatter for `ai_cycle.py`, or keep generated prompt-body files.
3. During migration, compare the effective prompt text to the current `.opencode/prompts/*.md`.

Do not allow the Pi and OpenCode paths to silently diverge semantically.

### Model routing

Initial routing should match current cost strategy:

```text
architect      DeepSeek V4 Pro     high
investigator   DeepSeek V4 Flash   high
implementer    DeepSeek V4 Flash   high
reviewer       DeepSeek V4 Flash   high
reviewer-pro   DeepSeek V4 Pro     xhigh/max-equivalent
```

If `ai_cycle.py` currently has a separate stronger/SOL escalation path beyond these roles, preserve it. Inspect the full current implementation rather than assuming the supplied starter agents represent every escalation branch.

### Tool/permission behavior for deterministic cycle

Architect/reviewer child Pi processes should run without arbitrary Bash.

Use:

```text
read,grep,find,ls,sts_git,sts_inspect
```

If project extensions are not reliably loaded in noninteractive child processes, do not weaken this to arbitrary Bash. Instead:

- run a small trusted Pi extension explicitly with `-e`, or
- expose the read-only inspection operations another deterministic way.

Implementer may use normal tools, but destructive commands remain denied.

## Phase 5 — preserve the deterministic STS verification layer

Do **not** delegate the following decisions to the parent LLM or a Pi prompt:

- whether the working tree is clean enough to start;
- whether a verification command is allowed;
- whether a command is cheap or expensive when the architect output is malformed;
- seed-count extraction and the hard 128 cap;
- maximum repair/review loops;
- candidate fingerprints;
- protected workflow restoration/checking;
- high-risk classification and mandatory escalation;
- whether required checks passed;
- whether an experiment log/decision log update is required.

The current Python logic is authoritative until an equivalent deterministic implementation is proven by tests.

The supplied `sts-safety.ts` is defense in depth for interactive Pi. It is **not** a replacement for `MAX_AUTOMATED_SEEDS` in `ai_cycle.py`.

## Phase 6 — tests

Extend `tools/test_ai_cycle.py`.

At minimum add tests for:

1. backend selection: OpenCode vs Pi;
2. exact Pi argv construction for each role;
3. model routing;
4. tool allowlists;
5. timeout propagation;
6. non-zero Pi exit handling;
7. malformed JSONL handling;
8. final assistant-response extraction;
9. retry behavior;
10. cheap reviewer FIX → repair → rereview;
11. high-risk PASS → escalation;
12. rejected-session escalation/recovery behavior;
13. hard seed cap still blocks >128 before execution;
14. dirty-tree refusal still happens before any LLM invocation;
15. protected workflow paths remain protected;
16. OpenCode backend still works during migration.

Use a fake `pi` executable/process fixture. Tests must not call real APIs.

## Phase 7 — end-to-end bake-off

Run the same harmless task through both backends.

Example:

> Inspect `check_vwin_calibration.py` and improve one misleading or incomplete explanatory comment if one clearly exists. Do not change behavior. If no such change is justified, make no code change.

Compare:

- resulting diff;
- architect plan quality;
- review result;
- retries;
- ELI5 output;
- API cost;
- runtime;
- repository cleanliness.

Then use a bounded real semantic task.

Do not flip the default backend until:

- tests pass;
- one no-op/comment task passes;
- one real code task passes;
- no seed/safety invariant regresses.

## Phase 8 — make Pi the default, keep rollback

Once parity is demonstrated:

- make Pi the default backend;
- retain `--backend opencode` or equivalent for a temporary rollback period;
- document the backend selection in the knowledge base;
- append a decision-log entry explaining the migration and why Pi was selected;
- update any process/tooling documentation required by `AGENTS.md`.

Do not delete `.opencode/` or OpenCode support in the same commit that flips the default.

Delete legacy support only in a later, separately reviewed cleanup.

## Phase 9 — optional second-generation improvements

Only after the Pi backend is stable:

### A. Typed STS tools

Add custom tools such as:

```text
sts_build
sts_verify
sts_paired_eval
sts_record_experiment
```

`sts_paired_eval` should validate a schema with `seeds <= 128` before launching anything.

This is preferable to letting an LLM compose raw benchmark shell commands.

### B. Deterministic native `/sts-cycle`

Eventually a Pi extension may implement the workflow state machine itself:

```text
clean tree
  -> architect
  -> implementer
  -> deterministic verification
  -> reviewer
  -> repair loop if needed
  -> high-risk escalation if needed
  -> bounded paired evaluation if required
  -> experiment/decision log
```

Do not move this logic out of Python until its behavior is covered by equivalent tests.

### C. Parallel read-only investigation

Use `investigator` subagents in parallel for questions such as:

- training/inference parity;
- offline/online distribution shift;
- actual online model consumption;
- search/RNG semantics;
- prior experiment evidence.

Use many readers, one writer.

Do not add parallel implementers sharing one working tree. If parallel writers are ever introduced, give each a separate Git worktree and explicit resource limits.

## Acceptance criteria for the full migration

The integration is done when all of the following hold:

- Pi and direct DeepSeek V4 Pro/Flash work with tool calls.
- `AGENTS.md` is loaded and remains authoritative.
- project-local `.pi/agents` are discoverable through explicit project scope.
- architect/reviewer roles cannot use arbitrary Bash.
- implementer cannot commit/push/reset/clean/restore through Pi's Bash tool.
- protected workflow files are blocked interactively.
- `tools/ai_cycle.py` can execute all roles through Pi.
- existing retry/review/escalation semantics are preserved.
- `MAX_AUTOMATED_SEEDS=128` remains enforced deterministically before execution.
- tests cover the Pi backend without API calls.
- dirty-tree handling remains correct.
- failed/malformed Pi processes fail safely.
- ELI5 summaries remain available.
- required KB/experiment/decision logging rules remain unchanged.
- OpenCode rollback remains possible until a later cleanup.
- one harmless and one real end-to-end task pass under Pi.

## Commands for the human after implementation

```bash
# Refresh/check model catalog
pi update --models
pi --list-models deepseek

# Inspect discovered project resources interactively
pi --model deepseek/deepseek-v4-flash:high

# Run repository orchestration tests
python3 -m pytest tools/test_ai_cycle.py -q

# Inspect final diff
git status
git diff --check
git diff
```

## Instructions to the CLI coding agent receiving this handoff

1. Read `AGENTS.md` first.
2. Read the current `tools/ai_cycle.py`, `tools/test_ai_cycle.py`, `opencode.json`, and all `.opencode/prompts/*.md`; this handoff is not a substitute for current code.
3. Read Pi's current documentation/reference extension code when implementing Pi-specific APIs.
4. Implement incrementally and retain the OpenCode backend.
5. Reuse the supplied `.pi` starter files where compatible, but correct them if current Pi APIs require it.
6. Do not weaken any current STS safety/evaluation rule merely to make Pi integration easier.
7. Do not run large seed evaluations as part of integration.
8. Run focused tests and report exact deviations from this handoff.
9. Append the required repository decision-log/knowledge-base updates once the tooling decision becomes effective.
