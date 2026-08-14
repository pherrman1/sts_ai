import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock


def load_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("cline_guardrails", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module

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
            "git clean -fx", "git clean -fdx",
            "git push --force-with-lease=main", "git push origin HEAD:main",
            "git push origin +HEAD:main", "git push origin HEAD:refs/heads/main",
            "git -C . reset --hard HEAD", "echo ok & rm -rf build",
            "echo ok\nrm -rf build", "bash -c 'rm -rf build'",
            "sh -c 'git reset --hard HEAD'",
        ):
            self.assertTrue(pre(command)["cancel"], command)
        self.assertTrue(pre("git push", "main")["cancel"])

    def test_serena_payloads_on_main(self):
        for tool in ("serena__replace_symbol_body", "serena__replace_content"):
            self.assertTrue(invoke({"preToolUse": {"toolName": tool, "parameters": {}}, "branch": "main"})["cancel"])
        self.assertFalse(invoke({"preToolUse": {"toolName": "serena__find_symbol", "parameters": {}}, "branch": "main"})["cancel"])
        self.assertTrue(invoke({"preToolUse": {"toolName": "mcp", "parameters": {"toolName": "serena__replace_symbol_body"}}, "branch": "main"})["cancel"])

    def test_main_edit_block(self):
        payload = {"preToolUse": {"toolName": "write_to_file", "parameters": {"path": "x"}}, "branch": "main"}
        self.assertTrue(invoke(payload)["cancel"])


class CompletionTests(unittest.TestCase):
    def test_completion_validation_is_pretooluse(self):
        path = ROOT / "tests/agent/_cline_invalid.py"
        path.write_text("def broken(:\n", encoding="utf-8")
        try:
            value = invoke({"hookName": "PreToolUse", "preToolUse": {"toolName": "attempt_completion", "parameters": {}}})
            self.assertTrue(value["cancel"])
        finally:
            path.unlink()

    def test_invalid_changed_shell_cancels_pretooluse(self):
        path = ROOT / "tests/agent/_cline_invalid.sh"
        path.write_text("if true; then\n", encoding="utf-8")
        try:
            value = invoke({"hookName": "PreToolUse", "preToolUse": {"toolName": "submit_and_exit", "parameters": {}}})
            self.assertTrue(value["cancel"])
        finally:
            path.unlink()

    def test_diff_check_failure_blocks_pretooluse(self):
        module = load_module()
        failed = subprocess.CompletedProcess(["git"], 1, "bad.py:1: trailing whitespace.\n", "")
        with mock.patch.object(module.subprocess, "run", return_value=failed):
            value = module.handle_pre_tool_use({"preToolUse": {"toolName": "attempt_completion", "parameters": {}}})
        self.assertTrue(value["cancel"])
        self.assertIn("git diff --check", value["errorMessage"])

    def test_task_start_baseline_and_committed_change(self):
        module = load_module()
        value = invoke({"hookName": "TaskStart", "taskId": "test-task"})
        self.assertFalse(value["cancel"])
        self.assertTrue(module.BASELINE_PATH.exists())
        self.assertIn("docs/knowledge-base/operations/agent-context-and-workflow.md", [str(p.relative_to(ROOT)) for p in module.changed_files("4d6aecd49fe12b5423d9ca4ef7201307b8c82709")])
        cleanup = invoke({"hookName": "TaskComplete", "taskComplete": {}})
        self.assertFalse(cleanup["cancel"])
        self.assertFalse(module.BASELINE_PATH.exists())

    def test_docs_only_and_cpp_completion_are_cheap(self):
        module = load_module()
        with mock.patch.object(module, "changed_files", return_value=[ROOT / "README.md"]):
            docs = module.handle_pre_tool_use({"preToolUse": {"toolName": "attempt_completion", "parameters": {}}})
        self.assertFalse(docs["cancel"])
        with mock.patch.object(module, "changed_files", return_value=[ROOT / "CMakeLists.txt"]):
            cpp = module.handle_pre_tool_use({"preToolUse": {"toolName": "submit_and_exit", "parameters": {}}})
        self.assertFalse(cpp["cancel"])
        self.assertIn("focused local verification", cpp["contextModification"])

    def test_task_complete_is_cleanup_only(self):
        value = invoke({"hookName": "TaskComplete", "taskComplete": {}})
        self.assertFalse(value["cancel"])
        self.assertNotIn("contextModification", value)


if __name__ == "__main__":
    unittest.main()
