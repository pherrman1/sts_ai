import json
import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.live_game_runtime import CTM_NAME, OOC_NAME, OOC_WIN_NAME, OOC_FLOOR_NAME, RuntimeFailure, RuntimeManager, sha256


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
        root_models = self.repo / "models"
        root_models.mkdir(parents=True)
        (models / CTM_NAME).write_bytes(b"ctm")
        (models / OOC_NAME).write_bytes(b"ooc")
        (root_models / OOC_WIN_NAME).write_bytes(b"win")
        (root_models / OOC_FLOOR_NAME).write_bytes(b"floor")
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
        self.assertEqual((release / f"models/{OOC_WIN_NAME}").read_bytes(), b"win")
        self.assertEqual((release / f"models/{OOC_FLOOR_NAME}").read_bytes(), b"floor")
        self.assertEqual(manifest["oocWinModelSha256"], sha256(release / f"models/{OOC_WIN_NAME}"))
        self.assertEqual(manifest["oocFloorModelSha256"], sha256(release / f"models/{OOC_FLOOR_NAME}"))
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
        self.assertIn(f"oocWinModel={self.manager.current}/models/{OOC_WIN_NAME}", text)
        self.assertIn(f"oocFloorModel={self.manager.current}/models/{OOC_FLOOR_NAME}", text)

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

    def test_missing_source_win_model_fails_clearly(self):
        (self.repo / f"models/{OOC_WIN_NAME}").unlink()
        with self.assertRaisesRegex(RuntimeFailure, "tracked OOC win model missing"):
            self.install()

    def test_missing_source_floor_model_fails_clearly(self):
        (self.repo / f"models/{OOC_FLOOR_NAME}").unlink()
        with self.assertRaisesRegex(RuntimeFailure, "tracked OOC floor model missing"):
            self.install()

    def test_status_does_not_require_mcp_and_reports_active_mismatch(self):
        manifest = self.install()
        self.active.parent.mkdir(parents=True)
        self.active.write_text(json.dumps({"runtimeId": "older"}))
        status = self.manager.status()
        self.assertTrue(status["usable"])
        self.assertIn(status["mcpEndpoint"], ("offline", "reachable"))
        self.assertFalse(status["activeRuntimeMatchesCurrent"])
        self.assertFalse(status["activeProcessMatches"])
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
        active = self.manager.record_active(inspector, os.getpid())
        self.assertEqual(active["runtimeId"], manifest["runtimeId"])
        self.assertEqual(active["oocFloorModelSha256"], manifest["oocFloorModelSha256"])
        self.assertEqual(active["inspectorJarSha256"], sha256(inspector))
        self.assertEqual(active["processPid"], os.getpid())
        self.assertTrue(self.manager.active_process_matches(active))
        self.assertEqual(json.loads(self.active.read_text()), active)
        status = self.manager.status()
        self.assertTrue(status["activeProcessMatches"])
        self.assertTrue(status["activeRuntimeMatchesCurrent"])

    def test_build_advisor_packages_only_wrapper_selected_fallback_preset(self):
        fallback = self.repo / "build/linux-gcc-debug/one_combat_advisor"
        requested = self.repo / "build/linux-gcc-debug-ccache/one_combat_advisor"
        fallback.parent.mkdir(parents=True)
        requested.parent.mkdir(parents=True)
        fallback.write_text("fallback")
        requested.write_text("wrong-newer")
        fallback.chmod(fallback.stat().st_mode | stat.S_IXUSR)
        requested.chmod(requested.stat().st_mode | stat.S_IXUSR)
        os.utime(requested, (fallback.stat().st_mtime + 10, fallback.stat().st_mtime + 10))
        wrapper_output = ("ccache_fallback=linux-gcc-debug build_preset=linux-gcc-debug-build "
                          "configure_forced=false reason=test\nbuild_route=native root=test\n")
        with mock.patch("tools.live_game_runtime.run"), \
             mock.patch("tools.live_game_runtime.run_output", return_value=wrapper_output):
            self.assertEqual(self.manager.build_advisor(), fallback)

    def test_allow_missing_advisor_does_not_require_or_record_runtime(self):
        base = Path(self.temp.name)
        game = base / "game"
        mods = game / "mods"
        mods.mkdir(parents=True)
        (mods / "MCPTheSpire.jar").write_bytes(b"mcp")
        (mods / "sts-model-inspector.jar").write_bytes(b"inspector")
        modthespire = base / "ModTheSpire.jar"
        modthespire.write_bytes(b"mts")
        calls = base / "runtime-calls"
        runtime = base / "runtime-tool"
        runtime.write_text("import pathlib, sys\n"
                           f"pathlib.Path({str(calls)!r}).open('a').write(sys.argv[1] + '\\n')\n"
                           "raise SystemExit(2)\n")
        runtime.chmod(runtime.stat().st_mode | stat.S_IXUSR)
        environment = {
            **os.environ,
            "HOME": str(base / "home"),
            "STS_GAME_DIR": str(game),
            "STS_MODTHESPIRE_JAR": str(modthespire),
            "STS_MCP_THE_SPIRE_JAR": str(mods / "MCPTheSpire.jar"),
            "STS_MODEL_INSPECTOR_JAR": str(mods / "sts-model-inspector.jar"),
            "STS_JAVA_BIN": "/bin/true",
            "STS_LIVE_RUNTIME_TOOL": str(runtime),
            "STS_MCP_PORT": "49151",
        }
        completed = subprocess.run(
            [str(Path(__file__).parents[1] / "tools/live_game_start.sh"),
             "--allow-missing-advisor", "--check"],
            env=environment, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        )
        self.assertEqual(completed.returncode, 1, completed.stdout + completed.stderr)
        self.assertIn("MCP-only mode", completed.stdout + completed.stderr)
        self.assertEqual(calls.read_text().splitlines(), ["ensure"])

    def test_restart_targets_only_verified_mcp_owner_pids(self):
        source = (Path(__file__).parents[1] / "tools/live_game_start.sh").read_text()
        self.assertIn('kill -TERM "${mcp_owner_pids[@]}"', source)
        self.assertNotIn('kill -TERM "${game_pids[@]}"', source)

    def test_immediate_driver_preserves_arguments_and_skips_probe(self):
        root = Path(__file__).parents[1]
        source = (root / "tools/live_game_start.sh").read_text()
        body = source.split("run_requested_driver() {", 1)[1].split("\n}\n", 1)[0]
        base = Path(self.temp.name)
        output = base / "arguments.json"
        uv = base / "uv"
        uv.write_text("#!/usr/bin/env python3\nimport json,sys,pathlib\n"
                      f"pathlib.Path({str(output)!r}).write_text(json.dumps(sys.argv[1:]))\n")
        uv.chmod(0o755)
        args = ["--new-run", "--max-steps", "1", "--trace", "trace with spaces.jsonl"]
        script = ("set -euo pipefail\nrun_driver=1\nprobe=1\n"
                  f"repo_root={shlex.quote(str(root))}\nmcp_url='http://127.0.0.1:8080/mcp'\n"
                  f"driver_args=({shlex.join(args)})\n"
                  "run_probe() { exit 99; }\nrun_requested_driver() {" + body + "\n}\nrun_requested_driver\n")
        result = subprocess.run(["bash", "-c", script], env={**os.environ, "PATH": str(base) + os.pathsep + os.environ["PATH"]},
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertEqual(json.loads(output.read_text()), ["run", "--extra", "live-driver", "python",
            "tools/live_game_driver.py", "--mcp-url", "http://127.0.0.1:8080/mcp", *args])

    def test_immediate_driver_rejects_conflicting_launcher_modes(self):
        launcher = str(Path(__file__).parents[1] / "tools/live_game_start.sh")
        for args in (["--run", "--check"], ["--run", "--foreground"], ["--", "--new-run"]):
            result = subprocess.run([launcher, *args], capture_output=True, text=True)
            self.assertEqual(result.returncode, 2)

    def test_java_configuration_uses_environment_first_seam(self):
        source = (Path(__file__).parents[1] /
                  "mods/sts-model-inspector/src/main/java/stsmodelinspector/STSModelInspector.java").read_text()
        self.assertIn('environmentFirst(p, "STS_MODEL_INSPECTOR_ADVISOR", "advisor")', source)
        self.assertIn('environmentFirst(p, "STS_CTM_MODEL", "ctmModel")', source)
        self.assertIn('environmentFirst(p, "STS_LIVE_OOC_MODEL", "oocModel")', source)
        self.assertIn('System.getenv("STS_MODEL_INSPECTOR_CONFIG")', source)


if __name__ == "__main__":
    unittest.main()
