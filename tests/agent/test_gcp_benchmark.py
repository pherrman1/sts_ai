import importlib.util
import hashlib
import json
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


def valid_manifest():
    sha = "a" * 40
    digest = "b" * 64
    return {
        "schema_version": 1,
        "experiment_id": "policy-2x2",
        "frozen_sha": sha,
        "checkout": "checkouts/policy-2x2",
        "build_dir": "checkouts/policy-2x2/build/linux-gcc-release",
        "binary": {"remote_path": "checkouts/policy-2x2/build/linux-gcc-release/one_combat", "sha256": digest},
        "artifacts": [{"remote_path": "artifacts/policy-model.txt", "sha256": "c" * 64}],
        "common_env": {
            "OMP_NUM_THREADS": "1",
            "STS_EXECUTABLE_GIT_SHA": sha,
            "STS_SILVER_TELEMETRY": "1",
        },
        "required_env": ["OMP_NUM_THREADS", "STS_EXECUTABLE_GIT_SHA", "STS_SILVER_TELEMETRY"],
        "expect_silver_telemetry": True,
        "command": [
            "checkouts/policy-2x2/build/linux-gcc-release/one_combat",
            "bestbench", "1000", "32", "1", "975000", "{results}",
        ],
        "arms": [
            {"name": "A", "results": "results/policy-A.csv", "log": "logs/policy-A.log", "env": {"STS_POLICY_ARM": "A"}},
            {"name": "B", "results": "results/policy-B.csv", "log": "logs/policy-B.log", "env": {"STS_POLICY_ARM": "B"}},
        ],
    }


def write_manifest(directory, payload):
    path = Path(directory) / "manifest.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


