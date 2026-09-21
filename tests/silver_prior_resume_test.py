"""Crash-consistency and failure-evidence tests; no gameplay seeds are run."""
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import silver_prior_dataset as d
import silver_prior_collect as collect


class ResumeTest(unittest.TestCase):
    def test_atomic_publish_and_conflict(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / "root.json.gz"
            d.publish(path, {"root": 1})
            original = path.read_bytes()
            d.publish(path, {"root": 1})
            self.assertEqual(original, path.read_bytes())
            with self.assertRaises(ValueError):
                d.publish(path, {"root": 2})
            self.assertEqual(original, path.read_bytes())

    def test_raw_commit_resumes_without_relabeling(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus = Path(temp)
            entry = {"root": {"root_id": "source/combat/decision"}, "split": "TRAIN", "judge_selected": False}
            selection = d.seal({"plan_sha256": "plan", "executable_git_sha": "sha", "entries": [entry]})
            d.publish(corpus / "pilot-selection.json", selection)
            binding = {"executable_git_sha": "sha", "label_binary": {"path": "fixture"}}
            job, raw = {"identity": "fixed"}, {"fixture_raw": True}
            native_calls = []

            def native(command, env):
                native_calls.append(command)
                d.publish(command[-1], raw)
                return subprocess.CompletedProcess(command, 0, "fixture", "")

            publish = d.publish

            def crash_on_timing(path, value):
                if "timing" in Path(path).parts:
                    raise InterruptedError("crash after atomic raw commit")
                publish(path, value)

            with patch.object(collect, "check_binding", return_value=(binding, {"sha256": "plan"}, {})), \
                 patch.object(d, "job_for", return_value=job), \
                 patch.object(d, "validate_raw"), patch.object(d, "shard", return_value={"fixture": True}), \
                 patch.object(collect, "guard_command", side_effect=native):
                with patch.object(d, "publish", side_effect=crash_on_timing):
                    with self.assertRaises(InterruptedError):
                        collect.label(corpus, True)
                collect.label(corpus, True)
                self.assertEqual(len(native_calls), 1)
                self.assertEqual(len(list((corpus / "shards/L").glob("*.gz"))), 1)
                self.assertEqual(len(list((corpus / "timing/L").glob("*.json"))), 1)

    def test_malformed_capture_is_retained(self):
        with tempfile.TemporaryDirectory() as temp:
            corpus = Path(temp)
            binding = {"sha256": "binding", "executable_git_sha": "sha", "source_binary": {"path": "fixture"}}

            def native(command, env):
                Path(env["STS_SILVER_ROOT_MECHANISM_CAPTURE"]).write_text('{"truncated":')
                return subprocess.CompletedProcess(command, 0, "stdout evidence", "stderr evidence")

            with patch.object(collect, "check_binding", return_value=(binding, {"pilot_sources": [1]}, {})), \
                 patch.object(collect, "guard_command", side_effect=native):
                with self.assertRaises(ValueError):
                    collect.capture(corpus, True)
            failure = d.read(corpus / "failures/source-1.json")
            self.assertEqual(failure["stdout"], "stdout evidence")
            self.assertEqual((corpus / failure["attempt"] / "roots.jsonl").read_text(), '{"truncated":')

    def test_full_collection_rejected_locally(self):
        with patch.object(collect.socket, "gethostname", return_value="local"):
            with self.assertRaises(ValueError):
                collect.require_execution_host(False)


if __name__ == "__main__":
    unittest.main()
