import json
import os
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path

from tools.live_game_runtime import CTM_NAME, OOC_NAME, RuntimeFailure, RuntimeManager, sha256


class LiveGameRuntimeTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        base = Path(self.temp.name)
        self.repo = base / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.email", "test@example.invalid"], cwd=self.repo, check=True)
        subprocess.run(["git", "config", "user.name", "Test"], cwd=self.repo, check=True)
        models = self.repo / "selfplay/models"
        models.mkdir(parents=True)
        (models / CTM_NAME).write_bytes(b"ctm")
        (models / OOC_NAME).write_bytes(b"ooc")
        subprocess.run(["git", "add", "."], cwd=self.repo, check=True)
        subprocess.run(["git", "commit", "-qm", "fixture"], cwd=self.repo, check=True)
        self.advisor = base / "advisor"
        self.advisor.write_text("#!/bin/sh\nexit 0\n")
        self.advisor.chmod(self.advisor.stat().st_mode | stat.S_IXUSR)
        self.config = base / "home/config.properties"
        self.active = base / "cache/active-runtime.json"
        self.manager = RuntimeManager(self.repo, base / "runtime", self.config, self.active)

    def tearDown(self):
        self.temp.cleanup()

    def install(self):
        return self.manager.install(self.advisor)

    def test_install_copies_self_contained_artifacts_and_activates_atomically(self):
        manifest = self.install()
        release = self.manager.current.resolve()
        self.assertTrue(self.manager.current.is_symlink())
        self.assertTrue((release / "one_combat_advisor").is_file())
        self.assertEqual((release / f"models/{CTM_NAME}").read_bytes(), b"ctm")
        self.assertEqual((release / f"models/{OOC_NAME}").read_bytes(), b"ooc")
        self.assertEqual(manifest["advisorSha256"], sha256(release / "one_combat_advisor"))
        self.assertNotIn("/.codex/worktrees/", json.dumps(self.manager.desired_config(manifest)))
        self.assertFalse(any(path.name.startswith(".current.") for path in self.manager.root.iterdir()))

    def test_repairs_stale_config_and_preserves_unrelated_keys(self):
        self.config.parent.mkdir(parents=True)
        self.config.write_text("theme=dark\nadvisor=/home/me/.codex/worktrees/old/advisor\nctmModel=/gone\n"
                               "oocModel=/home/me/.codex/worktrees/old/ooc\n# keep\n")
        self.install()
        text = self.config.read_text()
        self.assertIn("theme=dark", text)
        self.assertIn("# keep", text)
        self.assertIn(str(self.manager.current), text)
        self.assertNotIn("/.codex/worktrees/", text)
        self.assertIn(f"oocModel={self.manager.current}/models/{OOC_NAME}", text)

    def test_valid_runtime_is_reused_without_install(self):
        first = self.install()
        release = self.manager.current.resolve()
        second = self.manager.ensure()
        self.assertEqual(first["installedAt"], second["installedAt"])
        self.assertEqual(release, self.manager.current.resolve())

    def test_dirty_model_content_does_not_reuse_incompatible_cached_release(self):
        first = self.install()
        (self.repo / f"selfplay/models/{CTM_NAME}").write_bytes(b"changed-ctm")
        second = self.install()
        self.assertNotEqual(first["runtimeId"], second["runtimeId"])
        self.assertNotEqual(first["ctmSha256"], second["ctmSha256"])

    def test_missing_and_corrupt_artifacts_are_detected(self):
        self.install()
        advisor = self.manager.current.resolve() / "one_combat_advisor"
        advisor.write_bytes(b"corrupt")
        with self.assertRaisesRegex(RuntimeFailure, "hash mismatch"):
            self.manager.validate_release()
        advisor.unlink()
        with self.assertRaisesRegex(RuntimeFailure, "missing"):
            self.manager.validate_release()

    def test_missing_source_model_fails_clearly(self):
        (self.repo / f"selfplay/models/{CTM_NAME}").unlink()
        with self.assertRaisesRegex(RuntimeFailure, "tracked CTM model missing"):
            self.install()

    def test_status_does_not_require_mcp_and_reports_active_mismatch(self):
        manifest = self.install()
        self.active.parent.mkdir(parents=True)
        self.active.write_text(json.dumps({"runtimeId": "older"}))
        status = self.manager.status()
        self.assertTrue(status["usable"])
        self.assertIn(status["mcpEndpoint"], ("offline", "reachable"))
        self.assertFalse(status["activeRuntimeMatchesCurrent"])
        self.assertEqual(status["manifest"]["runtimeId"], manifest["runtimeId"])

    def test_manifest_hash_is_checked(self):
        self.install()
        path = self.manager.current.resolve() / "manifest.json"
        manifest = json.loads(path.read_text())
        manifest["ctmSha256"] = "0" * 64
        path.write_text(json.dumps(manifest))
        with self.assertRaisesRegex(RuntimeFailure, "hash mismatch"):
            self.manager.validate_release()

    def test_active_metadata_records_runtime_and_installed_jar_hashes(self):
        manifest = self.install()
        inspector = Path(self.temp.name) / "inspector.jar"
        inspector.write_bytes(b"jar")
        active = self.manager.record_active(inspector)
        self.assertEqual(active["runtimeId"], manifest["runtimeId"])
        self.assertEqual(active["inspectorJarSha256"], sha256(inspector))
        self.assertEqual(json.loads(self.active.read_text()), active)

    def test_java_configuration_uses_environment_first_seam(self):
        source = (Path(__file__).parents[1] /
                  "mods/sts-model-inspector/src/main/java/stsmodelinspector/STSModelInspector.java").read_text()
        self.assertIn('environmentFirst(p, "STS_MODEL_INSPECTOR_ADVISOR", "advisor")', source)
        self.assertIn('environmentFirst(p, "STS_CTM_MODEL", "ctmModel")', source)
        self.assertIn('environmentFirst(p, "STS_LIVE_OOC_MODEL", "oocModel")', source)
        self.assertIn('System.getenv("STS_MODEL_INSPECTOR_CONFIG")', source)


if __name__ == "__main__":
    unittest.main()
