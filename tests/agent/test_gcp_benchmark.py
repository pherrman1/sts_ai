import importlib.util
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/agent/gcp_benchmark.py"
SEED_GUARD = ROOT / "tools/seed_guard.sh"


def load_module():
    spec = importlib.util.spec_from_file_location("gcp_benchmark", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class GcpBenchmarkTests(unittest.TestCase):
    def test_local_seed_guard_rejects_gcp_mode(self):
        result = subprocess.run(
            [str(SEED_GUARD), "--gcp-research", "guard-only", "./build/one_combat", "bestbench", "1000", "2000", "0"],
            cwd=ROOT,
            text=True,
            capture_output=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("requires host sts-test", result.stderr)

    def test_designated_remote_command_uses_gcp_context(self):
        module = load_module()
        args = module.parser().parse_args(
            ["run", "--foreground", "--guard-only", "--", "./build/one_combat", "bestbench", "1000", "2000", "0"]
        )
        captured = {}

        def fake_ssh(parsed, remote):
            captured["remote"] = remote
            return 0

        with mock.patch.object(module, "ssh_command", side_effect=fake_ssh):
            self.assertEqual(module.remote_run(args), 0)
        self.assertIn("cd /home/philippherrmann/sts_sweep;", captured["remote"])
        self.assertIn("env STS_GCP_RESEARCH_CONTEXT=sts-test", captured["remote"])
        self.assertIn("bash tools/seed_guard.sh --gcp-research guard-only", captured["remote"])
        self.assertIn("bestbench 1000 2000 0", captured["remote"])

    def test_non_designated_run_is_rejected_before_gcloud(self):
        module = load_module()
        args = module.parser().parse_args(
            ["--instance", "other-vm", "run", "--", "./build/one_combat", "bestbench", "1000", "2000", "0"]
        )
        with mock.patch.object(module, "gcloud_path", side_effect=AssertionError("gcloud must not be resolved")):
            with self.assertRaisesRegex(ValueError, "designated GCP target"):
                module.remote_run(args)

    def test_non_designated_start_is_rejected_before_gcloud(self):
        module = load_module()
        args = module.parser().parse_args(["--zone", "wrong-zone", "start-instance"])
        with mock.patch.object(module, "gcloud_path", side_effect=AssertionError("gcloud must not be resolved")):
            with self.assertRaisesRegex(ValueError, "designated GCP target"):
                module.start_instance(args)

    def test_explicit_gcloud_override_is_used(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "gcloud"
            executable.touch()
            with mock.patch.dict(module.os.environ, {"STS_GCLOUD": str(executable)}):
                self.assertEqual(module.gcloud_path(), str(executable))

    def test_documented_windows_path_is_a_fallback_candidate(self):
        module = load_module()
        self.assertIn("gcloud.cmd", " ".join(module.WINDOWS_GCLOUD))

    def test_run_builds_guarded_detached_command(self):
        module = load_module()
        args = module.parser().parse_args(
            ["run", "--", "./build/one_combat", "bestbench", "1000", "2000", "0"]
        )
        captured = {}

        def fake_ssh(parsed, remote):
            captured["remote"] = remote
            return 0

        with mock.patch.object(module, "ssh_command", side_effect=fake_ssh):
            self.assertEqual(module.remote_run(args), 0)
        self.assertIn("seed_guard.sh --gcp-research", captured["remote"])
        self.assertIn("2000", captured["remote"])
        self.assertIn("nohup", captured["remote"])
        self.assertIn("remote_pid", captured["remote"])
        self.assertIn("env STS_GCP_RESEARCH_CONTEXT=sts-test", captured["remote"])
        self.assertIn("test -f tools/seed_guard.sh", captured["remote"])
        self.assertIn("command -v nohup", captured["remote"])

    def test_run_can_select_nonexecuting_guard_proof(self):
        module = load_module()
        args = module.parser().parse_args(
            ["run", "--foreground", "--guard-only", "--", "./build/one_combat", "bestbench", "1000", "2000", "0"]
        )
        captured = {}

        def fake_ssh(parsed, remote):
            captured["remote"] = remote
            return 0

        with mock.patch.object(module, "ssh_command", side_effect=fake_ssh):
            self.assertEqual(module.remote_run(args), 0)
        self.assertIn("--gcp-research guard-only", captured["remote"])
        self.assertNotIn("nohup", captured["remote"])
        self.assertIn("cd", captured["remote"])
        self.assertIn("env STS_GCP_RESEARCH_CONTEXT=sts-test", captured["remote"])

    def test_run_default_refuses_parallel_work(self):
        module = load_module()
        args = module.parser().parse_args(
            ["run", "--", "./build/one_combat", "bestbench", "1000", "2", "0"]
        )
        captured = {}
        def fake_ssh(parsed, remote):
            captured["remote"] = remote
            return 0

        with mock.patch.object(module, "ssh_command", side_effect=fake_ssh):
            module.remote_run(args)
        self.assertIn("active one_combat process found", captured["remote"])
        self.assertIn('comm= | awk \'$2 == "one_combat"', captured["remote"])
        self.assertNotIn("parallel_run_explicitly_allowed", captured["remote"])

    def test_run_allows_parallel_work_only_with_explicit_opt_in(self):
        module = load_module()
        args = module.parser().parse_args(
            ["run", "--allow-parallel", "--", "./build/one_combat", "bestbench", "1000", "2", "0"]
        )
        captured = {}

        def fake_ssh(parsed, remote):
            captured["remote"] = remote
            return 0

        with mock.patch.object(module, "ssh_command", side_effect=fake_ssh):
            module.remote_run(args)
        self.assertIn("parallel_run_explicitly_allowed", captured["remote"])


if __name__ == "__main__":
    unittest.main()