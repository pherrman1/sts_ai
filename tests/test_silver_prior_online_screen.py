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
        "transaction_subdecisions": 0, "transaction_decisions": 0, "transaction_failures": 0,
        "conversion_failures": 0, "semantic_resolution_failures": 0,
        "knowledge_failures": 0,
    }
    line = "[silver-combat] " + " ".join(f"{key}={value}" for key, value in fields.items())
    if samples is not None:
        line += " prior_inference_samples_micros=" + ",".join(map(str, samples))
    return line


class OnlineScreenParserTests(unittest.TestCase):
    def test_transaction_simulations_count_replacement_subdecisions(self):
        counters = {"decisions": 43, "transaction_subdecisions": 2,
                    "transaction_decisions": 1}
        self.assertEqual(44, screen.effective_search_decisions(counters))

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
                        "outcome": {"won": int(learned), "floor": 40 + int(learned),
                                    "hpEnd": 50 + int(learned), "fightsLost": int(not learned),
                                    "sec": 12.0 + int(learned)},
                        "provenance": {"executable_git_sha": "reviewed-sha",
                                       "binary_sha256": "a" * 64},
                        "artifact_sha256_prelaunch": screen.EXPECTED_ARTIFACT_SHA256,
                        "run_flags": dict(screen.FROZEN_RUN_FLAGS),
                        "arm_specific_flags": {
                            "STS_SILVER_ROOT_PRIOR_MODEL": "frozen artifact" if learned else "unset"
                        },
                        "telemetry": {
                            "latency_samples_available": True,
                            "prior_inference_samples_micros": [6000] if learned else [],
                            "counters": {
                                "decisions": 2, "simulations": 2000,
                                "prior_model_loaded": int(learned),
                                "prior_evaluations": int(learned),
                                "root_puct_decisions": int(learned),
                                "transaction_subdecisions": 0,
                                "transaction_decisions": 0,
                                "prior_inference_micros": 6000 if learned else 0,
                                "search_wall_micros": 100000 + int(learned),
                                "prior_skipped_forced": 0,
                                "prior_skipped_non_player_normal": 0,
                                "prior_eligible_decisions": int(learned),
                                "prior_surface_failures": 0, "transaction_failures": 0,
                                "conversion_failures": 0, "semantic_resolution_failures": 0,
                                "knowledge_failures": 0,
                            },
                        },
                    }
                    path = root / f"{arm}-{seed}.json"
                    path.write_text(json.dumps(row))
                    summaries.append(path)
            result = screen.summarize_screen(summaries, "reviewed-sha", "a" * 64)
            self.assertEqual(64, result["runs"])
            self.assertEqual(32, result["arms"]["LEARNED"]["seed_count"])
            self.assertEqual(6000, result["arms"]["LEARNED"]["prior_inference_p95_micros"])
            self.assertEqual("ONLINE_LEARNED_PRIOR_PROMISING", result["analysis"]["classification"])
            self.assertEqual(32, result["analysis"]["paired_win_table"]["learned_only"])
            self.assertEqual(0, result["analysis"]["paired_win_table"]["control_only"])
            self.assertEqual(20260923, result["analysis"]["paired_bootstrap"]["seed"])
            with self.assertRaisesRegex(ValueError, "missing 1 arm/seed"):
                screen.summarize_screen(summaries[:-1], "reviewed-sha", "a" * 64)

    @staticmethod
    def _synthetic_pairs(learned_only, control_only, both_win, both_lose):
        states = ([ (0, 1) ] * learned_only + [(1, 0)] * control_only
                  + [(1, 1)] * both_win + [(0, 0)] * both_lose)
        pairs = {}
        for offset, (control_win, learned_win) in enumerate(states):
            seed = 24100000 + offset
            rows = {}
            for arm, won in (("CONTROL", control_win), ("LEARNED", learned_win)):
                rows[arm] = {
                    "outcome": {"won": won, "floor": 40 + won, "hpEnd": 50 + won,
                                "fightsLost": 1 - won, "sec": 10 + won},
                    "telemetry": {"counters": {"search_wall_micros": 100000 + won,
                                                "decisions": 10 + won,
                                                "simulations": 10000 + 1000 * won}},
                }
            pairs[seed] = rows
        return pairs

    def test_preregistered_win_table_and_all_classification_outcomes(self):
        promising = screen.analyze_paired_results(self._synthetic_pairs(4, 0, 8, 20))
        self.assertEqual("ONLINE_LEARNED_PRIOR_PROMISING", promising["classification"])
        self.assertEqual({"learned_only": 4, "control_only": 0,
                          "both_win": 8, "both_lose": 20}, promising["paired_win_table"])
        self.assertEqual(12, promising["wins"]["LEARNED"])
        self.assertEqual(8, promising["wins"]["CONTROL"])
        self.assertEqual(4, promising["net_discordant"])
        self.assertEqual(0.125, promising["exact_two_sided_binomial_p"])

        unfavorable = screen.analyze_paired_results(self._synthetic_pairs(0, 4, 8, 20))
        self.assertEqual("ONLINE_LEARNED_PRIOR_UNFAVORABLE", unfavorable["classification"])
        self.assertEqual(-4, unfavorable["net_discordant"])

        inconclusive = screen.analyze_paired_results(self._synthetic_pairs(3, 2, 7, 20))
        self.assertEqual("ONLINE_LEARNED_PRIOR_INCONCLUSIVE", inconclusive["classification"])
        self.assertEqual(1, inconclusive["net_discordant"])
        self.assertEqual(inconclusive["paired_bootstrap"],
                         screen.analyze_paired_results(self._synthetic_pairs(3, 2, 7, 20))["paired_bootstrap"])
        self.assertIn("floor", inconclusive["secondary_outcomes"])
        self.assertIn("end_hp", inconclusive["secondary_outcomes"])
        self.assertIn("fights_lost", inconclusive["secondary_outcomes"])
        self.assertIn("wall_time_seconds", inconclusive["secondary_outcomes"])
        self.assertIn("search_time_micros", inconclusive["secondary_outcomes"])
        self.assertIn("decisions", inconclusive["secondary_outcomes"])
        self.assertIn("simulations", inconclusive["secondary_outcomes"])

    def test_binary_hash_must_match(self):
        with tempfile.TemporaryDirectory() as directory:
            binary = Path(directory) / "one_combat"
            binary.write_bytes(b"stale executable")
            with self.assertRaisesRegex(ValueError, "one_combat SHA-256 mismatch"):
                screen.verify_binary(binary, "0" * 64)


if __name__ == "__main__":
    unittest.main()
