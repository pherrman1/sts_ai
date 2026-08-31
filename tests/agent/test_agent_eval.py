import hashlib
import importlib.util
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/agent/eval.py"
GUARDRAIL_FIXTURE_PATHS = (
    "src/sim/SimHelpers.cpp",
    "tests/agent/test_cline_guardrails.py",
    "tools/agent/cline_guardrails.py",
)


def cli(*args):
    return subprocess.run([sys.executable, str(SCRIPT), *args], cwd=ROOT, text=True, capture_output=True)


def load_eval_module():
    spec = importlib.util.spec_from_file_location("agent_eval", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class AgentEvalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.eval_module = load_eval_module()
        result = cli("prepare", "guardrail-command-policy")
        if result.returncode:
            raise AssertionError(result.stderr)
        cls.fixture = json.loads(result.stdout)

    def clone_fixture(self):
        source = Path(self.fixture["workspace"])
        workspace = Path(tempfile.mkdtemp(
            prefix="guardrail-command-policy-test-",
            dir=self.eval_module.RUNTIME / "work",
        ))
        subprocess.run(
            ["git", "clone", "--shared", "--quiet", "--no-checkout", str(source), str(workspace)],
            check=True,
        )
        subprocess.run(
            ["git", "sparse-checkout", "set", "--no-cone", *GUARDRAIL_FIXTURE_PATHS],
            cwd=workspace, check=True,
        )
        subprocess.run(["git", "checkout", "--quiet"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.email", "agent-eval@example.invalid"], cwd=workspace, check=True)
        subprocess.run(["git", "config", "user.name", "agent-eval"], cwd=workspace, check=True)
        baseline = subprocess.run(
            ["git", "rev-parse", "HEAD"], cwd=workspace,
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        self.eval_module.record_prepared_baseline(
            "guardrail-command-policy", workspace, baseline,
        )
        return {"workspace": str(workspace), "baseline_commit": baseline}

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
        first = self.clone_fixture()
        second = self.clone_fixture()
        before = subprocess.run(["git", "status", "--porcelain=v1"], cwd=second["workspace"], text=True, capture_output=True).stdout
        result = cli("grade", "guardrail-command-policy", first["workspace"])
        self.assertEqual(result.returncode, 1)
        after = subprocess.run(["git", "status", "--porcelain=v1"], cwd=second["workspace"], text=True, capture_output=True).stdout
        self.assertEqual(before, after)

    def test_committed_forbidden_path_is_still_scoped_against_prepared_baseline(self):
        prepared = self.clone_fixture()
        workspace = Path(prepared["workspace"])
        allowed = workspace / "tools" / "agent" / "committed_allowed.txt"
        forbidden = workspace / "src" / "committed_forbidden.txt"
        allowed.write_text("allowed\n", encoding="utf-8")
        forbidden.write_text("forbidden\n", encoding="utf-8")
        subprocess.run(["git", "add", str(allowed), str(forbidden)], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-qm", "agent committed changes"], cwd=workspace, check=True)

        result = cli("grade", "guardrail-command-policy", str(workspace))
        self.assertEqual(result.returncode, 1, result.stderr)
        record = json.loads(result.stdout)
        self.assertEqual(record["baseline_commit"], prepared["baseline_commit"])
        self.assertNotEqual(record["candidate_commit"], record["baseline_commit"])
        self.assertIn("tools/agent/committed_allowed.txt", record["changed_files"])
        self.assertIn("src/committed_forbidden.txt", record["changed_files"])
        self.assertTrue(any(
            check["name"] == "changed-path-policy"
            and not check["passed"]
            and "forbidden path changed: src/committed_forbidden.txt" in check["detail"]
            for check in record["checks"]
        ))

    def test_rewritten_non_descendant_history_fails_closed(self):
        prepared = self.clone_fixture()
        workspace = Path(prepared["workspace"])
        tree = subprocess.run(
            ["git", "rev-parse", "HEAD^{tree}"], cwd=workspace,
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        rewritten = subprocess.run(
            ["git", "commit-tree", tree], cwd=workspace, input="rewritten history\n",
            text=True, capture_output=True, check=True,
        ).stdout.strip()
        subprocess.run(["git", "update-ref", "HEAD", rewritten], cwd=workspace, check=True)

        result = cli("grade", "guardrail-command-policy", str(workspace))
        self.assertEqual(result.returncode, 2)
        self.assertIn("candidate HEAD is not a descendant", result.stderr)

    def test_committed_rename_retains_forbidden_source_path(self):
        prepared = self.clone_fixture()
        workspace = Path(prepared["workspace"])
        old_path = "src/sim/SimHelpers.cpp"
        new_path = "tools/agent/renamed_sim_helpers.cpp"
        subprocess.run(["git", "mv", old_path, new_path], cwd=workspace, check=True)
        subprocess.run(
            ["git", "commit", "-qm", "agent renamed forbidden source"],
            cwd=workspace, check=True,
        )

        result = cli("grade", "guardrail-command-policy", str(workspace))
        self.assertEqual(result.returncode, 1, result.stderr)
        record = json.loads(result.stdout)
        self.assertIn(old_path, record["changed_files"])
        self.assertIn(new_path, record["changed_files"])
        self.assertTrue(any(
            check["name"] == "changed-path-policy"
            and not check["passed"]
            and f"forbidden path changed: {old_path}" in check["detail"]
            for check in record["checks"]
        ))

    def test_merge_resolution_forbidden_path_is_scoped(self):
        prepared = self.clone_fixture()
        workspace = Path(prepared["workspace"])
        allowed_path = "tools/agent/side_branch_allowed.txt"
        forbidden_path = "src/merge_only.cpp"
        subprocess.run(["git", "switch", "-c", "allowed-side"], cwd=workspace, check=True)
        (workspace / allowed_path).write_text("allowed side change\n", encoding="utf-8")
        subprocess.run(["git", "add", allowed_path], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-qm", "allowed side change"], cwd=workspace, check=True)
        subprocess.run(["git", "switch", "-"], cwd=workspace, check=True)
        subprocess.run(
            ["git", "merge", "--no-ff", "--no-commit", "allowed-side"],
            cwd=workspace, check=True,
        )
        (workspace / forbidden_path).write_text("merge-only change\n", encoding="utf-8")
        subprocess.run(["git", "add", forbidden_path], cwd=workspace, check=True)
        subprocess.run(["git", "commit", "-qm", "merge with forbidden resolution"], cwd=workspace, check=True)

        result = cli("grade", "guardrail-command-policy", str(workspace))
        self.assertEqual(result.returncode, 1, result.stderr)
        record = json.loads(result.stdout)
        self.assertIn(forbidden_path, record["changed_files"])
        self.assertTrue(any(
            check["name"] == "changed-path-policy"
            and not check["passed"]
            and f"forbidden path changed: {forbidden_path}" in check["detail"]
            for check in record["checks"]
        ))

    def test_manifest_rejects_unsafe_paths(self):
        import importlib.util
        spec = importlib.util.spec_from_file_location("agent_eval", SCRIPT)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        with self.assertRaises(module.EvalError):
            module.safe_rel("../../outside", "workspace")


if __name__ == "__main__":
    unittest.main()
