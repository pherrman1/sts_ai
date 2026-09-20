"""Native projection -> advisor provider -> structured one-screen action contract."""
import copy
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

    def run_rows(self, observations, model=True):
        env = os.environ.copy()
        env.pop("STS_CTM_MODEL", None)
        env.pop("STS_LIVE_OOC_MODEL", None)
        if model:
            env["STS_LIVE_OOC_MODEL"] = str(self.model)
        if self.ctm:
            env["STS_CTM_MODEL"] = str(self.ctm)
        if self.win:
            env["STS_LIVE_OOC_WIN_MODEL"] = str(self.win)
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
        for fixture, response in zip(self.fixtures.values(), self.run_rows(list(self.fixtures.values()))):
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["id"], "live_ooc_decision_v1")
            self.assertEqual(evaluator["policy"], "mcts_ctm")
            if fixture["fixture"].startswith("unsupported_"):
                self.assertEqual(evaluator["status"], "UNSUPPORTED")
                continue
            if evaluator["status"] == "UNSUPPORTED":
                self.assertTrue(evaluator.get("reason", "").startswith("OOC_MCTS_"), response)
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

    def test_missing_model_keeps_explicit_unsupported(self):
        response, = self.run_rows([self.fixtures["event_big_fish"]], model=False)
        self.assertEqual(response["evaluators"][0]["reason"], "MODEL_UNAVAILABLE")

    def test_compound_candidates_preserve_semantic_targets(self):
        rest, wall, selector = self.run_rows([
            self.fixtures["rest_smith_lift_dig_remove_key"], self.fixtures["event_living_wall"],
            self.fixtures["upgrade_duplicate_physical_cards"]])
        for response in (rest, wall):
            evaluator = response["evaluators"][0]
            self.assertEqual(evaluator["status"], "OK")
            targeted = [c for c in evaluator["candidateSummaries"]
                        if c["semanticPayload"].get("type") in {"transaction", "deck_card"}
                        or c["semanticPayload"].get("target", {}).get("type") in {"transaction", "deck_card"}]
            self.assertTrue(targeted)
            self.assertTrue(all("visits" in c and "prior" in c for c in targeted))
        self.assertEqual(selector["evaluators"][0]["status"], "OK")

    def test_capture_support_boundary(self):
        response, = self.run_rows([{"boundary": "ooc", "ooc": {
            "schemaVersion": 1, "screen": "selector", "unsupportedReason": "SELECTOR_CONFIRMATION_ONLY"}}])
        self.assertEqual(response["evaluators"][0]["status"], "UNSUPPORTED")

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
