import hashlib
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/agent/eval.py"
GUARDRAIL_FIXTURE_PATHS = (
    "src/committed_forbidden.txt",
    "src/merge_only.cpp",
    "src/sim/SimHelpers.cpp",
    "tests/agent/test_cline_guardrails.py",
    "tools/agent/committed_allowed.txt",
    "tools/agent/cline_guardrails.py",
    "tools/agent/renamed_sim_helpers.cpp",
    "tools/agent/side_branch_allowed.txt",
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
        workspace = self.eval_module.create_workspace("guardrail-command-policy-test-")
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

    def test_prepare_normalizes_crlf_setup_patch(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.txt"
            target.write_bytes(b"before\n")
            patch = root / "setup.patch"
            patch.write_bytes(
                b"--- a/target.txt\r\n+++ b/target.txt\r\n"
                b"@@ -1 +1 @@\r\n-before\r\n+after\r\n"
            )
            self.eval_module.apply_setup_patch(root, patch, "crlf")
            self.assertEqual(target.read_text(encoding="utf-8").splitlines(), ["after"])

        result = cli("prepare", "doctor-submodule-validation")
        self.assertEqual(result.returncode, 0, result.stderr)
        workspace = Path(json.loads(result.stdout)["workspace"])
        self.assertEqual(
            subprocess.run(
                ["git", "status", "--short"], cwd=workspace,
                text=True, capture_output=True, check=True,
            ).stdout,
            "",
        )

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
            fsck = subprocess.run(
                ["git", "fsck", "--full", "--no-reflogs", "--unreachable"],
                cwd=workspace, text=True, capture_output=True, check=True,
            )
            self.assertEqual(fsck.stdout, "")
            self.assertFalse((workspace / ".git" / "objects" / "info" / "alternates").exists())
            self.assertFalse((workspace / ".git" / "modules").exists())
            hidden_root = ROOT / "evals" / "coding_agent" / "tasks" / "guardrail-command-policy"
            for hidden in ("private/grader.py", "setup.patch", "task.json"):
                object_id = subprocess.run(
                    ["git", "hash-object", str(hidden_root / hidden)], cwd=ROOT,
                    text=True, capture_output=True, check=True,
                ).stdout.strip()
                present = subprocess.run(
                    ["git", "cat-file", "-e", object_id], cwd=workspace,
                    text=True, capture_output=True,
                )
                self.assertNotEqual(present.returncode, 0, hidden)
        self.assertTrue(Path(first["workspace"]).exists())
        self.assertTrue(Path(second["workspace"]).exists())

        cache = self.eval_module.cache_path(self.eval_module.export_identity()) / "tree"
        cached_readme = (cache / "json" / "README.md").read_bytes()
        first_readme = Path(first["workspace"]) / "json" / "README.md"
        second_readme = Path(second["workspace"]) / "json" / "README.md"
        second_before = second_readme.read_bytes()
        first_readme.write_bytes(b"candidate A mutation\n")
        self.assertEqual(second_readme.read_bytes(), second_before)
        self.assertEqual((cache / "json" / "README.md").read_bytes(), cached_readme)

        shutil_target = Path(first["workspace"]) / "source-cleanup-proof.txt"
        shutil_target.write_text("independent\n", encoding="utf-8")
        self.assertEqual(shutil_target.read_text(encoding="utf-8"), "independent\n")

        with tempfile.TemporaryDirectory() as tmp:
            runtime = Path(tmp) / "runtime"
            identity = {"version": 1, "head": "a" * 40, "submodules": {"json": "b" * 40, "pybind11": "c" * 40}}

            def minimal_export(destination):
                (destination / "public.txt").write_text("public\n", encoding="utf-8")

            with (
                mock.patch.object(self.eval_module, "RUNTIME", runtime),
                mock.patch.object(self.eval_module, "export_identity", return_value=identity),
                mock.patch.object(self.eval_module, "build_public_export", side_effect=minimal_export) as build,
            ):
                destinations = [Path(tmp) / name for name in ("first", "second")]
                for destination in destinations:
                    destination.mkdir()
                    self.eval_module.tracked_export(destination)
                self.assertEqual(build.call_count, 1)
                self.assertEqual([path for path in self.eval_module.cache_path(identity).parent.iterdir() if path.name.startswith(".tmp-")], [])
                entry = self.eval_module.cache_path(identity)
                (entry / "manifest.json").write_text("{}\n", encoding="utf-8")
                third = Path(tmp) / "third"; third.mkdir()
                with self.assertRaisesRegex(self.eval_module.EvalError, "identity/content mismatch"):
                    self.eval_module.tracked_export(third)

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            target = root / "target.txt"
            target.write_text("same\n", encoding="utf-8")
            patch = root / "noop.patch"
            patch.write_text(
                "--- a/target.txt\n+++ b/target.txt\n@@ -1 +1 @@\n-same\n+same\n",
                encoding="utf-8",
            )
            stats = subprocess.CompletedProcess([], 0, b"1\t1\ttarget.txt\0", b"")
            applied = subprocess.CompletedProcess([], 0, "", "")
            with mock.patch.object(
                self.eval_module.subprocess, "run", side_effect=(stats, applied),
            ):
                with self.assertRaisesRegex(self.eval_module.EvalError, "made no repository change"):
                    self.eval_module.apply_setup_patch(root, patch, "noop")

            original_read_bytes = Path.read_bytes

            def unreadable_target(path):
                if path == target:
                    raise OSError("denied")
                return original_read_bytes(path)

            with (
                mock.patch.object(self.eval_module.subprocess, "run", return_value=stats),
                mock.patch.object(Path, "read_bytes", unreadable_target),
            ):
                with self.assertRaisesRegex(self.eval_module.EvalError, "failed to inspect setup patch target"):
                    self.eval_module.apply_setup_patch(root, patch, "unreadable")

            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                mock.patch.object(
                    self.eval_module, "prepare",
                    side_effect=self.eval_module.EvalError("failed to inspect setup patch target"),
                ),
                mock.patch.object(sys, "argv", [str(SCRIPT), "prepare", "guardrail-command-policy"]),
                mock.patch.object(sys, "stdout", stdout),
                mock.patch.object(sys, "stderr", stderr),
            ):
                self.assertEqual(self.eval_module.main(), 2)
            self.assertEqual(stdout.getvalue(), "")
            infra_error = json.loads(stderr.getvalue())
            self.assertEqual(infra_error["result"], "INFRA_ERROR")
            self.assertIn("failed to inspect setup patch target", infra_error["error"])

            hidden = root / "evals"
            hidden.mkdir()
            (hidden / "private.txt").write_text("secret", encoding="utf-8")
            with mock.patch.object(
                self.eval_module.shutil, "rmtree", side_effect=OSError("denied"),
            ):
                with self.assertRaisesRegex(self.eval_module.EvalError, "failed to remove"):
                    self.eval_module.remove_hidden_data(root)
            self.assertTrue(hidden.exists())

            def minimal_export(workspace):
                (workspace / "evals").mkdir()

            git_result = subprocess.CompletedProcess([], 0, "", "")
            with (
                mock.patch.object(self.eval_module, "tracked_export", side_effect=minimal_export),
                mock.patch.object(self.eval_module, "apply_setup_patch"),
                mock.patch.object(
                    self.eval_module, "remove_hidden_data",
                    side_effect=self.eval_module.EvalError("failed to remove hidden evaluator data"),
                ),
                mock.patch.object(self.eval_module, "git", return_value=git_result) as git_mock,
            ):
                with self.assertRaisesRegex(self.eval_module.EvalError, "failed to remove"):
                    self.eval_module.prepare("guardrail-command-policy")
            self.assertFalse(any(call.args[1:2] in (("add",), ("commit",)) for call in git_mock.call_args_list))

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