class GcpBenchmarkTests(unittest.TestCase):
    def test_manifest_validates_and_renders_shared_configuration(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            manifest = module.load_run_manifest(write_manifest(directory, valid_manifest()))
        command, log, fresh = module.manifest_arm(manifest, "B")
        self.assertEqual(log, "logs/policy-B.log")
        self.assertEqual(fresh, ["results/policy-B.csv", "results/policy-B.csv.meta.json", "logs/policy-B.log"])
        self.assertEqual(command[0], "env")
        self.assertIn("STS_SILVER_TELEMETRY=1", command)
        self.assertIn("STS_POLICY_ARM=B", command)
        self.assertEqual(command[-2:], ["975000", "results/policy-B.csv"])

    def test_manifest_fails_closed_on_missing_telemetry(self):
        module = load_module()
        payload = valid_manifest()
        payload["common_env"]["STS_SILVER_TELEMETRY"] = "0"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "must be nonzero"):
                module.load_run_manifest(write_manifest(directory, payload))

    def test_v2_manifest_clears_ambient_environment(self):
        module = load_module()
        payload = valid_manifest()
        payload["schema_version"] = 2
        payload["clear_env"] = True
        with tempfile.TemporaryDirectory() as directory:
            manifest = module.load_run_manifest(write_manifest(directory, payload))
        command, _log, _fresh = module.manifest_arm(manifest, "A")
        self.assertEqual(command[:2], ["env", "-i"])

    def test_manifest_fails_closed_on_reused_output(self):
        module = load_module()
        payload = valid_manifest()
        payload["arms"][1]["results"] = payload["arms"][0]["results"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "paths must be unique"):
                module.load_run_manifest(write_manifest(directory, payload))

    def test_manifest_fails_closed_on_common_configuration_override(self):
        module = load_module()
        payload = valid_manifest()
        payload["arms"][0]["env"]["OMP_NUM_THREADS"] = "8"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "overrides common_env"):
                module.load_run_manifest(write_manifest(directory, payload))

    def test_manifest_requires_thread_and_sha_provenance(self):
        module = load_module()
        payload = valid_manifest()
        payload["required_env"].remove("OMP_NUM_THREADS")
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "must include OMP_NUM_THREADS"):
                module.load_run_manifest(write_manifest(directory, payload))

    def test_manifest_binary_must_belong_to_declared_build(self):
        module = load_module()
        payload = valid_manifest()
        payload["binary"]["remote_path"] = "checkouts/other/build/one_combat"
        payload["command"][0] = payload["binary"]["remote_path"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "build_dir/one_combat"):
                module.load_run_manifest(write_manifest(directory, payload))

    def test_manifest_reserves_implicit_sidecar_paths(self):
        module = load_module()
        payload = valid_manifest()
        payload["arms"][1]["log"] = payload["arms"][0]["results"] + ".meta.json"
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "sidecar paths must be unique"):
                module.load_run_manifest(write_manifest(directory, payload))

    def test_run_manifest_adds_env_and_refuses_existing_outputs(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = write_manifest(directory, valid_manifest())
            args = module.parser().parse_args(["run-manifest", str(path), "A", "--foreground"])
            captured = {}
            with mock.patch.object(module, "ssh_command", side_effect=lambda _args, remote: captured.setdefault("remote", remote) and 0):
                self.assertEqual(module.manifest_run(args), 0)
        remote = captured["remote"]
        self.assertIn("STS_SILVER_TELEMETRY=1", remote)
        self.assertIn("STS_POLICY_ARM=A", remote)
        self.assertIn("refusing existing output", remote)
        self.assertIn("policy-A.csv.meta.json", remote)

    def test_copy_to_verifies_local_and_remote_hash(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "artifact.json"
            source.write_text("{}", encoding="utf-8")
            digest = hashlib.sha256(b"{}").hexdigest()
            args = module.parser().parse_args(["copy-to", str(source), "artifacts/a.json", "--expect-sha256", digest])
            with mock.patch.object(module, "run_gcloud") as copy:
                copy.return_value.returncode = 0
                with mock.patch.object(module, "ssh_command", return_value=0) as ssh:
                    self.assertEqual(module.copy_to(args), 0)
        self.assertIn(digest, ssh.call_args.args[1])
        self.assertIn("sha256sum", ssh.call_args.args[1])

    def test_copy_to_rejects_wrong_local_hash_before_transfer(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "artifact.json"
            source.write_text("{}", encoding="utf-8")
            args = module.parser().parse_args(["copy-to", str(source), "artifacts/a.json", "--expect-sha256", "0" * 64])
            with mock.patch.object(module, "run_gcloud", side_effect=AssertionError("must not transfer")):
                with self.assertRaisesRegex(ValueError, "local SHA-256 mismatch"):
                    module.copy_to(args)

    def test_exact_sha_preflight_checks_checkout_binding_and_hashes(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            path = write_manifest(directory, valid_manifest())
            args = module.parser().parse_args(["exact-sha-preflight", str(path)])
            with mock.patch.object(module, "ssh_command", return_value=0) as ssh:
                self.assertEqual(module.exact_sha_preflight(args), 0)
        remote = ssh.call_args.args[1]
        self.assertIn("rev-parse HEAD", remote)
        self.assertIn("status --porcelain --untracked-files=no", remote)
        self.assertIn("CMAKE_HOME_DIRECTORY:INTERNAL=", remote)
        self.assertIn("b" * 64, remote)
        self.assertIn("c" * 64, remote)

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

    def test_copy_to_uses_designated_relative_remote_path(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as directory:
            source = Path(directory) / "artifact.json"
            source.write_text("{}")
            args = module.parser().parse_args(
                ["copy-to", str(source), "pilot-artifacts/run/artifact.json"]
            )
            with mock.patch.object(module, "run_gcloud") as run:
                run.return_value.returncode = 0
                self.assertEqual(module.copy_to(args), 0)
            command = run.call_args.args
            self.assertEqual(command[:3], (args, "compute", "scp"))
            self.assertEqual(command[3], str(source))
            self.assertEqual(
                command[4],
                "philippherrmann@sts-test:/home/philippherrmann/sts_sweep/"
                "pilot-artifacts/run/artifact.json",
            )

    def test_copy_paths_fail_closed_before_gcloud(self):
        module = load_module()
        cases = [
            ["copy-from", "../outside", "local.json"],
            ["copy-from", "/tmp/outside", "local.json"],
            ["copy-from", "logs/*", "local.json"],
            ["copy-from", "logs/x;touch", "local.json"],
            ["copy-from", "logs/x\nname", "local.json"],
            ["copy-from", "logs/`id`", "local.json"],
            ["copy-from", "logs//empty", "local.json"],
            ["--zone", "wrong-zone", "copy-from", "artifact.json", "local.json"],
        ]
        for argv in cases:
            with self.subTest(argv=argv):
                args = module.parser().parse_args(argv)
                with mock.patch.object(
                    module, "gcloud_path", side_effect=AssertionError("gcloud must not be resolved")
                ):
                    with self.assertRaisesRegex(ValueError, "designated|relative|components"):
                        module.copy_from(args)

    def test_copy_from_uses_designated_relative_remote_path(self):
        module = load_module()
        args = module.parser().parse_args(
            ["copy-from", "logs/run.log", "local-run.log"]
        )
        with mock.patch.object(module, "run_gcloud") as run:
            run.return_value.returncode = 0
            self.assertEqual(module.copy_from(args), 0)
        self.assertEqual(
            run.call_args.args[3:],
            (
                "philippherrmann@sts-test:/home/philippherrmann/sts_sweep/logs/run.log",
                "local-run.log",
            ),
        )

    def test_job_status_validates_pid_and_uses_designated_ssh(self):
        module = load_module()
        args = module.parser().parse_args(["job-status", "1234"])
        with mock.patch.object(module, "ssh_command", return_value=0) as ssh:
            self.assertEqual(module.job_status(args), 0)
        self.assertIn("ps -p 1234", ssh.call_args.args[1])
        self.assertIn("job_status=not_running_or_unknown", ssh.call_args.args[1])
        invalid = module.parser().parse_args(["job-status", "0"])
        with self.assertRaisesRegex(ValueError, "positive"):
            module.job_status(invalid)

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
        self.assertIn('comm= | awk \'$2 == "one_combat" {print; found=1}', captured["remote"])
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
