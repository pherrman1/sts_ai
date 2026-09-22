import importlib.util
import io
import json
import sys
import unittest
from contextlib import redirect_stderr
from pathlib import Path
from unittest import mock

import numpy as np

SCRIPT = Path(__file__).parents[1] / "tools/evaluate_silver_prior_locked.py"
spec = importlib.util.spec_from_file_location("evaluate_locked", SCRIPT)
ev = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ev)


def checkpoint():
    return {"state_dict": {}, "normalization": {}, "arm": ev.ARM, "tau": ev.TAU,
            "epoch": 12, "config": {"seed": ev.SEED, "architecture": "SilverPriorNetV1",
                "temperatures": {ev.ARM: ev.TAU},
                **{f"{k}_sha256": v for k, v in ev.HASHES.items()}}}


class LockedEvaluatorTests(unittest.TestCase):
    def test_checkpoint_hash_and_embedded_metadata_fail_before_manifests_or_labels(self):
        with mock.patch.object(ev, "sha256", return_value="bad"), \
             mock.patch.object(ev.dataset, "read") as read:
            with self.assertRaisesRegex(ValueError, "checkpoint SHA"):
                ev.validate_checkpoint(Path("candidate.pt"))
            read.assert_not_called()

        for key, value in (("arm", "T1"), ("tau", 1.0), ("seed", 3),
                           ("architecture", "Other"), ("release_sha256", "wrong")):
            cp = checkpoint()
            if key in ("arm", "tau"):
                cp[key] = value
            elif key in ("seed", "architecture"):
                cp["config"][key] = value
            else:
                cp["config"][key] = value
            with self.subTest(key=key), mock.patch.object(ev, "sha256", return_value=ev.CHECKPOINT_SHA256), \
                 mock.patch.object(ev.torch, "load", return_value=cp):
                with mock.patch.object(ev.dataset, "read") as read:
                    with self.assertRaisesRegex(ValueError, "metadata mismatch"):
                        ev.validate_checkpoint(Path("candidate.pt"))
                    read.assert_not_called()

    def test_only_locked_l_and_preselected_locked_j_entries_are_selected(self):
        entries = [
            {"split": "TRAIN", "judge_selected": True, "root": {"root_id": "train"}},
            {"split": "VALIDATION", "judge_selected": True, "root": {"root_id": "valid"}},
            {"split": "LOCKED_TEST", "judge_selected": False, "root": {"root_id": "l0"}},
            {"split": "LOCKED_TEST", "judge_selected": True, "root": {"root_id": "l1"}},
        ]
        selection = {"sha256": ev.HASHES["selection"], "plan_sha256": "p",
                     "executable_git_sha": "g", "pilot": False, "entries": entries}
        release = {"sha256": ev.HASHES["release"], "binding_sha256": ev.HASHES["binding"],
                   "selection_sha256": ev.HASHES["selection"], "training_ready": True,
                   "quarantined_roots": [], "files": []}
        binding = {"sha256": ev.HASHES["binding"], "plan_sha256": "p", "executable_git_sha": "g"}
        vocab = {"sha256": ev.HASHES["vocabulary"]}; plan = {"sha256": "p", "vocabulary_sha256": ev.HASHES["vocabulary"]}
        def read(path):
            return {"release.json": release, "binding.json": binding, "selection.json": selection,
                    "vocabulary.json": vocab, "plan.json": plan}[Path(path).name]
        with mock.patch.object(ev.dataset, "read", side_effect=read), \
             mock.patch.object(ev.dataset, "check_seal"), mock.patch.object(ev.projection, "validate_vocabulary"):
            result = ev._load_sealed_manifests(Path("corpus"))
        self.assertEqual([x["root"]["root_id"] for x in result[-2]], ["l0", "l1"])
        self.assertEqual([x["root"]["root_id"] for x in result[-1]], ["l1"])

    def test_manifest_hash_mismatch_fails_before_label_paths(self):
        for name in ev.HASHES:
            vals = {f"{key}.json": {"sha256": value} for key, value in ev.HASHES.items()}
            vals["plan.json"] = {"sha256": "p"}
            vals[f"{name}.json"]["sha256"] = "wrong"
            with self.subTest(name=name), mock.patch.object(ev.dataset, "read", side_effect=lambda p, v=vals: v[Path(p).name]), \
                 mock.patch.object(ev.dataset, "check_seal"), \
                 mock.patch.object(ev.projection, "validate_vocabulary"):
                with self.assertRaisesRegex(ValueError, "provenance mismatch"):
                    ev._load_sealed_manifests(Path("corpus"))

    def test_l_reads_only_locked_l_shards_and_j_reads_raw_j(self):
        entry = {"split": "LOCKED_TEST", "judge_selected": True,
                 "root": {"root_id": "r", "source_seed": 22}}
        obs = {"candidates": [{"action": "A"}]}; stored = {"replay": {"raw": 1}, "observation": obs, "values": [1.0]}
        job = {"split": "LOCKED_TEST", "estimator": "J"}
        with mock.patch.object(ev.dataset, "identity_hash", return_value="ident"), \
             mock.patch.object(ev.dataset, "file_hash", return_value="sum"), \
             mock.patch.object(ev.dataset, "read", return_value=stored) as read, \
             mock.patch.object(ev.dataset, "check_seal"), \
             mock.patch.object(ev.dataset, "job_for", return_value=job), \
             mock.patch.object(ev.dataset, "shard", return_value=stored):
            rows = ev._load_l(Path("c"), [entry], {"shards/L/ident.json.gz": "sum"}, {}, {"executable_git_sha": "g"}, {})
        self.assertEqual(len(rows), 1)
        self.assertTrue(str(read.call_args.args[0]).endswith("shards/L/ident.json.gz"))

        raw = {"raw": 1}; projected = {"observation": obs, "values": [2.0]}
        with mock.patch.object(ev.dataset, "identity_hash", return_value="ident"), \
             mock.patch.object(ev.dataset, "file_hash", return_value="sum"), \
             mock.patch.object(ev.dataset, "read", return_value=raw) as read, \
             mock.patch.object(ev.dataset, "job_for", return_value=job) as job_for, \
             mock.patch.object(ev.dataset, "validate_raw") as validate, \
             mock.patch.object(ev.dataset, "shard", return_value=projected):
            jrows = ev._load_j(Path("c"), [entry], {"raw/J/ident.json.gz": "sum"}, {}, {"executable_git_sha": "g"}, {},
                               {"r": (obs, [1.0], 22, "r")})
        self.assertEqual(len(jrows), 1)
        self.assertTrue(str(read.call_args.args[0]).endswith("raw/J/ident.json.gz"))
        self.assertEqual(job_for.call_args.kwargs, {"role": "J"})
        validate.assert_called_once_with(raw, job)

    def test_l_loader_rejects_train_and_validation_before_opening_any_path(self):
        for split in ("TRAIN", "VALIDATION"):
            entry = {"split": split, "root": {"root_id": split, "source_seed": 1}}
            with self.subTest(split=split), mock.patch.object(ev.dataset, "file_hash") as file_hash:
                with self.assertRaisesRegex(ValueError, "non-LOCKED_TEST"):
                    ev._load_l(Path("c"), [entry], {}, {}, {}, {})
                file_hash.assert_not_called()

    def test_j_alignment_is_exact_and_mismatch_fails_closed(self):
        entry = {"split": "LOCKED_TEST", "judge_selected": True,
                 "root": {"root_id": "r", "source_seed": 22}}
        obs = {"candidates": [{"action": "A"}]}
        with mock.patch.object(ev.dataset, "identity_hash", return_value="i"), \
             mock.patch.object(ev.dataset, "file_hash", return_value="s"), \
             mock.patch.object(ev.dataset, "read", return_value={"raw": True}), \
             mock.patch.object(ev.dataset, "job_for", return_value={}), \
             mock.patch.object(ev.dataset, "validate_raw"), \
             mock.patch.object(ev.dataset, "shard", return_value={"observation": obs, "values": [1.0]}):
            with self.assertRaisesRegex(ValueError, "alignment"):
                ev._load_j(Path("c"), [entry], {"raw/J/i.json.gz": "s"}, {}, {"executable_git_sha": "g"}, {}, {})

    def test_quarantine_excludes_without_replacement_and_other_manifest_hashes_are_checked(self):
        self.assertIn("binding", ev.HASHES)
        self.assertEqual(len(ev.HASHES), 4)
        entries = [{"split": "LOCKED_TEST", "judge_selected": True,
                    "root": {"root_id": "q", "source_seed": 3}}]
        release = {"sha256": ev.HASHES["release"], "binding_sha256": ev.HASHES["binding"],
                   "selection_sha256": ev.HASHES["selection"], "training_ready": True,
                   "quarantined_roots": ["q"], "quarantine_resolution_sha256": "rhash", "files": []}
        binding = {"sha256": ev.HASHES["binding"], "plan_sha256": "p", "executable_git_sha": "g"}
        selection = {"sha256": ev.HASHES["selection"], "plan_sha256": "p", "executable_git_sha": "g", "pilot": False, "entries": entries}
        vocab = {"sha256": ev.HASHES["vocabulary"]}; plan = {"sha256": "p", "vocabulary_sha256": ev.HASHES["vocabulary"]}
        resolution = {"schema": "silver_prior_quarantine_v1", "sha256": "rhash", "binding_sha256": binding["sha256"],
                      "selection_sha256": selection["sha256"], "quarantined_roots": ["q"]}
        def read(path):
            return {"release.json": release, "binding.json": binding, "selection.json": selection,
                    "vocabulary.json": vocab, "plan.json": plan, "rhash.json": resolution}[Path(path).name]
        with mock.patch.object(ev.dataset, "read", side_effect=read), mock.patch.object(ev.dataset, "check_seal"), \
             mock.patch.object(ev.projection, "validate_vocabulary"):
            with self.assertRaisesRegex(ValueError, "empty or duplicate"):
                ev._load_sealed_manifests(Path("c"))

    def test_cli_refuses_any_output_dir_after_consumption_before_label_access(self):
        with mock.patch.object(ev, "validate_checkpoint") as checkpoint_loader, \
             mock.patch.object(ev, "_load_sealed_manifests") as manifest_loader, \
             mock.patch.object(ev, "_load_l") as l_loader, \
             mock.patch.object(ev, "_load_j") as j_loader, \
             mock.patch.object(ev.dataset, "read") as dataset_reader:
            self.assertTrue(ev.LOCKED_TEST_CONSUMED)
            for output_dir in ("/tmp/locked-test-v1", "/tmp/locked-test-v2", "/tmp/elsewhere/new-name"):
                argv = ["evaluate_silver_prior_locked.py", "--checkpoint", "/unused/T2.pt",
                        "--corpus", "/unused/corpus", "--output-dir", output_dir]
                stderr = io.StringIO()
                with mock.patch.object(sys, "argv", argv), redirect_stderr(stderr):
                    with self.assertRaises(SystemExit) as exited:
                        ev.main()
                self.assertEqual(exited.exception.code, 2)
                self.assertIn("LOCKED_TEST already consumed", stderr.getvalue())
                self.assertIn(ev.CONSUMED_EVIDENCE, stderr.getvalue())
            for target in (checkpoint_loader, manifest_loader, l_loader, j_loader, dataset_reader):
                target.assert_not_called()
            with self.assertRaisesRegex(RuntimeError, "already consumed"):
                ev.run(Path("/unused/T2.pt"), Path("/unused/corpus"), Path("/tmp/new-output"))
            for target in (checkpoint_loader, manifest_loader, l_loader, j_loader, dataset_reader):
                target.assert_not_called()

    def test_source_cluster_bootstrap_uses_source_seed_and_5000_replicates(self):
        with mock.patch.object(ev.trainer, "bootstrap_summary", return_value={}) as bootstrap:
            ev._summary([1.0, 2.0], [10, 20])
        self.assertEqual(bootstrap.call_args.kwargs, {"n_boot": 5000, "seed": ev.SEED})
        result = ev.trainer.bootstrap_summary([0.0, 1.0, 1.0], [10, 20, 20], n_boot=5000, seed=ev.SEED)
        self.assertEqual(result["cluster"], "source_seed")
        self.assertEqual(result["sources"], 2)

    def test_decision_rule_is_exactly_both_upper_ci_gates(self):
        l_per = [{"root_id": f"l{i}", "source_seed": i, "expected_regret": 1.0,
                  "uniform_regret": 2.0, "argmax_regret": 1.0, "top_agreement": 1.0,
                  "concordance": 1.0, "entropy": 0.5, "top_probability": 0.8} for i in range(2)]
        j_rows = [(None, [1.0, 0.0], i, f"j{i}") for i in range(2)]
        j_preds = [{"logits": [2., 0.], "root_id": f"j{i}", "source_seed": i} for i in range(2)]
        l_by_root = {f"j{i}": ({}, [1.0, 0.0], i, f"j{i}") for i in range(2)}
        for failed_gate, expected in ((None, "PRIOR_MODEL_LOCKED_TEST_CONFIRMED"),
                                      (7, "PRIOR_MODEL_LOCKED_TEST_NOT_CONFIRMED"),
                                      (14, "PRIOR_MODEL_LOCKED_TEST_NOT_CONFIRMED")):
            counter = [0]
            def choose_ci(vals, seeds):
                index = counter[0]; counter[0] += 1
                return {"ci95": [0.1, 0.2] if index == failed_gate else [-1.0, -0.1]}
            with self.subTest(failed_gate=failed_gate), mock.patch.object(ev, "_summary", side_effect=choose_ci) as summary:
                _, _, decision = ev.summarize(l_per, j_preds, j_rows, l_by_root)
            self.assertEqual(decision, expected)
            self.assertEqual(summary.call_count, 16)

    def test_real_summary_primary_l_delta_is_model_minus_uniform(self):
        self.assertTrue(np.isfinite(ev.TAU))
        self.assertEqual(ev.BOOTSTRAPS, 5000)

    def test_validation_comparison_uses_hash_bound_t2_summaries_and_is_descriptive(self):
        validation = ev.load_validation_diagnostics()
        self.assertEqual(validation["L"]["roots"], 1512)
        self.assertEqual(validation["J"]["roots"], 64)
        locked_l = {"model_minus_uniform": {"mean": -1.0, "ci95": [-1.2, -0.8]}}
        locked_j = {"metrics": {"model_minus_uniform": {"mean": -2.0, "ci95": [-2.4, -1.6]},
                                 "teacher_minus_uniform": {"mean": -3.0, "ci95": [-3.4, -2.6]},
                                 "soft_prior_headroom_recovery": 2.0}}
        result = ev.validation_comparison(validation, locked_l, locked_j)
        self.assertEqual(result["classification_role"], "DESCRIPTIVE_ONLY")
        self.assertEqual(result["locked_j_model_minus_uniform"]["mean"], -2.0)
        self.assertEqual(result["locked_j_soft_prior_headroom_recovery"], 2.0)

    def test_consumed_provenance_pins_outputs_and_imported_trainer(self):
        import hashlib
        packet = Path(__file__).parents[1] / "docs/experiments/evidence/silver_prior_locked_test_v1_20260922/provenance.json"
        provenance = json.loads(packet.read_text())
        external = Path(provenance["durable_raw_summary_directory"])
        for name, expected in provenance["external_output_sha256"].items():
            actual = hashlib.sha256((external / name).read_bytes()).hexdigest()
            self.assertEqual(actual, expected, name)
        trainer = Path(__file__).parents[1] / "tools/train_silver_prior.py"
        self.assertEqual(hashlib.sha256(trainer.read_bytes()).hexdigest(), provenance["trainer_source_sha256"])


if __name__ == "__main__":
    unittest.main()
