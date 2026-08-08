# Handoff: Add a deterministic fast path to `tools/ai_cycle.py`

## Goal

Reduce latency and API cost for genuinely trivial/non-behavioral tasks without weakening the full STS research workflow.

The current orchestrator remains authoritative for:
- clean-tree checks;
- protected workflow paths;
- verification command allowlisting;
- retry limits;
- candidate fingerprints;
- hard automated seed cap (`MAX_AUTOMATED_SEEDS = 128`);
- reviewer validation;
- high-risk escalation for semantic/research-sensitive changes;
- recovery behavior.

This change adds a **narrow deterministic fast path**, not a second autonomous workflow.

## Important design principle

Retry/review counts are maximums, never targets.

Desired behavior:

```text
TRIVIAL
  deterministic classification
  -> Flash implementer
  -> cheap deterministic verification
  -> Flash reviewer
  -> PASS => accepted
  -> no architect, no Pro escalation

NORMAL
  -> Pro architect
  -> Flash implementer
  -> verification
  -> Flash reviewer
  -> PASS => accepted unless deterministic escalation rules require Pro

HIGH RISK
  -> full normal flow
  -> mandatory Pro escalation when required
```

If classification is uncertain, use NORMAL.

---

# 1. Task-side fast-path eligibility

Add a deterministic function such as:

```python
def classify_fast_path_task(task: str) -> tuple[bool, list[str]]:
    ...
```

Fast path should be deliberately narrow.

A task is only a fast-path candidate when its wording clearly requests a non-behavioral change, for example:
- comment / explanatory comment;
- docstring;
- typo / spelling / grammar;
- wording-only correction;
- documentation-only edit;
- formatting-only edit;

AND, for source-code comment/docstring tasks, the task explicitly constrains behavior, e.g.:
- "do not change behavior";
- "no behavior change";
- equivalent clear wording.

Do NOT classify as trivial merely because the task is short.

Immediately reject fast-path classification if the request includes a semantic operation such as:
- implement/add/remove behavior;
- bug fix where behavior changes;
- refactor/restructure;
- model/search/training/inference logic change;
- RNG/fairness/evaluation methodology change;
- schema/interface/build-system/configuration change;
- generated/model artifact change.

Do not rely on an LLM to classify the task.

Persist the classification and reasons in the session, e.g.:

```text
.ai/<session>/task-classification.json
```

Example:

```json
{
  "class": "TRIVIAL_CANDIDATE",
  "reasons": [
    "task explicitly requests explanatory-comment change",
    "task explicitly says do not change behavior"
  ]
}
```

---

# 2. Deterministic trivial plan

For a fast-path candidate, skip the Pro architect and create a small deterministic plan file compatible with the existing implementer/reviewer interfaces.

Do not change the JSON plan schema if avoidable.

The plan should say, in substance:

- implement only the exact requested non-behavioral edit;
- do not alter executable semantics;
- no opportunistic cleanup;
- if satisfying the request requires behavior changes, make no change and report that;
- inspect only the relevant local context;
- verification is cheap only.

Verification for this deterministic plan should include at minimum:

```bash
git diff --check
```

Use the existing verification command representation and validation path.

For documentation-only changes, use only existing cheap documentation checks that are already deterministic and available; do not invent expensive checks.

Do not run game-seed benchmarks in the fast path.

Print something clear:

```text
===== FAST PATH CANDIDATE =====
Reason: explicit non-behavioral comment-only task
Architect skipped.
```

---

# 3. Post-implementation diff confirmation

Fast-path task wording is not sufficient. Confirm the actual diff before continuing as trivial.

Add a deterministic function such as:

```python
def confirm_trivial_diff() -> tuple[bool, list[str]]:
    ...
```

The fast path may continue only when ALL are true:

- at most 2 changed files;
- at most 50 changed lines (or similarly conservative small limit);
- no protected workflow paths;
- no model/generated binary artifacts;
- no CMake/build/schema/config/interface changes;
- no new executable source logic;
- no deletions/additions that cannot confidently be classified as comments/whitespace in source files;
- documentation files may contain normal prose changes;
- source-code changes must be conservatively recognizable as comment/docstring/whitespace-only.

For source files, it is acceptable to support a conservative set of obvious comment forms:
- `# ...`
- `// ...`
- `/* ... */`
- leading `*` inside block comments
- blank/whitespace-only lines

Do not attempt clever semantic parsing for arbitrary languages in this first version.

If the diff cannot be confidently proven trivial, do **not** silently bless it.

Preferred safe behavior:

```text
===== FAST PATH ABORTED =====
The resulting diff is not confidently non-behavioral.
No acceptance decision was made.
Rerun the task through the normal cycle.
```

Return a distinct nonzero result or normal rejection code as appropriate.

Do not automatically restore user changes unless the existing orchestrator already has an established safe mechanism for that.

Persist the post-diff classification and reasons.

---

# 4. Escalation semantics

Modify high-risk escalation so **path names alone do not force Pro escalation for a confirmed trivial diff**.

Currently high-risk paths/concepts are useful for semantic changes, but a comment in a VNet/Searcher file should not be treated like a VNet/Searcher behavior change.

Conceptually:

```python
should_escalate_to_sol(
    ...,
    confirmed_trivial=False,
)
```

When `confirmed_trivial` is true, ignore escalation reasons that arise only from:
- a high-risk path name;
- high-risk terms in the deterministic trivial plan.

BUT do NOT suppress escalation/failure for strong evidence such as:
- required verification failure earlier in the session;
- reviewer CRITICAL issue;
- reviewer has >=2 MAJOR issues;
- reviewer uncertainty HIGH;
- diff no longer satisfies trivial constraints;
- protected/control-plane changes;
- any other existing explicit safety failure.

