import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/agent/cline_guardrails.py"


def invoke(payload):
    result = subprocess.run([sys.executable, str(SCRIPT)], input=json.dumps(payload), text=True, capture_output=True, cwd=ROOT)
    if result.stderr:
        # Block diagnostics are intentionally on stderr; malformed stderr is not output protocol.
        assert result.returncode == 0
    value = json.loads(result.stdout)
    assert isinstance(value, dict)
    assert isinstance(value["cancel"], bool)
    assert set(value) <= {"cancel", "errorMessage", "contextModification"}
    return value


def pre(command, branch="feature"):
    return invoke({"hookName": "PreToolUse", "branch": branch, "preToolUse": {"toolName": "execute_command", "parameters": {"command": command}}})


class PreToolUseTests(unittest.TestCase):
    def test_allowed_commands(self):
        for command in (
            "git status --short", "git diff --check",
            "cmake --build --preset linux-gcc-debug-build",
            "ctest --preset linux-gcc-test",
            "tools/seed_guard.sh ./build/one_combat bestbench 1000 8 0",
            "tools/seed_guard.sh guard-only ./build/one_combat bestbench 1000 8 0",
        ):
            self.assertFalse(pre(command)["cancel"], command)
        self.assertFalse(invoke({"preToolUse": {"toolName": "read_file", "parameters": {"path": "x"}}, "branch": "main"})["cancel"])

    def test_blocked_commands(self):
        for command in (
            "git reset --hard HEAD~1", "git clean -fd", "git push --force",
            "git push --force-with-lease", "git push origin main", "rm -rf build",
            "pkill -f v_server.py", "sudo apt install x",
            "./build/one_combat bestbench 1000 8 0", "./build/one_combat",
            "python3 tools/verify/check_replay.py --self-test",
        ):
            self.assertTrue(pre(command)["cancel"], command)
        self.assertTrue(pre("git push", "main")["cancel"])

    def test_main_edit_block(self):
        payload = {"preToolUse": {"toolName": "write_to_file", "parameters": {"path": "x"}}, "branch": "main"}
        self.assertTrue(invoke(payload)["cancel"])


class TaskCompleteTests(unittest.TestCase):
    def test_clean_completion_shape(self):
        value = invoke({"hookName": "TaskComplete", "taskComplete": {"taskMetadata": {"changedFiles": []}}})
        self.assertFalse(value["cancel"])

    def test_cpp_completion_only_context(self):
        value = invoke({"hookName": "TaskComplete", "taskComplete": {"taskMetadata": {"changedFiles": ["CMakeLists.txt"]}}})
        self.assertFalse(value["cancel"])
        self.assertIn("focused local verification", value["contextModification"])
        self.assertIn("Linux GCC", value["contextModification"])

    def test_invalid_changed_python_cancels(self):
        path = ROOT / "tests/agent/_cline_invalid.py"
        path.write_text("def broken(:\n", encoding="utf-8")
        try:
            value = invoke({"hookName": "TaskComplete", "taskComplete": {"taskMetadata": {"changedFiles": [str(path.relative_to(ROOT))]}}})
            self.assertTrue(value["cancel"])
        finally:
            path.unlink()

    def test_invalid_changed_shell_cancels(self):
        path = ROOT / "tests/agent/_cline_invalid.sh"
        path.write_text("if true; then\n", encoding="utf-8")
        try:
            value = invoke({"hookName": "TaskComplete", "taskComplete": {"taskMetadata": {"changedFiles": [str(path.relative_to(ROOT))]}}})
            self.assertTrue(value["cancel"])
        finally:
            path.unlink()

    def test_docs_only_has_no_cpp_context(self):
        value = invoke({"hookName": "TaskComplete", "taskComplete": {"taskMetadata": {"changedFiles": ["README.md"]}}})
        self.assertFalse(value["cancel"])
        self.assertNotIn("contextModification", value)

    def test_diff_check_failure_cancels(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("cline_guardrails", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        completed = subprocess.CompletedProcess(["git"], 1, "bad.py:1: trailing whitespace.\n", "")
        with mock.patch.object(module.subprocess, "run", return_value=completed):
            value = module.handle_task_complete({"taskComplete": {"taskMetadata": {"changedFiles": []}}})
        self.assertTrue(value["cancel"])
        self.assertIn("git diff --check", value["errorMessage"])


if __name__ == "__main__":
    unittest.main()
