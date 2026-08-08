#!/usr/bin/env python3
"""API-free regression tests for the STS-local Pi subagent lifecycle guard.

These tests intentionally do not launch Pi or call an LLM.  They verify the
source-level lifecycle contract in `.pi/extensions/subagent/index.ts` that
prevents a completed subagent from leaving the parent tool call pending forever.

The production bug this protects against was:

    final assistant message
        -> agent_end
        -> child/stdio never emits Node "close"
        -> runSingleAgent() Promise never resolves
        -> parent Pi remains on "Working..." forever

Run from anywhere inside the repository:

    python3 tools/test_pi_subagent_lifecycle.py
"""

from __future__ import annotations

import ast
import re
import subprocess
import unittest
from pathlib import Path


def repo_root() -> Path:
    # Resolve relative to this test file, not the caller's shell directory, so
    # `python3 /path/to/repo/tools/test_pi_subagent_lifecycle.py` works too.
    start = Path(__file__).resolve().parent
    result = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        cwd=start,
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return Path(result.stdout.strip()).resolve()


ROOT = repo_root()
INDEX = ROOT / ".pi" / "extensions" / "subagent" / "index.ts"


def source() -> str:
    return INDEX.read_text(encoding="utf-8")


def function_body(text: str, name: str) -> str:
    """Return a best-effort balanced-brace body for a named TS function."""
    patterns = [
        rf"function\s+{re.escape(name)}\s*\([^)]*\)[^{{]*\{{",
        rf"const\s+{re.escape(name)}\s*=\s*\([^)]*\)\s*=>\s*\{{",
    ]
    match = None
    for pattern in patterns:
        match = re.search(pattern, text, re.S)
        if match:
            break
    if not match:
        raise AssertionError(f"Could not locate function {name!r}")

    brace = text.find("{", match.start())
    depth = 0
    in_string: str | None = None
    escaped = False
    i = brace
    while i < len(text):
        ch = text[i]

        if in_string is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == in_string:
                in_string = None
            i += 1
            continue

        if ch in {"'", '"', "`"}:
            in_string = ch
            i += 1
            continue

        if text.startswith("//", i):
            end = text.find("\n", i)
            if end == -1:
                return text[brace + 1 :]
            i = end + 1
            continue

        if text.startswith("/*", i):
            end = text.find("*/", i + 2)
            if end == -1:
                raise AssertionError(f"Unterminated comment while parsing {name!r}")
            i = end + 2
            continue

        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[brace + 1 : i]
        i += 1

    raise AssertionError(f"Unbalanced function body for {name!r}")


def const_number(text: str, name: str) -> int:
    """Evaluate a numeric TS const expression using a restricted Python AST."""
    match = re.search(
        rf"const\s+{re.escape(name)}\s*=\s*([^;]+);",
        text,
    )
    if not match:
        raise AssertionError(f"Missing numeric constant {name}")

    expr = match.group(1).replace("_", "").strip()
    tree = ast.parse(expr, mode="eval")

    def eval_node(node: ast.AST) -> int:
        if isinstance(node, ast.Expression):
            return eval_node(node.body)
        if isinstance(node, ast.Constant) and isinstance(node.value, int):
            return node.value
        if isinstance(node, ast.BinOp) and isinstance(node.op, (ast.Mult, ast.Add, ast.Sub)):
            left = eval_node(node.left)
            right = eval_node(node.right)
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Add):
                return left + right
            return left - right
        raise AssertionError(f"Unsafe/unsupported numeric expression for {name}: {expr}")

    return eval_node(tree)


class LifecycleGuardContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if not INDEX.is_file():
            raise AssertionError(f"Missing subagent extension: {INDEX}")
        cls.text = source()

    def test_local_fork_and_lifecycle_markers_present(self) -> None:
        self.assertIn("STS-LOCAL FORK", self.text)
        self.assertIn("STS-SUBAGENT-LIFECYCLE-GUARD", self.text)

    def test_live_subagent_starts_with_running_exit_code(self) -> None:
        body = function_body(self.text, "runSingleAgent")
        self.assertRegex(
            body,
            r"const\s+currentResult\s*:\s*SingleResult\s*=\s*\{[\s\S]*?exitCode\s*:\s*-1\s*,",
        )

    def test_parallel_status_uses_single_running_predicate(self) -> None:
        self.assertIn("function isRunningResult", self.text)
        self.assertRegex(
            self.text,
            r"const\s+running\s*=\s*allResults\.filter\(isRunningResult\)\.length\s*;",
        )

    def test_guard_timeouts_are_positive_and_bounded(self) -> None:
        end_grace = const_number(self.text, "AGENT_END_CLOSE_GRACE_MS")
        termination_grace = const_number(self.text, "CHILD_TERMINATION_GRACE_MS")
        hard_timeout = const_number(self.text, "SUBAGENT_HARD_TIMEOUT_MS")

        self.assertGreater(end_grace, 0)
        self.assertGreater(termination_grace, 0)
        self.assertGreater(hard_timeout, end_grace + termination_grace)
        # Keep the safety net bounded to something operationally reasonable.
        self.assertLessEqual(hard_timeout, 60 * 60 * 1000)

    def test_agent_end_starts_bounded_shutdown_watchdog(self) -> None:
        body = function_body(self.text, "runSingleAgent")
        agent_end = re.search(
            r'if\s*\(event\.type\s*===\s*"agent_end"\)\s*\{([\s\S]*?)\n\s*\}',
            body,
        )
        self.assertIsNotNone(agent_end, "Missing agent_end lifecycle handler")
        # Search a wider slice because nested braces make regex body matching conservative.
        start = body.find('if (event.type === "agent_end")')
        window = body[start : start + 2600]
        self.assertIn("agentEndTimer = setTimeout", window)
        self.assertIn('proc.kill("SIGTERM")', window)
        self.assertIn("terminationTimer = setTimeout", window)
        self.assertIn('proc.kill("SIGKILL")', window)
        self.assertIn("finish(", window)

    def test_agent_end_requires_captured_final_assistant_message_for_success(self) -> None:
        start = self.text.find('if (event.type === "agent_end")')
        self.assertNotEqual(start, -1)
        window = self.text[start : start + 2600]
        self.assertIn("sawFinalAssistantMessage", window)
        self.assertIn("Subagent emitted agent_end without a final assistant message.", window)
        self.assertRegex(window, r"forcedExitCode\s*=\s*1")
        self.assertRegex(window, r"forcedExitCode\s*=\s*0")

    def test_final_assistant_detection_excludes_tool_use_turns(self) -> None:
        self.assertIn("hasFinalText", self.text)
        self.assertIn("hasToolCall", self.text)
        self.assertRegex(
            self.text,
            r"if\s*\(hasFinalText\s*&&\s*!hasToolCall\)\s+sawFinalAssistantMessage\s*=\s*true",
        )

    def test_completion_is_idempotent(self) -> None:
        body = function_body(self.text, "finish")
        self.assertRegex(body, r"if\s*\(settled\)\s*return\s*;")
        self.assertRegex(body, r"settled\s*=\s*true\s*;")
        self.assertIn("cleanupLifecycle()", body)
        self.assertIn("resolve(code)", body)

    def test_close_and_error_both_settle_through_finish(self) -> None:
        self.assertRegex(
            self.text,
            r'proc\.on\("close",\s*\(code\)\s*=>\s*\{[\s\S]*?finish\(forcedExitCode\s*\?\?\s*code\s*\?\?\s*0\)',
        )
        self.assertRegex(
            self.text,
            r'proc\.on\("error",\s*\(error\)\s*=>\s*\{[\s\S]*?finish\(1\)',
        )

    def test_hard_timeout_cannot_leave_parent_pending_forever(self) -> None:
        self.assertRegex(
            self.text,
            r"hardTimeoutTimer\s*=\s*setTimeout\(\(\)\s*=>\s*\{[\s\S]*?terminateAndFinish\(",
        )
        self.assertIn("SUBAGENT_HARD_TIMEOUT_MS", self.text)
        self.assertIn("Subagent exceeded hard timeout", self.text)

    def test_abort_uses_same_bounded_termination_path(self) -> None:
        self.assertRegex(
            self.text,
            r"abortHandler\s*=\s*\(\)\s*=>\s*\{[\s\S]*?wasAborted\s*=\s*true[\s\S]*?terminateAndFinish\(1\)",
        )

    def test_cleanup_removes_abort_listener_and_all_timers(self) -> None:
        body = function_body(self.text, "cleanupLifecycle")
        self.assertIn("clearTimer(agentEndTimer)", body)
        self.assertIn("clearTimer(terminationTimer)", body)
        self.assertIn("clearTimer(hardTimeoutTimer)", body)
        self.assertIn('signal.removeEventListener("abort", abortHandler)', body)

    def test_no_legacy_proc_killed_guard(self) -> None:
        # `ChildProcess.killed` means kill() was called, not that the OS process
        # has actually exited.  Lifecycle decisions must use exitCode/signalCode.
        self.assertNotIn("proc.killed", self.text)
        self.assertIn("proc.exitCode === null", self.text)
        self.assertIn("proc.signalCode === null", self.text)


if __name__ == "__main__":
    unittest.main(verbosity=2)