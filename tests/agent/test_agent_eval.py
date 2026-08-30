import hashlib
import json
import subprocess
import sys
import tempfile
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

    def test_prepare_overlays_skill_into_clean_candidate_baseline(self):
        content = b"---\nname: pilot-skill\ndescription: Test skill.\n---\n"
        with tempfile.TemporaryDirectory() as tmp:
            skill_file = Path(tmp) / "SKILL.md"
            skill_file.write_bytes(content)
            result = cli("prepare", "guardrail-command-policy", "--skill-file", str(skill_file), "--skill-name", "pilot-skill")
        self.assertEqual(result.returncode, 0, result.stderr)
        prepared = json.loads(result.stdout)
        workspace = Path(prepared["workspace"])
        target = workspace / ".agents" / "skills" / "pilot-skill" / "SKILL.md"
        self.assertEqual(target.read_bytes(), content)
        self.assertEqual(prepared["skill_name"], "pilot-skill")
        self.assertEqual(prepared["skill_sha256"], hashlib.sha256(content).hexdigest())
        self.assertIn("Use the $pilot-skill skill", prepared["prompt"])
        self.assertFalse((workspace / "evals").exists())
        self.assertEqual(subprocess.run(["git", "status", "--short"], cwd=workspace, text=True, capture_output=True).stdout, "")
        self.assertEqual(subprocess.run(["git", "diff", "--name-only", "HEAD"], cwd=workspace, text=True, capture_output=True).stdout, "")
        self.assertEqual(subprocess.run(["git", "show", "HEAD:.agents/skills/pilot-skill/SKILL.md"], cwd=workspace, capture_output=True).stdout, content)

    def test_prepare_skill_options_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            skill_file = root / "SKILL.md"
            skill_file.write_text("test", encoding="utf-8")
            cases = [
                ("--skill-file", str(skill_file)),
                ("--skill-name", "pilot-skill"),
                ("--skill-file", str(root / "missing.md"), "--skill-name", "pilot-skill"),
                ("--skill-file", str(root), "--skill-name", "pilot-skill"),
                ("--skill-file", str(skill_file), "--skill-name", "../unsafe"),
                ("--skill-file", str(skill_file), "--skill-name", "Uppercase"),
            ]
            for args in cases:
                with self.subTest(args=args):
                    result = cli("prepare", "guardrail-command-policy", *args)
                    self.assertEqual(result.returncode, 2)
                    self.assertIn("INFRA_ERROR", result.stderr)

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
