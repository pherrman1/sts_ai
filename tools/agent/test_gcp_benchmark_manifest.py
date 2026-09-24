#!/usr/bin/env python3
"""Focused tests for strict GCP run-manifest environment/output handling."""
from __future__ import annotations

import copy
import json
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import gcp_benchmark


EXAMPLE = Path(__file__).with_name("research_run_manifest.example.json")


class RunManifestTests(unittest.TestCase):
    def setUp(self) -> None:
        self.payload = json.loads(EXAMPLE.read_text(encoding="utf-8"))

    def load_payload(self, payload: dict) -> dict:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "manifest.json"
            path.write_text(json.dumps(payload), encoding="utf-8")
            return gcp_benchmark.load_run_manifest(path)

    def test_v2_clean_environment_and_fresh_outputs(self) -> None:
        manifest = self.load_payload(self.payload)
        command, _log, fresh = gcp_benchmark.manifest_arm(manifest, "A")
        self.assertEqual(command[:2], ["env", "-i"])
        self.assertIn("HOME=/home/philippherrmann", command)
        self.assertIn("PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin", command)
        self.assertIn("results/replace-with-experiment-id-A.csv.meta.json", fresh)
        self.assertIn("logs/replace-with-experiment-id-A.log", fresh)

    def test_v1_inherited_environment_remains_accepted(self) -> None:
        old = copy.deepcopy(self.payload)
        old["schema_version"] = 1
        old.pop("environment_policy")
        for arm in old["arms"]:
            arm.pop("fresh_outputs")
        manifest = self.load_payload(old)
        command, _log, _fresh = gcp_benchmark.manifest_arm(manifest, "A")
        self.assertEqual(command[0], "env")
        self.assertNotEqual(command[1], "-i")

    def test_clean_policy_requires_explicit_home_and_path(self) -> None:
        bad = copy.deepcopy(self.payload)
        del bad["common_env"]["PATH"]
        with self.assertRaisesRegex(ValueError, "HOME and PATH"):
            self.load_payload(bad)

    def test_unknown_fields_fail_closed(self) -> None:
        bad = copy.deepcopy(self.payload)
        bad["unexpected"] = True
        with self.assertRaisesRegex(ValueError, "unknown or missing"):
            self.load_payload(bad)

    def test_fresh_output_collisions_fail_closed(self) -> None:
        bad = copy.deepcopy(self.payload)
        bad["arms"][0]["fresh_outputs"] = [bad["arms"][1]["results"]]
        with self.assertRaisesRegex(ValueError, "paths must be unique"):
            self.load_payload(bad)

    def test_fresh_output_guard_rejects_dangling_symlink(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            dangling = root / "dangling-output"
            dangling.symlink_to(root / "missing-target")
            guard = gcp_benchmark.fresh_output_guard([str(dangling)])
            result = subprocess.run(["bash", "-c", guard], check=False)
            self.assertEqual(result.returncode, 2)

            absent = root / "absent-output"
            guard = gcp_benchmark.fresh_output_guard([str(absent)])
            result = subprocess.run(["bash", "-c", guard], check=False)
            self.assertEqual(result.returncode, 0)

    def test_manifest_run_uses_seed_guard_from_pinned_checkout(self) -> None:
        manifest = self.load_payload(self.payload)
        expected_guard = (
            f"{gcp_benchmark.REMOTE_ROOT}/{manifest['checkout']}/tools/seed_guard.sh"
        )
        args = SimpleNamespace(
            action="run-manifest",
            project=gcp_benchmark.PROJECT,
            zone=gcp_benchmark.ZONE,
            instance=gcp_benchmark.INSTANCE,
            user=gcp_benchmark.REMOTE_USER,
            remote_root=gcp_benchmark.REMOTE_ROOT,
            manifest=EXAMPLE,
            arm="A",
            foreground=True,
            guard_only=True,
            allow_parallel=False,
        )
        remotes: list[str] = []
        with patch.object(
            gcp_benchmark,
            "ssh_command",
            side_effect=lambda _args, remote: remotes.append(remote) or 0,
        ):
            self.assertEqual(gcp_benchmark.manifest_run(args), 0)
        self.assertEqual(len(remotes), 1)
        remote = remotes[0]
        self.assertIn(f"cd {gcp_benchmark.REMOTE_ROOT};", remote)
        self.assertIn(f"test -f {expected_guard}; command -v bash", remote)
        self.assertIn(f"bash {expected_guard} --gcp-research guard-only env -i ", remote)
        self.assertNotIn("bash tools/seed_guard.sh --gcp-research", remote)

        preflight_commands: list[str] = []
        with patch.object(
            gcp_benchmark,
            "ssh_command",
            side_effect=lambda _args, remote: preflight_commands.append(remote) or 0,
        ):
            self.assertEqual(gcp_benchmark.exact_sha_preflight(args), 0)
        self.assertEqual(len(preflight_commands), 1)
        self.assertIn(
            f"git -C {gcp_benchmark.REMOTE_ROOT}/{manifest['checkout']} "
            "ls-files --error-unmatch tools/seed_guard.sh >/dev/null",
            preflight_commands[0],
        )
        self.assertIn(f"test -f {expected_guard}", preflight_commands[0])

    def test_generic_run_retains_remote_root_seed_guard(self) -> None:
        args = SimpleNamespace(
            project=gcp_benchmark.PROJECT,
            zone=gcp_benchmark.ZONE,
            instance=gcp_benchmark.INSTANCE,
            user=gcp_benchmark.REMOTE_USER,
            remote_root=gcp_benchmark.REMOTE_ROOT,
            command=["/bin/true"],
            foreground=True,
            guard_only=True,
            allow_parallel=False,
            log=None,
            fresh_paths=[],
        )
        remotes: list[str] = []
        with patch.object(
            gcp_benchmark,
            "ssh_command",
            side_effect=lambda _args, remote: remotes.append(remote) or 0,
        ):
            self.assertEqual(gcp_benchmark.remote_run(args), 0)
        self.assertEqual(len(remotes), 1)
        remote = remotes[0]
        self.assertIn("test -f tools/seed_guard.sh; command -v bash", remote)
        self.assertIn("bash tools/seed_guard.sh --gcp-research guard-only /bin/true", remote)


if __name__ == "__main__":
    unittest.main(verbosity=2)
