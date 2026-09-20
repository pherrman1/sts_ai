import json
import os
from pathlib import Path
import subprocess
import sys
import unittest


class AdvisorProtocolTest(unittest.TestCase):
    def run_advisor(self, rows, model=None):
        env = os.environ.copy()
        if model is not None:
            env["STS_CTM_MODEL"] = str(model)
        else:
            env.pop("STS_CTM_MODEL", None)
        proc = subprocess.run(
            [sys.argv[1]], input="\n".join(rows) + "\n", text=True,
            capture_output=True, check=True, env=env)
        self.assertEqual(proc.stderr, "")
        return [json.loads(line) for line in proc.stdout.splitlines()]

    def test_handshake_and_fail_closed_observation(self):
        rows = self.run_advisor([
            '{"protocol":"sts_model_inspector_v1","kind":"hello"}',
            '{"protocol":"sts_model_inspector_v1","kind":"observation",'
            '"session":"run-1","sequence":1,"observationHash":"abc",'
            '"observation":{"boundary":"card_reward","character":"IRONCLAD",'
            '"ascension":0,"act":1,"floor":1,"hp":80,"maxHp":80,"gold":99,"deck":[],'
            '"candidates":['
            '{"id":"Bash","upgraded":false,"misc":0},'
            '{"id":"Strike_R","upgraded":false,"misc":0},'
            '{"id":"Defend_R","upgraded":false,"misc":0},'
            '{"id":"AscendersBane","upgraded":false,"misc":0}]}}',
        ])
        self.assertEqual(rows[0]["status"], "READY")
        self.assertEqual(rows[0]["evaluators"], [])
        self.assertEqual(rows[1]["status"], "UNSUPPORTED")
        self.assertEqual(rows[1]["observationHash"], "abc")

    def test_stale_sequence_is_rejected(self):
        request = ('{"protocol":"sts_model_inspector_v1","kind":"observation",'
                   '"session":"run-1","sequence":2,"observationHash":"%s",'
                   '"observation":{"boundary":"combat"}}')
        rows = self.run_advisor([request % "new", request % "old"])
        self.assertEqual(rows[0]["status"], "UNSUPPORTED")
        self.assertEqual(rows[1]["status"], "STALE")

    def test_validation_is_explicit(self):
        rows = self.run_advisor([
            "not-json",
            '{"protocol":"wrong","kind":"hello"}',
            '{"protocol":"sts_model_inspector_v1","kind":"observation",'
            '"session":"run-1"}',
            '{"protocol":"sts_model_inspector_v1","kind":"observation",'
            '"session":"run-1","sequence":1,"observationHash":"abc",'
            '"observation":{"boundary":"rest","deck":[],"candidates":[{}]}}',
        ])
        self.assertEqual(rows[0]["code"], "MALFORMED_JSON")
        self.assertEqual(rows[1]["code"], "PROTOCOL_MISMATCH")
        self.assertEqual(rows[2]["code"], "MALFORMED_REQUEST")
        self.assertEqual(rows[3]["code"], "SCHEMA_MISMATCH")
        self.assertEqual(rows[3]["session"], "run-1")
        self.assertEqual(rows[3]["sequence"], 1)
        self.assertEqual(rows[3]["observationHash"], "abc")

    def test_schema_error_with_valid_identity_is_correlated(self):
        rows = self.run_advisor([
            '{"protocol":"sts_model_inspector_v1","kind":"observation",'
            '"session":"schema-run","sequence":7,"observationHash":"schema-hash",'
            '"observation":{"boundary":"card_reward","deck":[],"candidates":[{}]}}',
        ])
        self.assertEqual(rows[0]["status"], "ERROR")
        self.assertEqual(rows[0]["code"], "SCHEMA_MISMATCH")
        self.assertEqual(rows[0]["session"], "schema-run")
        self.assertEqual(rows[0]["sequence"], 7)
        self.assertEqual(rows[0]["observationHash"], "schema-hash")

    def test_native_importer_rejects_unknown_card_id(self):
        rows = self.run_advisor([
            '{"protocol":"sts_model_inspector_v1","kind":"observation",'
            '"session":"run-import","sequence":1,"observationHash":"import",'
            '"observation":{"boundary":"card_reward","character":"IRONCLAD",'
            '"ascension":0,"act":1,"floor":1,"hp":80,"maxHp":80,"gold":99,'
            '"deck":[{"id":"NOT_A_CARD","upgraded":false,"misc":0}],'
            '"candidates":[]}}',
        ])
        self.assertEqual(rows[0]["status"], "ERROR")
        self.assertEqual(rows[0]["code"], "UNKNOWN_CARD_ID")
        self.assertEqual(rows[0]["message"],
                         "observation contains an unknown save-file card ID")
        self.assertEqual(rows[0]["session"], "run-import")
        self.assertEqual(rows[0]["sequence"], 1)
        self.assertEqual(rows[0]["observationHash"], "import")

    def test_malformed_error_has_no_untrusted_identity(self):
        rows = self.run_advisor(["not-json"])
        self.assertEqual(rows[0]["code"], "MALFORMED_JSON")
        self.assertNotIn("session", rows[0])
        self.assertNotIn("sequence", rows[0])
        self.assertNotIn("observationHash", rows[0])

    def test_ctm_artifact_forecast_import_and_cache(self):
        observation = {
            "boundary": "combat", "character": "IRONCLAD", "ascension": 0,
            "act": 1, "floor": 7, "hp": 70, "maxHp": 80, "gold": 99,
            "roomClass": "MONSTER", "previousRoomClass": "SHOP",
            "encounter": "CULTIST", "potionKeepValue": 4.0,
            "isBurningElite": False, "potionCapacity": 3,
            "deck": [{"id": "Strike_R", "upgraded": False, "misc": 0,
                       "bottleBinding": 0}],
            "relics": [{"id": "Pen Nib", "data": 4}],
            "potions": ["Potion Slot", "Fire Potion", "Potion Slot",
                         "Potion Slot", "Potion Slot"],
        }
        wire = {"protocol": "sts_model_inspector_v1", "kind": "observation",
                "session": "ctm", "sequence": 1, "observationHash": "turn-1",
                "observation": dict(observation, combatEntryHash="entry-1",
                                     combatEntry=observation)}
        repeat = dict(wire, sequence=2, observationHash="turn-2")
        rows = self.run_advisor([json.dumps(wire), json.dumps(repeat)], self.model)
        for row in rows:
            self.assertEqual(row["status"], "OK")
            self.assertEqual(row["evaluators"][0]["status"], "OK")
            histogram = row["evaluators"][0]["winningHpHistogram"]
            self.assertGreater(len(histogram), 1)
            self.assertAlmostEqual(sum(histogram), 1.0, places=4)
            self.assertEqual(row["evaluators"][0]["winningHpHistogramMin"], 0)
            self.assertNotIn("rng", json.dumps(row).lower())
        self.assertEqual(rows[0]["evaluators"][0]["combatEntryHash"], "entry-1")
        self.assertEqual(rows[1]["evaluators"][0]["latencyMicros"], 0)
        self.assertGreaterEqual(rows[0]["evaluators"][0]["deathProbability"], 0.0)
        self.assertLessEqual(rows[0]["evaluators"][0]["deathProbability"], 1.0)

    def test_ctm_room_history_categories_and_unknown_fail_closed(self):
        base = {"boundary": "combat", "character": "IRONCLAD", "ascension": 0,
                "act": 1, "floor": 7, "hp": 70, "maxHp": 80, "gold": 99,
                "roomClass": "MONSTER", "encounter": "CULTIST",
                "potionKeepValue": 4.0, "isBurningElite": False,
                "potionCapacity": 3,
                "deck": [{"id": "Strike_R", "upgraded": False, "misc": 0,
                          "bottleBinding": 0}],
                "relics": [], "potions": ["Potion Slot"] * 5}
        rows = []
        for sequence, previous in enumerate(("SHOP", "TREASURE", "BOSS_TREASURE", ""), 1):
            entry = dict(base, previousRoomClass=previous)
            rows.append({"protocol": "sts_model_inspector_v1", "kind": "observation",
                         "session": "room-history", "sequence": sequence,
                         "observationHash": "room-%d" % sequence,
                         "observation": dict(entry, combatEntryHash="entry-%d" % sequence,
                                              combatEntry=entry)})
        results = self.run_advisor([json.dumps(row) for row in rows], self.model)
        for row in results[:3]:
            self.assertEqual(row["status"], "OK")
            self.assertEqual(row["evaluators"][0]["status"], "OK")
        self.assertEqual(results[3]["status"], "ERROR")
        self.assertEqual(results[3]["code"], "UNSUPPORTED")

    def test_silver_rankings_include_physical_live_actions(self):
        entry = {
            "boundary": "combat", "character": "IRONCLAD", "ascension": 0,
            "act": 1, "floor": 1, "hp": 80, "maxHp": 80, "gold": 99,
            "roomClass": "MONSTER", "previousRoomClass": "NONE",
            "encounter": "CULTIST", "potionCapacity": 3,
            "deck": [{"id": "Strike_R", "upgraded": False, "misc": 0,
                      "bottleBinding": -1}],
            "relics": [], "potions": ["Potion Slot", "Fire Potion", "FairyPotion",
                                       "Potion Slot", "Potion Slot"],
        }
        root = dict(entry, schemaVersion=4, playerTurn=1, decisionInTurn=0,
                    combatInstance="ranked-actions-entry")
        root["combat"] = {
            "damageTrackingExact": True, "turn": 1, "energy": 3,
            "hand": [{"id": "Strike_R", "uuid": "physical-strike", "upgraded": False,
                      "misc": 0, "cost": 1, "costForTurn": 1}],
            "draw": [], "discard": [], "exhaust": [], "limbo": [], "stasis": [],
            "relics": [], "potions": ["Potion Slot", "Fire Potion", "FairyPotion"],
            "monsters": [{"id": "Cultist", "hp": 50, "maxHp": 50, "block": 0,
                          "nextMove": 3, "moveHistory": [3], "miscInfo": 0,
                          "dead": False, "powers": []}],
        }
        observation = dict(entry, combatEntry=entry, combatEntryHash="ranked-actions-entry",
                           silverRoot=root)
        wire = {"protocol": "sts_model_inspector_v1", "kind": "observation",
                "session": "ranked-actions", "sequence": 1,
                "observationHash": "ranked-actions-hash", "observation": observation}
        result, = self.run_advisor([json.dumps(wire)], self.model)
        self.assertEqual(result["status"], "OK")
        silver = next(row for row in result["evaluators"]
                      if row["id"] == "silver_player_decision_v2")
        self.assertEqual(silver["status"], "OK", silver)
        summaries = silver["rootActionSummaries"]
        self.assertTrue(summaries)
        self.assertTrue(all("liveAction" in row for row in summaries))
        actions = [row["liveAction"] for row in summaries]
        self.assertIn({"kind": "end_turn"}, actions)
        self.assertIn({"kind": "card", "cardUuid": "physical-strike", "targetIndex": 1}, actions)
        self.assertIn({"kind": "potion", "potionSlot": 2, "discard": False, "targetIndex": 1}, actions)
        self.assertIn({"kind": "potion", "potionSlot": 3, "discard": True}, actions)
        selected = next(row for row in summaries
                        if row["fingerprint"] == silver["selectedAction"])
        self.assertEqual(selected["liveAction"], silver["selectedLiveAction"])

    def test_unknown_combat_selection_remains_silver_with_ctm_enabled(self):
        for room, encounter in (("MONSTER", "SHELL_PARASITE"),
                                ("EVENT", "LAGAVULIN_EVENT")):
            with self.subTest(room=room, encounter=encounter):
                entry = {
                    "boundary": "combat", "character": "IRONCLAD", "ascension": 0,
                    "act": 2, "floor": 22, "hp": 15, "maxHp": 80, "gold": 99,
                    "roomClass": room, "previousRoomClass": "MONSTER",
                    "encounter": encounter, "potionKeepValue": 4.0,
                    "isBurningElite": False, "potionCapacity": 3,
                    "deck": [{"id": "Strike_R", "upgraded": False, "misc": 0,
                              "bottleBinding": -1}],
                    "relics": [], "potions": ["Potion Slot"] * 5,
                }
                observation = dict(entry, combatEntryHash="selection-entry", combatEntry=entry)
                observation["silverRoot"] = {
                    "schemaVersion": 4, "character": "IRONCLAD", "roomClass": room,
                    "encounter": encounter, "playerTurn": 3, "decisionInTurn": 1,
                    "combatInstance": "selection-entry",
                    "combat": {"damageTrackingExact": False, "cardSelect": {
                        "task": "", "canPickZero": True, "canPickAnyNumber": False,
                        "pickCount": 1, "cards": ["Strike_R"],
                    }},
                }
                wire = {"protocol": "sts_model_inspector_v1", "kind": "observation",
                        "session": "selection-session", "sequence": 1,
                        "observationHash": "selection-hash", "observation": observation}
                result, = self.run_advisor([json.dumps(wire)], self.model)
                self.assertEqual(result["status"], "OK")
                self.assertEqual(result["modelStatus"], "OK")
                self.assertEqual(result["session"], wire["session"])
                self.assertEqual(result["sequence"], wire["sequence"])
                self.assertEqual(result["observationHash"], wire["observationHash"])
                evaluators = {row["id"]: row for row in result["evaluators"]}
                self.assertIn(evaluators["ctm_combat_entry_v2"]["status"], ("OK", "UNSUPPORTED"))
                silver = evaluators["silver_player_decision_v2"]
                self.assertEqual(silver["status"], "UNSUPPORTED")
                self.assertEqual(silver["reason"], "silver_unmapped_selection_task")
                self.assertNotIn("live_ooc_decision_v1", evaluators)
                self.assertNotIn("selectedLiveAction", silver)

    def test_ctm_support_failures_and_missing_model_are_explicit(self):
        base = {"boundary": "combat", "character": "IRONCLAD", "ascension": 0,
                "act": 1, "floor": 7, "hp": 70, "maxHp": 80, "gold": 99,
                "roomClass": "MONSTER", "previousRoomClass": "NONE",
                "encounter": "CULTIST", "potionKeepValue": 4.0,
                "isBurningElite": False, "potionCapacity": 3,
            "deck": [{"id": "RitualDagger", "upgraded": False, "misc": 0,
                           "bottleBinding": -1}],
                "relics": [], "potions": ["SmokeBomb", "Potion Slot",
                                             "Potion Slot", "Potion Slot", "Potion Slot"]}
        smoke = {"protocol": "sts_model_inspector_v1", "kind": "observation",
                 "session": "fail", "sequence": 1, "observationHash": "smoke",
                 "observation": dict(base, combatEntryHash="smoke",
                                      combatEntry=base)}
        writhing = dict(base, encounter="WRITHING_MASS", potions=["Potion Slot"] * 5)
        writhing_wire = dict(smoke, sequence=2, observationHash="writhing",
                             observation=dict(writhing, combatEntryHash="writhing",
                                              combatEntry=writhing))
        rows = self.run_advisor([json.dumps(smoke), json.dumps(writhing_wire)], self.model)
        self.assertEqual(rows[0]["evaluators"][0]["status"], "UNSUPPORTED")
        self.assertEqual(rows[0]["evaluators"][0]["reason"], "smoke_bomb")
        self.assertEqual(rows[1]["evaluators"][0]["reason"], "writhing_ritual_intersection")

        missing_wire = dict(smoke, observation=dict(base, combatEntryHash="smoke",
                                                    combatEntry=base))
        missing = self.run_advisor([json.dumps(missing_wire)])
        self.assertEqual(missing[0]["status"], "MODEL_UNAVAILABLE")
        invalid = self.run_advisor([json.dumps(missing_wire)], "/definitely/not/a/model.native")
        self.assertEqual(invalid[0]["status"], "SCHEMA_MISMATCH")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        raise SystemExit("usage: live_advisor_protocol.py ADVISOR_BINARY CTM_MODEL")
    AdvisorProtocolTest.model = Path(sys.argv[2])
    unittest.main(argv=[sys.argv[0]])
