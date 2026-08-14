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
            "sh -c 'git reset --hard HEAD'", "zsh -c 'rm -rf build'",
            "git push origin +HEAD:feature",
        ):
            self.assertTrue(pre(command)["cancel"], command)
        self.assertTrue(pre("git push", "main")["cancel"])

    def test_serena_payloads_on_main(self):
        for tool in ("serena__replace_symbol_body", "serena__replace_content"):
            self.assertTrue(invoke({"preToolUse": {"toolName": tool, "parameters": {}}, "branch": "main"})["cancel"])
        self.assertFalse(invoke({"preToolUse": {"toolName": "serena__find_symbol", "parameters": {}}, "branch": "main"})["cancel"])
        for parameters in (
            {"serverName": "serena", "toolName": "replace_symbol_body"},
            {"server_name": "serena", "tool_name": "replace_symbol_body"},
        ):
            self.assertTrue(invoke({"preToolUse": {"toolName": "use_mcp_tool", "parameters": parameters}, "branch": "main"})["cancel"])
        self.assertFalse(invoke({"preToolUse": {"toolName": "use_mcp_tool", "parameters": {"serverName": "serena", "toolName": "find_symbol"}}, "branch": "main"})["cancel"])

    def test_main_edit_block(self):
        payload = {"preToolUse": {"toolName": "write_to_file", "parameters": {"path": "x"}}, "branch": "main"}
        self.assertTrue(invoke(payload)["cancel"])

    def test_current_sdk_run_commands_payloads(self):
        blocked = (
            {"commands": json.dumps(["git reset --hard HEAD"])},
            {"commands": json.dumps(["git push --force"])},
            {"commands": json.dumps(["rm -rf build"])},
            {"commands": json.dumps([{"command": "git", "args": ["reset", "--hard", "HEAD"]}])},
            {"commands": json.dumps([{"command": "./build/one_combat", "args": []}])},
            {"command": "git", "args": json.dumps(["reset", "--hard", "HEAD"])},
            {"commands": "git reset --hard HEAD"},
            {"command": "git reset --hard HEAD"},
            {"cmd": "git push --force"},
            {"command": "rm -rf build"},
            {"commands": "./build/one_combat bestbench 1000 8 0"},
        )
        for parameters in blocked:
            payload = {"preToolUse": {"toolName": "run_commands", "parameters": parameters}, "branch": "feature"}
            self.assertTrue(invoke(payload)["cancel"], parameters)
        allowed = (
            {"commands": json.dumps(["git status --short"])},
            {"commands": json.dumps(["ctest --preset linux-gcc-test"])},
            {"commands": json.dumps(["tools/seed_guard.sh ./build/one_combat bestbench 1000 8 0"])},
            {"commands": "git status --short"},
            {"command": "ctest --preset linux-gcc-test"},
            {"cmd": "git diff --check"},
        )
        for parameters in allowed:
            payload = {"preToolUse": {"toolName": "run_commands", "parameters": parameters}, "branch": "feature"}
            self.assertFalse(invoke(payload)["cancel"], parameters)


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
        self.assertTrue(module.baseline_path("test-task").exists())
        self.assertIn("docs/knowledge-base/operations/agent-context-and-workflow.md", [str(p.relative_to(ROOT)) for p in module.changed_files("4d6aecd49fe12b5423d9ca4ef7201307b8c82709")])
        cleanup = invoke({"hookName": "TaskComplete", "taskId": "test-task", "taskComplete": {}})
        self.assertFalse(cleanup["cancel"])
        self.assertFalse(module.baseline_path("test-task").exists())

    def test_task_state_is_isolated(self):
        module = load_module()
        invoke({"hookName": "TaskStart", "taskId": "task/one"})
        invoke({"hookName": "TaskStart", "taskId": "task/two"})
        one, two = module.baseline_path("task/one"), module.baseline_path("task/two")
        self.assertNotEqual(one, two)
        self.assertTrue(one.exists() and two.exists())
        invoke({"hookName": "TaskComplete", "taskId": "task/one", "taskComplete": {}})
        self.assertFalse(one.exists())
        self.assertTrue(two.exists())
        invoke({"hookName": "TaskComplete", "taskId": "task/two", "taskComplete": {}})

    def test_task_start_is_idempotent(self):
        module = load_module()
        task = "idempotent-task"
        path = module.baseline_path(task)
        try:
            with mock.patch.object(module, "git_head", return_value="baseline-X"):
                module.handle_task_start({"taskId": task, "taskStart": {}})
            with mock.patch.object(module, "git_head", return_value="head-Y"):
                module.handle_task_start({"taskId": task, "taskStart": {}})
            self.assertEqual(json.loads(path.read_text(encoding="utf-8"))["head"], "baseline-X")
        finally:
            path.unlink(missing_ok=True)

    def test_committed_whitespace_diff_is_checked(self):
        module = load_module()
        baseline = "baseline-sha"
        with mock.patch.object(module, "load_baseline", return_value={"head": baseline}), mock.patch.object(module, "changed_files", return_value=[]), mock.patch.object(module.subprocess, "run") as run:
            run.side_effect = [
                subprocess.CompletedProcess([], 1, "committed.py:1: trailing whitespace.\n", ""),
                subprocess.CompletedProcess([], 0, "", ""),
                subprocess.CompletedProcess([], 0, "", ""),
            ]
            error, _ = module.validate_changes("task")
        self.assertIn("git diff --check", error)
        self.assertEqual(run.call_args_list[0].args[0], ["git", "diff", "--check", f"{baseline}..HEAD"])

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
