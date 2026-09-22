"""Crash-consistency and failure-evidence tests; no gameplay seeds are run."""
import copy
import contextlib
import io
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
            selection = d.seal({"schema": "silver_prior_selection_v1", "pilot": True,
                                "plan_sha256": "plan", "executable_git_sha": "sha", "entries": [entry]})
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


class FinalizationTest(unittest.TestCase):
    """Synthetic scientific-format labels isolate finalization; no native execution."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.corpus = Path(self.temp.name)
        evidence = ROOT / "docs/experiments/evidence/silver_prior_dataset_v1"
        self.plan = d.read(evidence / "plan.json")
        self.vocab = d.read(evidence / "vocabulary.json")
        self.fixture = d.read(evidence / "representative-fixture.json.gz")
        self.sha = "a" * 40
        self.binding = d.seal({"executable_git_sha": self.sha, "plan_sha256": self.plan["sha256"]})
        self.addCleanup(patch.stopall)
        patch.object(collect, "check_binding", return_value=(self.binding, self.plan, self.vocab)).start()
        self.sources = self.plan["sources"]

    def captures(self, overlap=False):
        # Two TRAIN, two VALIDATION, one TEST: quarantine can leave each split represented.
        roots = []
        for i, index in enumerate((0, 1, 384, 385, 448)):
            root = copy.deepcopy(self.fixture["replay"]["job"]["root"])
            seed = self.sources[index]["seed"]
            root.update(root_id=f"{seed}/1/1/0", source_seed=seed,
                        executable_git_sha=self.sha, capture_config=d.CAPTURE)
            root["state"]["state"]["player"]["curHp"] = 70 if overlap and i == 2 else 70 - i
            root["state_hash"] = f'{d.fnv(d.canonical(root["state"])):016x}'
            roots.append(root)
        return roots

    def complete(self, captures, seeds=None):
        for seed in seeds if seeds is not None else [s["seed"] for s in self.sources]:
            saved = d.seal({"schema": "silver_prior_source_v1", "binding_sha256": self.binding["sha256"],
                            "seed": seed, "returncode": 0, "seconds": 1,
                            "canary": f"benchmark_canary PASS backend=silver seeds=1 wins=0 sims=10000 seed_lo={seed}",
                            "capture": [r for r in captures if r["source_seed"] == seed]})
            d.publish(self.corpus / "sources" / f"{seed}.json.gz", saved)

    def selection(self, captures, pilot=False, filename="selection.json"):
        selected = d.select(self.plan, captures, self.sha, pilot)
        d.publish(self.corpus / filename, selected)
        return selected

    def labels(self, selected):
        for entry in selected["entries"]:
            key = d.identity_hash(entry["root"])
            for role in ("L", "J") if entry["judge_selected"] else ("L",):
                job = d.job_for(entry, self.plan, self.sha, role)
                raw = copy.deepcopy(self.fixture["replay"])
                raw["job"] = job
                base = d.fnv(f'{job["teacher_identity"]}/{job["root"]["root_id"]}/{role}')
                for action in raw["actions"]:
                    template = copy.deepcopy(action["replicates"][0])
                    template.update(requested_simulations=job["continuation_budget"],
                                    simulations=job["continuation_budget"], victories=0,
                                    terminal_after_action=False, terminal_victory=False,
                                    value=1.0, leaf_root_value=1.0,
                                    victory_baseline_correction=0.0, applied_baseline_correction=0.0)
                    action["mean_corrected_value"] = 1.0
                    action["replicates"] = [{**template, "index": i, "rng_identity": d.replicate_seed(base, i)}
                                            for i in range(8)]
                d.validate_raw(raw, job)
                d.publish(self.corpus / "raw" / role / f"{key}.json.gz", raw)
                if role == "L":
                    d.publish(self.corpus / "shards/L" / f"{key}.json.gz", d.shard(raw, job, self.vocab))
                    d.publish(self.corpus / "timing/L" / f"{key}.json", {"seconds": 1})

    def finalize(self, **kwargs):
        with contextlib.redirect_stdout(io.StringIO()):
            return collect.finalize(self.corpus, False, **kwargs)

    def test_pilot_selection_cannot_be_full_release(self):
        captures = self.captures()[:2]
        self.complete(captures, self.plan["pilot_sources"])
        selected = self.selection(captures, pilot=True)
        self.labels(selected)
        with self.assertRaisesRegex(ValueError, "phase binding"):
            self.finalize()
        self.assertFalse((self.corpus / "release.json").exists())

    def test_partial_full_selection_counts_only_completed_sources(self):
        captures = self.captures()[:1]
        self.complete(captures, self.plan["pilot_sources"])
        selected = self.selection(captures)
        self.labels(selected)
        report = self.finalize()
        self.assertEqual(report["source_seeds_completed"], 16)
        self.assertEqual(len(report["source_seeds_missing"]), 496)
        self.assertEqual(len(report["completed_zero_root_sources"]), 15)
        self.assertFalse(report["training_ready"])
        self.assertFalse((self.corpus / "release.json").exists())
        self.assertEqual(len(list((self.corpus / "reports").glob("*.json"))), 1)

    def test_partial_selection_rejected_even_when_all_sources_completed(self):
        captures = self.captures()
        self.complete(captures)
        self.labels(self.selection(captures[:1]))
        with self.assertRaisesRegex(ValueError, "completed source population"):
            self.finalize()
        self.assertFalse((self.corpus / "release.json").exists())

    def test_selection_binding_rejected(self):
        selection = d.select(self.plan, [], self.sha)
        for field, value in (("plan_sha256", "wrong"), ("executable_git_sha", "wrong"),
                             ("schema", "wrong"), ("pilot", True), ("pilot", 0)):
            changed = {k: v for k, v in selection.items() if k != "sha256"}
            changed[field] = value
            with self.subTest(field=field, value=value), self.assertRaises(ValueError):
                collect.require_selection_binding(d.seal(changed), self.binding, self.plan, False)

    def test_complete_zero_root_sources_are_verified_and_release_is_repeatable(self):
        captures = self.captures()
        self.complete(captures)
        self.labels(self.selection(captures))
        report = self.finalize()
        self.assertEqual(report["source_seeds_completed"], 512)
        self.assertEqual(len(report["completed_zero_root_sources"]), 507)
        self.assertTrue(report["training_ready"])
        original = (self.corpus / "release.json").read_bytes()
        self.assertEqual(self.finalize(), report)
        self.assertEqual((self.corpus / "release.json").read_bytes(), original)

    def test_overlap_attempt_then_explicit_quarantine_preserves_evidence(self):
        captures = self.captures(overlap=True)
        self.complete(captures)
        self.labels(self.selection(captures))
        original = {p: p.read_bytes() for folder in ("raw", "shards", "sources")
                    for p in (self.corpus / folder).rglob("*.gz")}
        report = self.finalize()
        self.assertFalse(report["training_ready"])
        self.assertFalse((self.corpus / "release.json").exists())
        self.assertFalse((self.corpus / "report.json").exists())
        attempts = list((self.corpus / "reports").glob("*.json"))
        self.assertEqual(len(attempts), 1)
        final = self.finalize(quarantine_overlap=True)
        self.assertTrue(final["training_ready"])
        self.assertEqual(final["retained_membership"]["decision_roots"], 3)
        release = d.read(self.corpus / "release.json")
        self.assertEqual(len(release["quarantined_roots"]), 2)
        self.assertTrue(attempts[0].exists())
        self.assertEqual(self.finalize(quarantine_overlap=True), final)
        for path, contents in original.items():
            self.assertEqual(path.read_bytes(), contents)
        for name, value in (("binding.json", self.binding), ("plan.json", self.plan),
                            ("vocabulary.json", self.vocab)):
            d.publish(self.corpus / name, value)
        loaded = list(d.load_training_corpus(self.corpus))
        self.assertEqual(len(loaded), 1)  # the other TRAIN root was quarantined

    def test_quarantine_cannot_skip_the_preserved_attempt(self):
        captures = self.captures(overlap=True)
        self.complete(captures)
        self.labels(self.selection(captures))
        with self.assertRaisesRegex(ValueError, "attempt report first"):
            self.finalize(quarantine_overlap=True)
        self.assertFalse((self.corpus / "release.json").exists())

    def test_quarantine_cannot_empty_required_split(self):
        captures = self.captures(overlap=True)
        captures.pop(3)  # VALIDATION's only remaining root will be quarantined
        self.complete(captures)
        self.labels(self.selection(captures))
        self.finalize()
        with self.assertRaisesRegex(ValueError, "empty a required split"):
            self.finalize(quarantine_overlap=True)
        self.assertFalse((self.corpus / "release.json").exists())


if __name__ == "__main__":
    unittest.main()