A confirmed trivial task should normally never reach Pro escalation after a clean Flash PASS.

---

# 5. Reviewer behavior

Keep the Flash reviewer.

Do not skip semantic review entirely.

For a trivial fast-path review, reviewer inputs should still include:
- original task;
- deterministic plan;
- independent verification report;
- actual diff/repository state.

The reviewer must be told that the acceptance question is specifically:

> Did this remain a non-behavioral change and satisfy the requested wording/documentation correction without collateral modifications?

A PASS should accept immediately unless a retained hard escalation rule fires.

One review round is enough on PASS.

If reviewer returns FIX:
- use the existing fix/reverify/rereview machinery;
- never perform an extra review just because a configured maximum exists.

---

# 6. No-op behavior

A trivial task may legitimately produce no diff, especially requests such as:

> improve one misleading comment if one clearly exists; otherwise make no change.

Handle this cleanly.

If implementer reports no justified change and the working tree remains unchanged:
- do not fabricate a change;
- run only the minimal deterministic acceptance checks needed;
- reviewer may confirm that no change was justified if the current workflow supports this;
- avoid Pro escalation.

Do not reject solely because the diff is empty.

---

# 7. CLI / session visibility

At cycle start, print the selected policy:

```text
Task class: TRIVIAL_CANDIDATE
Workflow: implementer -> cheap verification -> reviewer
```

or:

```text
Task class: NORMAL
Workflow: architect -> implementer -> verification -> reviewer -> conditional escalation
```

After implementation:

```text
Fast-path diff confirmation: PASS
1 file, 2 changed lines, comments only
```

or the reason for fallback/rejection.

Store the decision in session artifacts so later debugging can explain why Pro was or was not called.

---

# 8. Tests

Extend `tools/test_ai_cycle.py`. No real API calls.

Add deterministic unit/integration tests covering at least:

## Classification

1. explicit comment + "do not change behavior" => candidate
2. typo in README/docs => candidate
3. short bug-fix request => NORMAL
4. "refactor this function, no behavior change" => NORMAL in first conservative version
5. VNet comment-only wording task => candidate despite the word VNet
6. RNG/search semantic task => NORMAL/HIGH-RISK, never trivial

## Diff confirmation

7. one-line Python `#` comment replacement => confirmed trivial
8. C++ `//` comment replacement => confirmed trivial
9. Markdown prose edit => confirmed trivial
10. source expression change => not trivial
11. comment + source expression change => not trivial
12. >2 files => not trivial
13. >configured trivial line limit => not trivial
14. protected workflow file => not trivial
15. build/config/schema file => not trivial
16. empty diff for "if justified, otherwise no change" => allowed/no-op

## Orchestration

17. trivial candidate skips architect
18. trivial candidate calls Flash implementer
19. trivial confirmed diff runs cheap verification
20. trivial PASS uses exactly one reviewer call
21. trivial PASS makes zero architect/Pro-escalation calls
22. trivial reviewer FIX uses existing repair path
23. failed required verification still blocks acceptance
24. non-trivial diff after candidate does not get accepted as fast path
25. normal task still runs architect
26. high-risk semantic task still escalates exactly as before
27. OpenCode rollback behavior remains unchanged
28. Pi backend behavior remains unchanged except role calls intentionally skipped by fast path
29. hard 128-seed cap unchanged
30. dirty-tree check still happens before any model call
31. protected workflow restoration/checks unchanged
32. recovery/continue-rejected behavior unchanged

Also run every pre-existing test.

---

# 9. Documentation

Update:
- `docs/knowledge-base/operations/ai-cycle.md`
- relevant decision-log entry for the new risk-proportional workflow

Document:
- fast path is deterministic;
- it is intentionally narrow;
- uncertainty falls back to NORMAL;
- Flash review is retained;
- path-based high-risk escalation is suppressed only for a post-diff-confirmed non-behavioral change;
- hard safety/verification rules remain authoritative;
- `MAX_AUTOMATED_SEEDS = 128` is unchanged.

If `AGENTS.md` describes the orchestration policy, update it minimally.

---

# 10. Non-goals

Do not:
- remove the architect from normal tasks;
- remove Flash review;
- weaken verification allowlisting;
- weaken seed parsing/caps;
- reduce reviewer severity handling;
- change model routing for normal/high-risk tasks;
- remove OpenCode rollback;
- rewrite `ai_cycle.py`;
- move orchestration into Pi;
- add automatic commits;
- run game benchmarks as part of this tooling change.

---

# Expected user-visible result

For:

```text
Inspect check_vwin_calibration.py and improve one misleading or incomplete
explanatory comment if one clearly exists. Do not change behavior. If no such
change is justified, make no code change.
```

Expected:

```text
===== FAST PATH CANDIDATE =====
Architect skipped.

===== IMPLEMENTER · DeepSeek V4 Flash =====
...

Fast-path diff confirmation: PASS
1 file, 2 changed lines, comments only

===== VERIFY =====
git diff --check
PASS

===== REVIEWER · DeepSeek V4 Flash =====
PASS

===== ACCEPTED =====
Implementation rounds: 1
Review rounds: 1
Architect calls: 0
Pro escalation calls: 0
```

For a semantic Searcher/VNet/RNG/training/evaluation change, behavior must remain the existing full workflow.

---

# Completion report

Report:
1. exact classification rules;
2. exact post-diff rules;
3. how ambiguous cases behave;
4. changes to escalation logic;
5. model calls for trivial vs normal vs high-risk tasks;
6. tests added and complete test-suite result;
7. `git diff --check`;
8. any deviations;
9. ELI5 summary.

Do not run real APIs or game-seed benchmarks for this implementation.
