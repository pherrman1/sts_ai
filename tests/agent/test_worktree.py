import argparse
import contextlib
import importlib.util
import io
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "tools" / "agent" / "worktree.py"


def load_module():
    spec = importlib.util.spec_from_file_location("agent_worktree", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class WorktreeTests(unittest.TestCase):
    def test_parser_requires_explicit_branch_or_detach(self):
        module = load_module()
        with contextlib.redirect_stderr(io.StringIO()), self.assertRaises(SystemExit):
            module.parser().parse_args(["create", "somewhere"])
        args = module.parser().parse_args(
            ["create", "somewhere", "--branch", "fix/example", "--start-point", "main"]
        )
        self.assertEqual(args.branch, "fix/example")
        self.assertFalse(args.detach)
        self.assertEqual(args.start_point, "main")

    def test_status_parser_preserves_clean_prefix_and_pins(self):
        module = load_module()
        revisions = {"json": "1" * 40, "pybind11": "2" * 40}
        with mock.patch.object(module, "require_checkout", return_value=Path("/repo")), \
             mock.patch.object(module, "pinned_revisions", return_value=revisions), \
             mock.patch.object(module, "status_records", return_value={
                 "json": (" ", revisions["json"]),
                 "pybind11": (" ", revisions["pybind11"]),
             }), \
             mock.patch.object(module, "git", side_effect=["/repo/json", "/repo/pybind11"]), \
             mock.patch("builtins.print") as output:
            module.check(Path("/repo"))
        output.assert_called_once()
        self.assertIn("json=111111111111", output.call_args.args[0])

    def test_check_rejects_uninitialized_or_wrong_revision(self):
        module = load_module()
        revisions = {"json": "1" * 40, "pybind11": "2" * 40}
        records = {"json": ("-", revisions["json"]), "pybind11": ("+", "3" * 40)}
        with mock.patch.object(module, "require_checkout", return_value=Path("/repo")), \
             mock.patch.object(module, "pinned_revisions", return_value=revisions), \
             mock.patch.object(module, "status_records", return_value=records):
            with self.assertRaisesRegex(module.WorktreeError, "uninitialized.*wrong revision"):
                module.check(Path("/repo"))

    def test_create_initializes_after_git_worktree_add(self):
        module = load_module()
        args = argparse.Namespace(
            path=Path("new-worktree"), branch="fix/example", detach=False, start_point="main"
        )
        with mock.patch.object(Path, "exists", return_value=False), \
             mock.patch.object(module, "git") as git, \
             mock.patch.object(module, "initialize") as initialize, \
             mock.patch("builtins.print"):
            module.create(args)
        git.assert_called_once_with(
            module.ROOT, "worktree", "add", "-b", "fix/example",
            str(Path("new-worktree").resolve()), "main"
        )
        initialize.assert_called_once_with(Path("new-worktree").resolve())

    def test_initialize_seeds_linked_worktree_from_primary_module_repo(self):
        module = load_module()
        worktree = Path("/repo/linked")
        seed = Path("/repo/.git/modules/json")
        calls = []

        def fake_git(cwd, *args, capture=False):
            calls.append((Path(cwd), args, capture))
            return "https://example.test/json" if args[:4] == (
                "config", "-f", ".gitmodules", "--get"
            ) else ""

        with mock.patch.object(module, "require_checkout", return_value=worktree), \
             mock.patch.object(module, "pinned_revisions", return_value={"json": "1" * 40}), \
             mock.patch.object(module, "local_seed_repo", return_value=seed), \
             mock.patch.object(module, "check"), \
             mock.patch.object(module, "git", side_effect=fake_git), \
             mock.patch.object(Path, "exists", return_value=False), \
             mock.patch("builtins.print"):
            module.initialize(worktree)
        update = next(call for call in calls if "update" in call[1])
        self.assertIn("protocol.file.allow=always", update[1])
        self.assertIn(f"submodule.json.url={seed}", update[1])
        self.assertIn(
            (worktree / "json", ("remote", "set-url", "origin", "https://example.test/json"), False),
            calls,
        )

    def test_create_rolls_back_worktree_and_new_branch_when_initialize_fails(self):
        module = load_module()
        target = Path("new-worktree").resolve()
        args = argparse.Namespace(
            path=target, branch="fix/example", detach=False, start_point="main"
        )
        with mock.patch.object(Path, "exists", return_value=False), \
             mock.patch.object(module, "initialize", side_effect=RuntimeError("clone failed")), \
             mock.patch.object(module, "git") as git:
            with self.assertRaisesRegex(module.WorktreeError, "creation was rolled back"):
                module.create(args)
        self.assertIn(
            mock.call(module.ROOT, "worktree", "remove", "--force", str(target)),
            git.call_args_list,
        )
        self.assertIn(mock.call(module.ROOT, "branch", "-D", "fix/example"), git.call_args_list)

    def test_remove_never_deinitializes_shared_submodule_configuration(self):
        module = load_module()
        target = Path(tempfile.gettempdir()) / "linked"
        calls = []

        def fake_git(cwd, *args, capture=False):
            calls.append((Path(cwd), args, capture))
            if args[:2] == ("status", "--porcelain"):
                return ""
            return ""

        with mock.patch.object(module, "require_checkout", return_value=target), \
             mock.patch.object(module, "registered_worktrees", return_value=[module.ROOT, target]), \
             mock.patch.object(module, "git", side_effect=fake_git), \
             mock.patch.object(module, "check") as check, \
             mock.patch("builtins.print"):
            module.remove(target)
        self.assertNotIn((target, ("submodule", "deinit", "-f", "--all"), False), calls)
        self.assertIn(
            (module.ROOT, ("worktree", "remove", "--force", str(target)), False), calls
        )
        check.assert_called_once_with(module.ROOT)

    def test_remove_refuses_dirty_worktree_before_removal(self):
        module = load_module()
        target = Path(tempfile.gettempdir()) / "linked"
        with mock.patch.object(module, "require_checkout", return_value=target), \
             mock.patch.object(module, "registered_worktrees", return_value=[module.ROOT, target]), \
             mock.patch.object(module, "git", return_value=" M source.cpp") as git:
            with self.assertRaisesRegex(module.WorktreeError, "refusing to remove dirty"):
                module.remove(target)
        self.assertFalse(any("remove" in call.args for call in git.call_args_list))

    def test_main_reports_subprocess_failure(self):
        module = load_module()
        failure = subprocess.CalledProcessError(1, ["git"])
        with mock.patch.object(module, "run", side_effect=failure), \
             contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(module.main(["check"]), 1)


if __name__ == "__main__":
    unittest.main()
