import importlib.util
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "forced", Path(__file__).resolve().parents[2] / "tools/analyze_silver_forced_action_audit.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ForcedActionAuditTest(unittest.TestCase):
    def rows(self, l_values=(2.0, 1.0), a_selected="b"):
        rows = []
        for source in range(2):
            for root_index in range(2):
                root = f"{source}/fight/{root_index}"
                native = ["a", "b"]
                for estimator, budget, values in (("L", 8, l_values), ("J", 16, (3.0, 0.0))):
                    for action_index, action in enumerate(native):
                        for replicate in range(2):
                            identity = (100000 * source + 10000 * root_index
                                        + (1000 if estimator == "J" else 0) + replicate + 1)
                            rows.append({"schema": MODULE.SCHEMA, "population": "primary",
                                "target_definition": MODULE.TARGET, "root_id": root,
                                "source_seed": source, "state_hash": f"state-{root}",
                                "root_snapshot_hash": f"snapshot-{root}",
                                "action_fingerprint": action, "native_order": native,
                                "estimator": estimator, "replicate": replicate,
                                "value": values[action_index], "continuation_budget": budget,
                                "simulations": budget, "terminal_after_action": False,
                                "terminal_victory": False,
                                "victories": 0, "victory_baseline_correction": 0.0,
                                "applied_baseline_correction": 0.0,
                                "leaf_root_value": values[action_index],
                                "rng_identity": identity, "root_outcome_rng_identity": identity,
                                "immediate_rng_counter_before": 0,
                                "immediate_rng_counter_after": 1 if action == "b" else 0,
                                "continuation_rng_identity": identity,
                                "continuation_rng_counter": 1 if action == "b" else 0,
                                "stochastic": action == "b",
                                "teacher_a_selected_action": a_selected,
                                "teacher_a_rng_identity": 900000 + source * 10 + root_index,
                                "teacher_a_budget": 16, "teacher_a_q": (0.0, 1.0)[action_index],
                                "teacher_a_visits": (2, 3)[action_index], "master_seed": 7,
                                "utility_definition": "BattleSearcher::evaluateEndState",
                                "evaluator_config": {"reuse_cap_mode": "none"},
                                "executable_git_sha": "a" * 40,
                                "source_executable_git_sha": "a" * 40,
                                "silver_upstream_sha": "b" * 40, "fixture_only": True})
        return rows

    def test_pass_and_fail_are_fail_closed(self):
        passed = MODULE.analyze(self.rows(), expected_roots=4, replicates=2,
                                l_budget=8, j_budget=16, fixture=True)
        self.assertEqual(passed["classification"], "FORCED_ACTION_TARGET_PASS")
        self.assertTrue(all(passed["gates"].values()))
        failed = MODULE.analyze(self.rows(l_values=(0.0, 2.0)), expected_roots=4,
                                replicates=2, l_budget=8, j_budget=16, fixture=True)
        self.assertEqual(failed["classification"], "FORCED_ACTION_TARGET_FAIL")
        self.assertFalse(failed["gates"]["regret_ci_below_zero"])

    def test_provenance_and_crn_mismatches_rejected(self):
        for index, field, value in ((0, "state_hash", "changed"),
                                    (0, "rng_identity", 42),
                                    (0, "stochastic", True),
                                    (0, "applied_baseline_correction", 1.0)):
            rows = self.rows()
            rows[index][field] = value
            with self.assertRaises(ValueError):
                MODULE.analyze(rows, expected_roots=4, replicates=2,
                               l_budget=8, j_budget=16, fixture=True)

    def test_terminal_action_requires_zero_continuation_simulations(self):
        rows = self.rows()
        for row in rows:
            if row["action_fingerprint"] == "b":
                row["terminal_after_action"] = True
                row["simulations"] = 0
        MODULE.analyze(rows, expected_roots=4, replicates=2,
                       l_budget=8, j_budget=16, fixture=True)
        rows[0]["terminal_after_action"] = True
        with self.assertRaises(ValueError):
            MODULE.analyze(rows, expected_roots=4, replicates=2,
                           l_budget=8, j_budget=16, fixture=True)

    def test_selection_is_two_per_source_and_order_independent(self):
        rows = [{"root_id": f"{source}/fight/{index}", "source_seed": source}
                for source in range(16) for index in range(4)]
        first = MODULE.select(rows)
        second = MODULE.select(list(reversed(rows)))
        self.assertEqual([row["root_id"] for row in first], [row["root_id"] for row in second])
        self.assertEqual(len(first), 32)
        self.assertEqual({source: sum(row["source_seed"] == source for row in first)
                          for source in range(16)}, {source: 2 for source in range(16)})

    def test_historical_population_is_separate_and_fail_closed(self):
        rows = self.rows()
        for row in rows:
            row["population"] = "historical_regression"
            row["fixture_only"] = False
            row["teacher_a_budget"] = 10000
        result = MODULE.analyze_historical(rows, replicates=2, l_budget=8, j_budget=16)
        self.assertEqual(result["classification"], "HISTORICAL_REGRESSION_PASS")
        with self.assertRaises(ValueError):
            MODULE.analyze(rows, expected_roots=4, replicates=2,
                           l_budget=8, j_budget=16, fixture=True)

    def test_missing_stochastic_coverage_cannot_authorize_global_target(self):
        rows = self.rows()
        for row in rows:
            row["stochastic"] = False
            row["immediate_rng_counter_after"] = row["immediate_rng_counter_before"]
            row["continuation_rng_counter"] = row["immediate_rng_counter_after"]
        result = MODULE.analyze(rows, expected_roots=4, replicates=2,
                                l_budget=8, j_budget=16, fixture=True)
        self.assertEqual(result["classification"], "FORCED_ACTION_TARGET_DETERMINISTIC_ONLY")
        self.assertFalse(result["gates"]["stochastic_coverage_present"])
        self.assertFalse(result["gates"]["stochastic_pairwise_not_worse"])


if __name__ == "__main__":
    unittest.main()
