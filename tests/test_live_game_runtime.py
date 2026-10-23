import json
import os
import shlex
import stat
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tools.live_game_runtime import (CTM_NAME, CTM_FAST_NAME, CTM_STACK_KEYS,
    CTM_CURRENT_NAME, CTM_CURRENT_FAST_NAME, CTM_A20_NAME, CTM_A20_FAST_NAME,
    CTM_QUALIFIED_KEYS, OOC_NAME, OOC_WIN_NAME, OOC_WIN_SOURCE, LEGACY_OOC_WIN_NAME,
    OOC_FLOOR_NAME, ARM_C_NAME, ACT4_SURVIVAL_NAME, CTM_CALIBRATION_NAME,
    ROLLOUT_ROOT_TABLE_NAME, LEGACY_ROLLOUT_ROOT_TABLE_NAME, RuntimeFailure, RuntimeManager, sha256)


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
        (models / CTM_FAST_NAME).write_bytes(b"fast-ctm")
        (models / OOC_NAME).write_bytes(b"ooc")
        (self.repo / OOC_WIN_SOURCE).parent.mkdir(parents=True, exist_ok=True)
        (self.repo / OOC_WIN_SOURCE).write_bytes(b"win")
        (root_models / OOC_FLOOR_NAME).write_bytes(b"floor")
        (root_models / ROLLOUT_ROOT_TABLE_NAME).write_bytes(b"root-table")
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
        self.assertEqual(manifest["oocWinModelName"], OOC_WIN_NAME)
        self.assertEqual(manifest["oocFloorModelSha256"], sha256(release / f"models/{OOC_FLOOR_NAME}"))
        self.assertEqual((release / f"models/{ROLLOUT_ROOT_TABLE_NAME}").read_bytes(), b"root-table")
        self.assertEqual(manifest["rolloutRootTableSha256"],
                         sha256(release / f"models/{ROLLOUT_ROOT_TABLE_NAME}"))
        self.assertEqual(manifest["advisorSha256"], sha256(release / "one_combat_advisor"))
        self.assertNotIn("/.codex/worktrees/", json.dumps(self.manager.desired_config(manifest)))
        self.assertFalse(any(path.name.startswith(".current.") for path in self.manager.root.iterdir()))

    def test_new_stack_pins_both_models_and_configures_fast_primary(self):
        manifest = self.install()
        self.assertEqual(manifest["ctmPrimary"], CTM_FAST_NAME)
        self.assertIs(manifest["ctmActiveLizard"], True)
        self.assertEqual(manifest["ctmFastSha256"], sha256(self.manager.current / "models" / CTM_FAST_NAME))
        self.assertEqual(self.manager.desired_config(manifest)["ctmModel"],
                         str(self.manager.current / "models" / CTM_FAST_NAME))
        active = self.manager.record_active(Path(self.temp.name) / "missing.jar", os.getpid())
        for key in CTM_STACK_KEYS:
            self.assertEqual(active[key], manifest[key])

    def test_arm_c_is_explicit_pinned_self_contained_and_preserved_on_refresh(self):
        first = self.install()
        self.assertNotIn("armCModelSha256", first)
        source = Path(self.temp.name) / "studentc.bin"
        source.write_bytes(b"arm-c-fixture")
        with mock.patch("tools.live_game_runtime.ARM_C_SHA256", sha256(source)):
            manifest = self.manager.install(self.advisor, arm_c_source=source)
            self.assertNotEqual(first["runtimeId"], manifest["runtimeId"])
            self.assertEqual((self.manager.current / "models" / ARM_C_NAME).read_bytes(), source.read_bytes())
            self.assertEqual(manifest["armCModelSha256"], sha256(source))
            source.unlink()
            self.assertEqual(self.manager.install(self.advisor), manifest)
            (self.manager.current / "models" / ARM_C_NAME).write_bytes(b"corrupt")
            with self.assertRaisesRegex(RuntimeFailure, "hash mismatch"):
                self.manager.validate_release()

    def test_wrong_arm_c_weights_fail_before_activation(self):
        before = self.install()
        source = Path(self.temp.name) / "wrong.bin"
        source.write_bytes(b"different-model")
        with self.assertRaisesRegex(RuntimeFailure, "Arm C SHA-256"):
            self.manager.install(self.advisor, arm_c_source=source)
        self.assertEqual(self.manager.validate_release(), before)

    def test_active_arm_c_selection_requires_matching_explicit_weights(self):
        self.install()
        source = Path(self.temp.name) / "studentc.bin"
        source.write_bytes(b"arm-c-fixture")
        with mock.patch("tools.live_game_runtime.ARM_C_SHA256", sha256(source)):
            self.manager.install(self.advisor, arm_c_source=source)
            for override, expected in ((None, False), ("", False), ("/missing", False), (str(source), True)):
                env = {k: v for k, v in os.environ.items() if k != "STS_LIVE_OOC_ARM_C"}
                if override is not None:
                    env["STS_LIVE_OOC_ARM_C"] = override
                with self.subTest(override=override), mock.patch.dict(os.environ, env, clear=True):
                    active = self.manager.record_active(Path(self.temp.name) / "missing.jar", os.getpid())
                    self.assertIs(active["armCMatchesInstalled"], expected)

    def qualified_sources(self):
        for name in (CTM_CURRENT_NAME, CTM_CURRENT_FAST_NAME, CTM_A20_NAME, CTM_A20_FAST_NAME):
            (self.repo / "selfplay/models" / name).write_bytes(name.encode())
        (self.repo / "models" / ACT4_SURVIVAL_NAME).write_bytes(b"act4-survival")
        (self.repo / "models" / CTM_CALIBRATION_NAME).write_bytes(b"ctm-calibration")

    def test_qualified_ctm_pins_both_ascensions_and_survives_refresh(self):
        self.qualified_sources()
        manifest = self.manager.install(self.advisor, qualified_ctm=True)
        self.assertEqual(manifest["ctmStackVersion"], 2)
        self.assertEqual(manifest["ctmPrimary"], CTM_CURRENT_FAST_NAME)
        self.assertEqual(manifest["ctmFallback"], CTM_CURRENT_NAME)
        self.assertEqual(manifest["ctmA20Primary"], CTM_A20_FAST_NAME)
        self.assertEqual(manifest["ctmA20Fallback"], CTM_A20_NAME)
        self.assertEqual((self.manager.current / "models" / ACT4_SURVIVAL_NAME).read_bytes(), b"act4-survival")
        self.assertEqual(manifest["ctmAct4SurvivalSha256"], sha256(self.manager.current / "models" / ACT4_SURVIVAL_NAME))
        self.assertEqual((self.manager.current / "models" / CTM_CALIBRATION_NAME).read_bytes(), b"ctm-calibration")
        self.assertEqual(manifest["ctmCalibrationSha256"], sha256(self.manager.current / "models" / CTM_CALIBRATION_NAME))
        self.assertEqual(self.manager.install(self.advisor), manifest)
        env = {"STS_LIVE_CTM_A20_MODEL": str(self.manager.current / "models" / CTM_A20_FAST_NAME),
               "STS_LIVE_CTM_A20_FALLBACK_MODEL": str(self.manager.current / "models" / CTM_A20_NAME)}
        with mock.patch.dict(os.environ, env):
            active = self.manager.record_active(Path(self.temp.name) / "missing.jar", os.getpid())
            self.assertIs(active["ctmMatchesInstalled"], True)
        with mock.patch.dict(os.environ, {**env, "STS_LIVE_CTM_A20_MODEL": ""}):
            active = self.manager.record_active(Path(self.temp.name) / "missing.jar", os.getpid())
            self.assertIs(active["ctmMatchesInstalled"], False)

    def test_qualified_ctm_partial_receipts_and_corruption_fail_closed(self):
        self.qualified_sources()
        manifest = self.manager.install(self.advisor, qualified_ctm=True)
        receipt = self.manager.current / "manifest.json"
        for missing in (*CTM_STACK_KEYS, *CTM_QUALIFIED_KEYS):
            with self.subTest(missing=missing):
                receipt.write_text(json.dumps({k: v for k, v in manifest.items() if k != missing}))
                with self.assertRaises(RuntimeFailure):
                    self.manager.validate_release()
        receipt.write_text(json.dumps(manifest))
        for name in (CTM_CURRENT_NAME, CTM_CURRENT_FAST_NAME, CTM_A20_NAME, CTM_A20_FAST_NAME):
            with self.subTest(corrupt=name):
                artifact = self.manager.current / "models" / name
                old = artifact.read_bytes()
                artifact.write_bytes(b"corrupt")
                with self.assertRaisesRegex(RuntimeFailure, "hash mismatch"):
                    self.manager.validate_release()
                artifact.write_bytes(old)

    def test_missing_a20_source_preserves_previous_release(self):
        before = self.install()
        self.qualified_sources()
        (self.repo / "selfplay/models" / CTM_A20_NAME).unlink()
        with self.assertRaisesRegex(RuntimeFailure, "A20 CTM model missing"):
            self.manager.install(self.advisor, qualified_ctm=True)
        self.assertEqual(self.manager.validate_release(), before)

    def test_repair_never_downgrades_selected_ctm_stack_to_cached_legacy(self):
        self.install()
        self.qualified_sources()
        self.manager.install(self.advisor, qualified_ctm=True)
        (self.manager.current / "one_combat_advisor").write_bytes(b"broken")
        with mock.patch.object(self.manager, "build_advisor", return_value=self.advisor):
            repaired = self.manager.ensure()
        self.assertEqual(repaired["ctmStackVersion"], 2)
        self.assertEqual(self.manager.validate_release(), repaired)

    def test_repair_preserves_qualified_selection_with_missing_or_invalid_stack_version(self):
        self.install()
        self.qualified_sources()
        selected = self.manager.install(self.advisor, qualified_ctm=True)
        for version in (None, "2", 1):
            with self.subTest(version=version):
                partial = dict(selected)
                if version is None:
                    partial.pop("ctmStackVersion")
                else:
                    partial["ctmStackVersion"] = version
                (self.manager.current / "manifest.json").write_text(json.dumps(partial))
                with mock.patch.object(self.manager, "build_advisor", return_value=self.advisor):
                    repaired = self.manager.ensure()
                self.assertEqual(repaired["ctmStackVersion"], 2)
                self.assertEqual(self.manager.validate_release(), repaired)
                selected = repaired

    def test_legacy_single_model_manifest_remains_valid(self):
        manifest = self.install()
        for key in CTM_STACK_KEYS:
            del manifest[key]
        path = self.manager.current / "manifest.json"
        path.write_text(json.dumps(manifest))
        (self.manager.current / "models" / CTM_FAST_NAME).unlink()
        self.assertEqual(self.manager.validate_release(), manifest)
        self.assertEqual(self.manager.desired_config(manifest)["ctmModel"],
                         str(self.manager.current / "models" / CTM_NAME))

    def test_partial_stack_never_downgrades_to_legacy(self):
        manifest = self.install()
        path = self.manager.current / "manifest.json"
        for missing in CTM_STACK_KEYS:
            with self.subTest(missing=missing):
                partial = {key: value for key, value in manifest.items() if key != missing}
                path.write_text(json.dumps(partial))
                with self.assertRaisesRegex(RuntimeFailure, "CTM stack manifest"):
                    self.manager.validate_release()
        for key, value in (("ctmActiveLizard", False), ("ctmPrimary", "../foreign"),
                           ("ctmStackVersion", True), ("ctmFastSha256", "bad")):
            path.write_text(json.dumps({**manifest, key: value}))
            with self.assertRaisesRegex(RuntimeFailure, "CTM stack manifest"):
                self.manager.validate_release()

    def test_fast_model_corruption_and_cache_identity(self):
        first = self.install()
        fast = self.manager.current / "models" / CTM_FAST_NAME
        fast.write_bytes(b"corrupt")
        with self.assertRaisesRegex(RuntimeFailure, "hash mismatch"):
            self.manager.validate_release()
        (self.repo / "selfplay/models" / CTM_FAST_NAME).write_bytes(b"changed-fast")
        second = self.install()
        self.assertNotEqual(first["ctmFastSha256"], second["ctmFastSha256"])
        self.assertNotEqual(first["runtimeId"], second["runtimeId"])

    def test_missing_fast_model_fails_before_activation(self):
        (self.repo / "selfplay/models" / CTM_FAST_NAME).unlink()
        with self.assertRaisesRegex(RuntimeFailure, "tracked CTM fast model missing"):
            self.install()
        self.assertFalse(self.manager.current.exists())

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
        (self.repo / OOC_WIN_SOURCE).unlink()
        with self.assertRaisesRegex(RuntimeFailure, "tracked OOC win model missing"):
            self.install()

    def test_pre_x2b_release_keeps_its_legacy_win_model_name(self):
        manifest = self.install()
        release = self.manager.current.resolve()
        (release / f"models/{OOC_WIN_NAME}").rename(release / f"models/{LEGACY_OOC_WIN_NAME}")
        del manifest["oocWinModelName"]
        (release / "manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(self.manager.validate_release(), manifest)
        self.assertEqual(self.manager.desired_config(manifest)["oocWinModel"],
                         str(self.manager.current / "models" / LEGACY_OOC_WIN_NAME))

    def test_pre_gen7f_release_keeps_its_legacy_root_table_name(self):
        manifest = self.install()
        self.assertEqual(manifest["rolloutRootTableName"], ROLLOUT_ROOT_TABLE_NAME)
        release = self.manager.current.resolve()
        (release / f"models/{ROLLOUT_ROOT_TABLE_NAME}").rename(release / f"models/{LEGACY_ROLLOUT_ROOT_TABLE_NAME}")
        del manifest["rolloutRootTableName"]
        (release / "manifest.json").write_text(json.dumps(manifest))
        self.assertEqual(self.manager.validate_release(), manifest)

    def test_missing_source_floor_model_fails_clearly(self):
        (self.repo / f"models/{OOC_FLOOR_NAME}").unlink()
        with self.assertRaisesRegex(RuntimeFailure, "tracked OOC floor model missing"):
            self.install()

    def test_missing_source_rollout_root_table_fails_clearly(self):
        (self.repo / f"models/{ROLLOUT_ROOT_TABLE_NAME}").unlink()
        with self.assertRaisesRegex(RuntimeFailure, "tracked rollout root table model missing"):
            self.install()

    def test_tampered_rollout_root_table_invalidates_release(self):
        self.install()
        (self.manager.current / "models" / ROLLOUT_ROOT_TABLE_NAME).write_bytes(b"changed")
        with self.assertRaisesRegex(RuntimeFailure, "runtime artifact hash mismatch"):
            self.manager.validate_release()

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

    def test_active_override_does_not_claim_installed_stack_match(self):
        self.install()
        for overrides in ({"STS_CTM_MODEL": str(self.manager.current / "models" / CTM_NAME)},
                          {"STS_CTM_ACTIVE_LIZARD": "0"},
                          {"STS_CTM_BREW_FALLBACK_MODEL": "/missing/model"}):
            with self.subTest(overrides=overrides), mock.patch.dict(os.environ, overrides):
                active = self.manager.record_active(Path(self.temp.name) / "inspector.jar", os.getpid())
                self.assertFalse(active["ctmMatchesInstalled"])
                self.assertEqual(active["ctmEnvironmentOverrides"], overrides)
                self.assertFalse(self.manager.status()["activeRuntimeMatchesCurrent"])

    def test_launcher_primary_uses_manifest_and_preserves_explicit_overrides(self):
        self.install()
        source = (Path(__file__).parents[1] / "tools/live_game_start.sh").read_text()
        block = source.split("  # ensure/install validated this manifest;", 1)[1].split(
            '  # Public X2-B (ADR-0029)', 1)[0]
        for primary in (CTM_FAST_NAME, None):
            manifest = self.manager.load_manifest()
            if primary is None:
                for key in CTM_STACK_KEYS:
                    manifest.pop(key, None)
            (self.manager.current / "manifest.json").write_text(json.dumps(manifest))
            for override in (None, "/explicit/model", ""):
                env = {key: value for key, value in os.environ.items() if key != "STS_CTM_MODEL"}
                if override is not None:
                    env["STS_CTM_MODEL"] = override
                script = ('set -euo pipefail\nruntime_root=' + shlex.quote(str(self.manager.root))
                          + '\n# ensure/install validated this manifest;' + block
                          + '\nprintf "%s" "$STS_CTM_MODEL"\n')
                result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
                self.assertEqual(result.returncode, 0, result.stderr)
                self.assertEqual(result.stdout, override if override is not None else
                                 str(self.manager.current / "models" / (primary or CTM_NAME)))

    def test_qualified_launcher_preserves_explicit_primary_without_injecting_other_models(self):
        self.qualified_sources()
        self.manager.install(self.advisor, qualified_ctm=True)
        source = (Path(__file__).parents[1] / "tools/live_game_start.sh").read_text()
        block = source.split("  # ensure/install validated this manifest;", 1)[1].split(
            '  # Public X2-B (ADR-0029)', 1)[0]
        keys = ("STS_CTM_MODEL", "STS_CTM_BREW_FALLBACK_MODEL", "STS_LIVE_CTM_A20_MODEL", "STS_LIVE_CTM_A20_FALLBACK_MODEL")
        for override in (None, "", "/explicit/legacy.native"):
            env = {k: v for k, v in os.environ.items() if k not in keys}
            if override is not None:
                env[keys[0]] = override
            report = "import os,json;print(json.dumps([os.environ.get(k) for k in " + repr(keys) + "]))"
            script = ('set -euo pipefail\nruntime_root=' + shlex.quote(str(self.manager.root))
                      + '\n# ensure/install validated this manifest;' + block
                      + '\npython3 -c ' + shlex.quote(report))
            result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stderr)
            actual = json.loads(result.stdout)
            if override is None:
                names = (CTM_CURRENT_FAST_NAME, CTM_CURRENT_NAME, CTM_A20_FAST_NAME, CTM_A20_NAME)
                self.assertEqual(actual, [str(self.manager.current / "models" / name) for name in names])
            else:
                self.assertEqual(actual, [override, None, None, None])

    def test_build_advisor_packages_only_wrapper_selected_fallback_preset(self):
        fallback = self.repo / "build/linux-gcc-release/one_combat_advisor"
        requested = self.repo / "build/linux-gcc-release-ccache/one_combat_advisor"
        fallback.parent.mkdir(parents=True)
        requested.parent.mkdir(parents=True)
        fallback.write_text("fallback")
        requested.write_text("wrong-newer")
        fallback.chmod(fallback.stat().st_mode | stat.S_IXUSR)
        requested.chmod(requested.stat().st_mode | stat.S_IXUSR)
        os.utime(requested, (fallback.stat().st_mtime + 10, fallback.stat().st_mtime + 10))
        wrapper_output = ("ccache_fallback=linux-gcc-release build_preset=linux-gcc-build "
                          "configure_forced=false reason=test\nbuild_route=native root=test\n")
        with mock.patch("tools.live_game_runtime.run"), \
             mock.patch("tools.live_game_runtime.run_output", return_value=wrapper_output) as build:
            self.assertEqual(self.manager.build_advisor(), fallback)
        command = build.call_args.args[0]
        self.assertEqual(command[command.index("--configure-preset") + 1], "linux-gcc-release-ccache")
        self.assertEqual(command[command.index("--build-preset") + 1], "linux-gcc-release-ccache-build")

    def test_build_advisor_packages_requested_release_without_fallback(self):
        requested = self.repo / "build/linux-gcc-release-ccache/one_combat_advisor"
        requested.parent.mkdir(parents=True)
        requested.write_text("release")
        requested.chmod(requested.stat().st_mode | stat.S_IXUSR)
        with mock.patch("tools.live_game_runtime.run"), \
             mock.patch("tools.live_game_runtime.run_output", return_value="build_route=native\n"):
            self.assertEqual(self.manager.build_advisor(), requested)

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
        self.assertIn('ctmPrimaryModel(p, System.getenv("STS_CTM_MODEL"))', source)
        self.assertIn('environmentFirst(p, "STS_LIVE_OOC_MODEL", "oocModel")', source)
        self.assertIn('System.getenv("STS_MODEL_INSPECTOR_CONFIG")', source)


if __name__ == "__main__":
    unittest.main()
