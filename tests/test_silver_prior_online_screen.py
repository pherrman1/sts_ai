import importlib.util
import json
import tempfile
import unittest
from pathlib import Path


MODULE = Path(__file__).parents[1] / "tools/silver_prior_online_screen.py"
SPEC = importlib.util.spec_from_file_location("silver_prior_online_screen", MODULE)
screen = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(screen)


def telemetry(decisions=2, evaluations=1, loaded=1, puct=1, samples=None):
    fields = {
        "decisions": decisions, "simulations": decisions * 1000,
        "prior_model_loaded": loaded, "prior_eligible_decisions": evaluations,
        "prior_evaluations": evaluations, "prior_skipped_forced": 0,
        "prior_skipped_non_player_normal": 0, "prior_surface_failures": 0,
        "prior_inference_micros": 7000 * evaluations, "root_puct_decisions": puct,
        "transaction_decisions": 0, "transaction_failures": 0,
        "conversion_failures": 0, "semantic_resolution_failures": 0,
        "knowledge_failures": 0,
    }
    line = "[silver-combat] " + " ".join(f"{key}={value}" for key, value in fields.items())
    if samples is not None:
        line += " prior_inference_samples_micros=" + ",".join(map(str, samples))
    return line


class OnlineScreenParserTests(unittest.TestCase):
    def test_sums_all_combat_counters_and_latency_samples(self):
        result = screen.parse_telemetry("\n".join([
            telemetry(decisions=2, evaluations=1, puct=1, samples=[6000]),
            telemetry(decisions=3, evaluations=2, puct=2, samples=[7000, 9000]),
        ]), require_latency_samples=True)
        self.assertEqual(2, result["combat_count"])
        self.assertEqual(5, result["counters"]["decisions"])
        self.assertEqual(5000, result["counters"]["simulations"])
        self.assertEqual(3, result["counters"]["prior_evaluations"])
        self.assertEqual(3, result["counters"]["root_puct_decisions"])
        self.assertEqual(7000, result["prior_inference_mean_micros"])
        self.assertEqual(7000, result["prior_inference_median_micros"])
        self.assertEqual(9000, result["prior_inference_p95_micros"])

    def test_rejects_missing_samples_when_exact_percentiles_are_required(self):
        with self.assertRaisesRegex(ValueError, "lacks prior_inference_samples"):
            screen.parse_telemetry(telemetry(), require_latency_samples=True)

    def test_rejects_learned_prior_surface_or_puct_mismatch(self):
        with self.assertRaisesRegex(ValueError, "gauge prior_model_loaded"):
            screen.parse_telemetry("\n".join([
                telemetry(loaded=1), telemetry(loaded=0),
            ]))

    def test_artifact_hash_is_pinned(self):
        with tempfile.TemporaryDirectory() as directory:
            artifact = Path(directory) / "T2.native"
            artifact.write_bytes(b"wrong artifact")
            with self.assertRaisesRegex(ValueError, "SHA-256 mismatch"):
                screen.verify_artifact(artifact)

    def test_run_metadata_must_match_expected_commit(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "LEARNED-7.csv"
            log_path = root / "LEARNED-7.log"
            csv_path.write_text("seed,won,floor,act,hpEnd,maxHp,fightsLost,sec\n7,1,51,3,20,80,0,12.0\n")
            Path(str(csv_path) + ".meta.json").write_text(json.dumps({
                "nSeeds": 1, "asc": 0, "sims": 1000, "threads": 1,
                "seedBlock": {"lo": 7, "hi": 7},
                "config": {"executableGitSha": "old", "effectiveCombatBackend": "silver", "fairPlay": True,
                           "collectKeys": False, "searcher3": False,
                           "silverReuseCapMode": "allocated", "silverReuseCap": 32768,
                           "silverAdaptiveEnabled": False, "silverExactRootBudgets": True,
                           "silverExactVisitLock": False, "silverRhoRacing": False},
            }))
            log_path.write_text(telemetry() + "\nBEST win%=100\n")
            with self.assertRaisesRegex(ValueError, "executableGitSha mismatch"):
                screen.summarize_run("LEARNED", 7, csv_path, log_path, "reviewed-sha")

    def test_run_rejects_evaluation_puct_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            csv_path = root / "LEARNED-7.csv"
            log_path = root / "LEARNED-7.log"
            csv_path.write_text("seed,won,floor,act,hpEnd,maxHp,fightsLost,sec\n7,1,51,3,20,80,0,12.0\n")
            Path(str(csv_path) + ".meta.json").write_text(json.dumps({
                "nSeeds": 1, "asc": 0, "sims": 1000, "threads": 1,
                "seedBlock": {"lo": 7, "hi": 7},
                "config": {"executableGitSha": "reviewed-sha", "effectiveCombatBackend": "silver", "fairPlay": True,
                           "collectKeys": False, "searcher3": False,
                           "silverReuseCapMode": "allocated", "silverReuseCap": 32768,
                           "silverAdaptiveEnabled": False, "silverExactRootBudgets": True,
                           "silverExactVisitLock": False, "silverRhoRacing": False},
            }))
            log_path.write_text(telemetry(evaluations=2, puct=1) + "\nBEST win%=100\n")
            with self.assertRaisesRegex(ValueError, "do not match root-PUCT"):
                screen.summarize_run("LEARNED", 7, csv_path, log_path, "reviewed-sha")

    def test_screen_requires_all_32_pairs_and_pools_treatment_samples(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            summaries = []
            for seed in range(24100000, 24100032):
                for arm in ("CONTROL", "LEARNED"):
                    learned = arm == "LEARNED"
                    row = {
                        "arm": arm, "seed": seed,
                        "provenance": {"executable_git_sha": "reviewed-sha"},
                        "artifact_sha256_prelaunch": screen.EXPECTED_ARTIFACT_SHA256 if learned else None,
                        "telemetry": {
                            "latency_samples_available": True,
                            "prior_inference_samples_micros": [6000] if learned else [],
                            "counters": {
                                "decisions": 2, "simulations": 2000,
                                "prior_model_loaded": int(learned),
                                "prior_evaluations": int(learned),
                                "root_puct_decisions": int(learned),
                                "prior_inference_micros": 6000 if learned else 0,
                                "prior_surface_failures": 0, "transaction_failures": 0,
                                "conversion_failures": 0, "semantic_resolution_failures": 0,
                                "knowledge_failures": 0,
                            },
                        },
                    }
                    path = root / f"{arm}-{seed}.json"
                    path.write_text(json.dumps(row))
                    summaries.append(path)
            result = screen.summarize_screen(summaries, "reviewed-sha")
            self.assertEqual(64, result["runs"])
            self.assertEqual(32, result["arms"]["LEARNED"]["seed_count"])
            self.assertEqual(6000, result["arms"]["LEARNED"]["prior_inference_p95_micros"])
            with self.assertRaisesRegex(ValueError, "missing 1 arm/seed"):
                screen.summarize_screen(summaries[:-1], "reviewed-sha")


if __name__ == "__main__":
    unittest.main()
