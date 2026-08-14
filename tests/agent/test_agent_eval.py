import json
import subprocess
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/agent/eval.py"


def cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


class AgentEvalTests(unittest.TestCase):
    def test_list_has_exactly_four_tasks(self):
        result = cli("list")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(len(result.stdout.splitlines()), 4)

    def test_prepare_isolated_and_hides_reference_data(self):
        first = json.loads(cli("prepare", "guardrail-command-policy").stdout)
        second = json.loads(cli("prepare", "guardrail-command-policy").stdout)
        self.assertNotEqual(first["workspace"], second["workspace"])
        for item in (first, second):
            workspace = Path(item["workspace"])
            self.assertFalse((workspace / "evals").exists())
            self.assertFalse((workspace / "setup.patch").exists())
            self.assertEqual(list((workspace / ".git").rglob("*private*")), [])
            self.assertEqual(subprocess.run(["git", "status", "--short"], cwd=workspace, text=True, capture_output=True).stdout, "")
        self.assertTrue(Path(first["workspace"]).exists())
        self.assertTrue(Path(second["workspace"]).exists())

    def test_traversal_workspace_is_infra_error(self):
        result = cli("grade", "guardrail-command-policy", str(ROOT / ".agent-eval" / "work" / ".."))
        self.assertEqual(result.returncode, 2)
        self.assertIn("INFRA_ERROR", result.stderr)

    def test_grading_one_trial_does_not_modify_another(self):
        first = json.loads(cli("prepare", "guardrail-command-policy").stdout)
        second = json.loads(cli("prepare", "guardrail-command-policy").stdout)
        before = subprocess.run(["git", "status", "--porcelain=v1"], cwd=second["workspace"], text=True, capture_output=True).stdout
        result = cli("grade", "guardrail-command-policy", first["workspace"])
        self.assertEqual(result.returncode, 1)
        after = subprocess.run(["git", "status", "--porcelain=v1"], cwd=second["workspace"], text=True, capture_output=True).stdout
        self.assertEqual(before, after)

    def test_manifest_rejects_unsafe_paths(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_eval", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(module.EvalError):
            module.safe_rel("../../outside", "workspace")


if __name__ == "__main__":
    unittest.main()