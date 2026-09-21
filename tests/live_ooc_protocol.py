"""Native projection -> advisor provider -> structured one-screen action contract."""
import copy
from concurrent.futures import ThreadPoolExecutor
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


class LiveOocProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.advisor, cls.fixture_binary, cls.model = map(Path, sys.argv[1:4])
        cls.ctm = Path(sys.argv[4]) if len(sys.argv) > 4 else None
        cls.win = Path(sys.argv[5]) if len(sys.argv) > 5 else None
        with tempfile.TemporaryDirectory() as directory:
            fixture = Path(directory) / "fixtures.jsonl"
            subprocess.run(["bash", "tools/seed_guard.sh", str(cls.fixture_binary), str(cls.model), str(fixture)],
                           check=True, capture_output=True, text=True)
            cls.fixtures = {row["fixture"]: row for row in map(json.loads, fixture.read_text().splitlines())}

    def run_rows(self, observations, model=True, policy=None, floor_model=True):
        env = os.environ.copy()
        env.pop("STS_CTM_MODEL", None)
        env.pop("STS_LIVE_OOC_MODEL", None)
        if model:
            env["STS_LIVE_OOC_MODEL"] = str(self.model)
        if self.ctm:
            env["STS_CTM_MODEL"] = str(self.ctm)
        if self.win:
            env["STS_LIVE_OOC_WIN_MODEL"] = str(self.win)
        env.pop("STS_LIVE_OOC_FLOOR_MODEL", None)
        if floor_model:
            env["STS_LIVE_OOC_FLOOR_MODEL"] = "models/v_rich_trees.txt"
        if policy:
            env["STS_LIVE_OOC_POLICY"] = policy
        requests = [dict(protocol="sts_model_inspector_v1", kind="observation", session="ooc-protocol",
                         sequence=i + 1, observationHash=f"fixture-{i}", observation=observation)
                    for i, observation in enumerate(observations)]
        proc = subprocess.run([str(self.advisor)], input="".join(json.dumps(r) + "\n" for r in requests),
                              text=True, capture_output=True, env=env, check=True)
        rows = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(len(rows), len(requests))
        for request, row in zip(requests, rows):
            for key in ("session", "sequence", "observationHash"):
                self.assertEqual(row[key], request[key])
        return rows

    def test_all_native_parity_fixtures(self):
        # Independent fixtures do not share a live session or compound plan.
        # Running a few advisor processes concurrently keeps the 512-sim
        # coverage without making this integration test serially prohibitive.
        fixtures = list(self.fixtures.values())
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(lambda row: self.run_rows([row])[0], fixtures))
        for fixture, response in zip(fixtures, responses):
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["id"], "live_ooc_decision_v1")
            self.assertEqual(evaluator["policy"], "mcts_ctm")
            if fixture["fixture"].startswith("unsupported_"):
                self.assertEqual(evaluator["status"], "UNSUPPORTED")
                continue
            if evaluator["status"] == "UNSUPPORTED":
                self.assertTrue(evaluator.get("reason", "").startswith("OOC_MCTS_")
                                or evaluator.get("reason", "") == "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED",
                                response)
                continue
            self.assertEqual(evaluator["status"], "OK", response)
            candidates = evaluator["candidateSummaries"]
            keys = [c["semanticKey"] for c in candidates]
            self.assertEqual(keys, sorted(set(keys)))
            chosen = next(c for c in candidates if c["semanticKey"] == evaluator["selectedSemanticKey"])
            self.assertEqual(chosen["visits"], max(c["visits"] for c in candidates))
            for candidate in candidates:
                self.assertIsInstance(candidate["visits"], int)
                self.assertGreaterEqual(candidate["visits"], 0)
                self.assertGreaterEqual(candidate["visitShare"], 0.0)
                self.assertGreaterEqual(candidate["prior"], 0.0)
            self.assertEqual(chosen["liveAction"], evaluator["selectedLiveAction"])
            self.assertIn("identity", evaluator["model"])

    def test_searing_blow_history_is_explicit_unsupported(self):
        response, = self.run_rows([self.fixtures["unsupported_searing_blow_upgrade_history"]])
        self.assertEqual(response["evaluators"][0]["status"], "UNSUPPORTED")
        self.assertEqual(response["evaluators"][0]["reason"], "SEARING_BLOW_UPGRADE_HISTORY_UNQUALIFIED")

    def test_event_fights_fail_closed_without_public_reward_pity_history(self):
        rows = self.run_rows([self.fixtures["unsupported_mushrooms_reward_pity"],
                              self.fixtures["unsupported_sphere_reward_pity"]])
        for response in rows:
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["status"], "UNSUPPORTED")
            self.assertEqual(evaluator["reason"], "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED")

    def test_resumed_combat_class_history_fails_closed(self):
        observation = copy.deepcopy(self.fixtures["event_big_fish"])
        observation["ooc"]["publicState"]["combatHistoryComplete"] = False
        response, = self.run_rows([observation])
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "UNSUPPORTED")
        self.assertEqual(evaluator["reason"], "PUBLIC_COMBAT_CLASS_HISTORY_UNQUALIFIED")

    def test_missing_model_keeps_explicit_unsupported(self):
        response, = self.run_rows([self.fixtures["event_big_fish"]], model=False)
        self.assertEqual(response["evaluators"][0]["reason"], "MODEL_UNAVAILABLE")

    def test_compound_candidates_preserve_semantic_targets(self):
        rest, wall = self.run_rows([
            self.fixtures["rest_smith_lift_dig_remove_key"], self.fixtures["event_living_wall"]])
        selector, = self.run_rows([self.fixtures["upgrade_duplicate_physical_cards"]])
        for response in (rest, wall):
            evaluator = response["evaluators"][0]
            self.assertEqual(evaluator["status"], "OK")
            targeted = [c for c in evaluator["candidateSummaries"]
                        if c["semanticPayload"].get("type") in {"transaction", "deck_card"}
                        or c["semanticPayload"].get("target", {}).get("type") in {"transaction", "deck_card"}]
            self.assertTrue(targeted)
            self.assertTrue(all("visits" in c and "prior" in c for c in targeted))
        self.assertEqual(selector["evaluators"][0]["status"], "OK")

    def test_compound_source_retains_target_before_selector_score(self):
        selector = self.fixtures["upgrade_duplicate_physical_cards"]
        standalone, = self.run_rows([selector], policy="v4")
        source, retained = self.run_rows([
            self.fixtures["event_living_wall"], selector], policy="v4")
        standalone_eval = standalone["evaluators"][0]
        source_eval = source["evaluators"][0]
        retained_eval = retained["evaluators"][0]
        self.assertEqual(source_eval["compoundPlan"]["status"], "PENDING")
        self.assertEqual(retained_eval["compoundPlan"]["status"], "APPLIED")
        self.assertEqual(retained_eval["compoundPlan"]["selectionMode"],
                         "retained_compound_target")
        self.assertNotEqual(standalone_eval["selectedSemanticKey"],
                            retained_eval["selectedSemanticKey"])
        chosen = next(c for c in retained_eval["candidateSummaries"]
                      if c["semanticKey"] == retained_eval["selectedSemanticKey"])
        self.assertEqual(chosen["visits"], max(c["visits"]
                                                for c in retained_eval["candidateSummaries"]))

    def test_semantic_only_roots_use_uniform_prior_and_checkpoint_leaf(self):
        rows = self.run_rows([self.fixtures[name] for name in
                              ("remove_selector", "transform_selector", "rewards_without_cards")])
        for response in rows:
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["status"], "OK", response)
            priors = [candidate["prior"] for candidate in evaluator["candidateSummaries"]]
            self.assertTrue(priors)
            self.assertTrue(all(abs(prior - priors[0]) < 1e-12 for prior in priors), response)

    def test_map_root_runs_mcts_and_stops_after_the_transition(self):
        response, = self.run_rows([self.fixtures["map_multiple_children"]])
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["model"]["kind"], "ooc_mcts_ctm")
        self.assertGreaterEqual(len(evaluator["candidateSummaries"]), 2)
        chosen = next(c for c in evaluator["candidateSummaries"]
                      if c["semanticKey"] == evaluator["selectedSemanticKey"])
        self.assertEqual(chosen["visits"], max(c["visits"] for c in evaluator["candidateSummaries"]))
        self.assertEqual(evaluator["selectedLiveAction"]["kind"], "choose")
        self.assertIsInstance(evaluator["selectedLiveAction"]["choiceIndex"], int)

    def test_map_root_rejects_incomplete_offered_relic_history(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        observation["ooc"]["publicState"]["seenRelicsComplete"] = False
        response, = self.run_rows([observation])
        evaluator = response["evaluators"][0]
        self.assertEqual(evaluator["status"], "UNSUPPORTED")
        self.assertEqual(evaluator["reason"], "PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED")

    def test_unqualified_pity_never_becomes_a_v4_midpoint(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        observation["ooc"]["publicState"]["rewardPityHistoryComplete"] = False
        v4_response, = self.run_rows([observation], policy="v4")
        v4 = v4_response["evaluators"][0]
        self.assertEqual(v4["status"], "UNSUPPORTED")
        self.assertEqual(v4["reason"], "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED")

        mcts_response, = self.run_rows([observation])
        mcts = mcts_response["evaluators"][0]
        self.assertEqual(mcts["status"], "OK")
        priors = [candidate["prior"] for candidate in mcts["candidateSummaries"]]
        self.assertTrue(priors)
        self.assertTrue(all(abs(prior - priors[0]) < 1e-12 for prior in priors), mcts)

    def test_opened_boss_chest_is_native_proceed_passthrough(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        ooc = observation["ooc"]
        ooc["screen"] = "treasure"
        ooc["details"] = {"chestType": "BossChest", "opened": True}
        ooc["liveChoices"] = [{"liveAction": {"kind": "proceed"},
                               "nativeAction": {"kind": "option", "index": 0}}]
        self.assertNotIn("unsupportedReason", ooc)
        response, = self.run_rows([observation])
        evaluator = response["evaluators"][0]
        self.assertEqual(evaluator["status"], "OK")
        self.assertEqual(evaluator["mode"], "native_pass_through")
        self.assertEqual(evaluator["selectedLiveAction"], {"kind": "proceed"})

    def test_woman_in_blue_is_a_complete_live_mcts_root(self):
        response, = self.run_rows([self.fixtures["event_woman_in_blue"]])
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["model"]["kind"], "ooc_mcts_ctm")
        self.assertEqual(evaluator["model"]["simulations"], 512)
        self.assertEqual(len(evaluator["candidateSummaries"]), 4)
        self.assertEqual(
            {candidate["liveAction"]["choiceIndex"] for candidate in evaluator["candidateSummaries"]},
            {1, 2, 3, 4},
        )
        chosen = next(candidate for candidate in evaluator["candidateSummaries"]
                      if candidate["semanticKey"] == evaluator["selectedSemanticKey"])
        self.assertEqual(chosen["visits"], max(candidate["visits"]
                                                for candidate in evaluator["candidateSummaries"]))
        self.assertEqual(chosen["liveAction"], evaluator["selectedLiveAction"])

    def test_complete_history_map_root_scores_paths(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        observation["ooc"]["publicState"]["seenRelicsComplete"] = True
        response, = self.run_rows([observation])
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["model"]["simulations"], 512)
        self.assertGreater(len(evaluator["candidateSummaries"]), 1)
        self.assertEqual(sum(c["visits"] for c in evaluator["candidateSummaries"]), 512)

    def test_missing_floor_model_fails_closed(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        observation["ooc"]["publicState"]["seenRelicsComplete"] = True
        response, = self.run_rows([observation], floor_model=False)
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "UNSUPPORTED")
        self.assertEqual(evaluator["reason"], "OOC_FLOOR_MODEL_UNAVAILABLE")

    def test_capture_support_boundary(self):
        response, = self.run_rows([{"boundary": "ooc", "ooc": {
            "schemaVersion": 1, "screen": "selector", "unsupportedReason": "SELECTOR_CONFIRMATION_ONLY"}}])
        self.assertEqual(response["evaluators"][0]["status"], "UNSUPPORTED")

    def test_active_winged_is_bounded_to_non_map_roots(self):
        selector = copy.deepcopy(self.fixtures["upgrade_duplicate_physical_cards"])
        selector["ooc"]["publicState"]["relics"].append({"id": "WingedGreaves", "data": 3})
        selector["ooc"]["unsupportedReason"] = \
            "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"
        response, = self.run_rows([selector])
        self.assertEqual(response["evaluators"][0]["status"], "OK", response)

        direct_map = copy.deepcopy(self.fixtures["map_multiple_children"])
        direct_map["ooc"]["publicState"]["relics"].append({"id": "WingedGreaves", "data": 3})
        direct_map["ooc"]["unsupportedReason"] = \
            "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"
        response, = self.run_rows([direct_map])
        self.assertEqual(response["evaluators"][0]["status"], "UNSUPPORTED")
        self.assertEqual(response["evaluators"][0]["reason"],
                         "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active")

    def test_schema_and_mapping_errors_cannot_fallback(self):
        base = self.fixtures["event_big_fish"]
        invalid_schema = copy.deepcopy(base)
        invalid_schema["ooc"]["publicState"].pop("pathVisits")
        missing = copy.deepcopy(base)
        missing["ooc"]["liveChoices"].pop()
        duplicate = copy.deepcopy(base)
        duplicate["ooc"]["liveChoices"].append(duplicate["ooc"]["liveChoices"][0])
        for model in (True, False):
            for response in self.run_rows([invalid_schema, missing, duplicate], model=model):
                self.assertEqual(response["status"], "ERROR")
                self.assertNotIn("evaluators", response)

    def test_capture_integrity_error_overrides_unsupported(self):
        observation = {"boundary": "ooc", "ooc": {
            "schemaVersion": 1, "screen": "map", "captureError": "IllegalArgumentException:bad edge",
            "unsupportedReason": "MODEL_UNAVAILABLE"}}
        for model in (True, False):
            response, = self.run_rows([observation], model=model)
            self.assertEqual(response["status"], "ERROR")
            self.assertNotIn("evaluators", response)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
