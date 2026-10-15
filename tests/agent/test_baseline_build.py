import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/agent/baseline_build.py"


def load_module():
    spec = importlib.util.spec_from_file_location("baseline_build", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BaselineBuildTests(unittest.TestCase):
    def test_export_accepts_empty_gitlink_directories_from_superproject_archive(self):
        module = load_module()
        revision = "1" * 40
        with tempfile.TemporaryDirectory() as temporary:
            destination = Path(temporary) / "source"
            destination.mkdir()
            (destination / "json").mkdir()
            (destination / "pybind11").mkdir()
            with mock.patch.object(module.subprocess, "run"), \
                 mock.patch.object(module, "extract_archive"), \
                 mock.patch.object(module, "capture", side_effect=[
                     f"160000 commit {revision}\tjson", "",
                     f"160000 commit {revision}\tpybind11", "",
                 ]):
                module.export_source("HEAD", destination)

    def test_defaults_build_one_combat_from_release_preset(self):
        module = load_module()
        args = module.parser().parse_args(["main"])
        self.assertEqual(args.ref, "main")
        self.assertEqual(args.target, "one_combat")
        self.assertEqual(args.configure_preset, "linux-gcc-release")
        self.assertEqual(args.build_preset, "linux-gcc-build")
        self.assertIsNone(args.artifact_name)

    def test_artifact_name_can_differ_from_cmake_target(self):
        module = load_module()
        args = module.parser().parse_args([
            "main", "--target", "unit-test", "--artifact-name", "test"
        ])
        self.assertEqual(args.target, "unit-test")
        self.assertEqual(args.artifact_name, "test")

    def test_preset_binary_dir_resolves_exported_source(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "CMakePresets.json").write_text(json.dumps({
                "configurePresets": [{
                    "name": "release", "binaryDir": "${sourceDir}/build/release"
                }],
                "buildPresets": [{
                    "name": "release-build", "configurePreset": "release"
                }],
            }), encoding="utf-8")
            self.assertEqual(
                module.preset_binary_dir(source, "release-build"),
                source / "build/release",
            )

    def test_unknown_build_preset_is_actionable(self):
        module = load_module()
        with tempfile.TemporaryDirectory() as temporary:
            source = Path(temporary)
            (source / "CMakePresets.json").write_text(
                '{"configurePresets": [], "buildPresets": []}', encoding="utf-8"
            )
            with self.assertRaisesRegex(module.BaselineBuildError, "unknown.*missing"):
                module.preset_binary_dir(source, "missing")


if __name__ == "__main__":
    unittest.main()
