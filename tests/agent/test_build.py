import importlib.util
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools/agent/build.py"


def load_module():
    spec = importlib.util.spec_from_file_location("agent_build", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class BuildTests(unittest.TestCase):
    def test_unwritable_ccache_falls_back_to_matching_plain_presets(self):
        module = load_module()
        args = module.parser().parse_args([
            "--configure-preset", "linux-gcc-debug-ccache",
            "--build-preset", "linux-gcc-debug-ccache-build",
        ])
        with mock.patch.object(
            module,
            "ccache_usable",
            return_value=(False, "cache directory is read-only"),
        ), \
             mock.patch("builtins.print") as output:
            module.apply_ccache_fallback(args)
        self.assertEqual(args.configure_preset, "linux-gcc-debug")
        self.assertEqual(args.build_preset, "linux-gcc-debug-build")
        self.assertIn("ccache_fallback=linux-gcc-debug", output.call_args.args[0])
        self.assertIn("cache directory is read-only", output.call_args.args[0])

    def test_ccache_fallback_forces_configure_for_new_binary_directory(self):
        module = load_module()
        args = module.parser().parse_args([
            "--configure-preset", "linux-gcc-debug-ccache",
            "--build-preset", "linux-gcc-debug-ccache-build",
            "--no-configure",
        ])
        with mock.patch.object(
            module,
            "ccache_usable",
            return_value=(False, "cache directory is read-only"),
        ), mock.patch("builtins.print") as output:
            module.apply_ccache_fallback(args)
        self.assertFalse(args.no_configure)
        self.assertIn("configure_forced=true", output.call_args.args[0])

    def test_usable_ccache_preserves_requested_presets(self):
        module = load_module()
        args = module.parser().parse_args([
            "--configure-preset", "linux-gcc-release-ccache",
            "--build-preset", "linux-gcc-release-ccache-build",
        ])
        with mock.patch.object(module, "ccache_usable", return_value=(True, "ok")):
            module.apply_ccache_fallback(args)
        self.assertEqual(args.configure_preset, "linux-gcc-release-ccache")
        self.assertEqual(args.build_preset, "linux-gcc-release-ccache-build")

    def test_default_commands_configure_then_build(self):
        module = load_module()
        args = module.parser().parse_args(["--target", "one_combat", "--target", "test"])
        self.assertEqual(module.cmake_commands(args), [
            ["cmake", "--preset", "linux-gcc-release"],
            ["cmake", "--build", "--preset", "linux-gcc-build", "--target", "one_combat", "test"],
        ])

    def test_native_cmake_is_preferred(self):
        module = load_module()
        args = module.parser().parse_args(["--no-configure", "--target", "one_combat"])
        with mock.patch.object(module.shutil, "which", return_value="/usr/bin/cmake"):
            with mock.patch.object(module.subprocess, "run") as invoke:
                self.assertEqual(module.run(args), 0)
        invoke.assert_called_once_with(
            ["/usr/bin/cmake", "--build", "--preset", "linux-gcc-build", "--target", "one_combat"],
            cwd=module.ROOT,
            check=True,
        )

    def test_windows_falls_back_to_one_wsl_command(self):
        module = load_module()
        args = module.parser().parse_args([])
        with mock.patch.object(module.shutil, "which", side_effect=[None, "C:/Windows/wsl.exe"]):
            with mock.patch.object(module.os, "name", "nt"):
                with mock.patch.object(module, "windows_to_wsl", return_value="/mnt/c/repo"):
                    with mock.patch.object(module.subprocess, "run") as invoke:
                        self.assertEqual(module.run(args), 0)
        argv = invoke.call_args.args[0]
        self.assertEqual(argv[:4], ["C:/Windows/wsl.exe", "-e", "bash", "-lc"])
        self.assertIn("cd /mnt/c/repo", argv[4])
        self.assertIn("cmake --preset linux-gcc-release", argv[4])
        self.assertIn("cmake --build --preset linux-gcc-build", argv[4])

    def test_windows_ccache_probe_runs_inside_selected_wsl_environment(self):
        module = load_module()
        args = module.parser().parse_args([
            "--configure-preset", "linux-gcc-debug-ccache",
            "--build-preset", "linux-gcc-debug-ccache-build",
        ])
        with mock.patch.object(module.shutil, "which", side_effect=[None, "wsl.exe"]), \
             mock.patch.object(module.os, "name", "nt"), \
             mock.patch.object(module, "wsl_ccache_usable", return_value=(True, "ok")) as probe, \
             mock.patch.object(module, "windows_to_wsl", return_value="/mnt/c/repo"), \
             mock.patch.object(module.subprocess, "run") as invoke:
            self.assertEqual(module.run(args), 0)
        probe.assert_called_once_with("wsl.exe")
        shell = invoke.call_args.args[0][4]
        self.assertIn("linux-gcc-debug-ccache", shell)
        self.assertIn("linux-gcc-debug-ccache-build", shell)

    def test_missing_toolchain_fails_actionably(self):
        module = load_module()
        args = module.parser().parse_args([])
        with mock.patch.object(module.shutil, "which", return_value=None):
            with mock.patch.object(module.os, "name", "posix"):
                with self.assertRaisesRegex(RuntimeError, "cmake is unavailable"):
                    module.run(args)


if __name__ == "__main__":
    unittest.main()
