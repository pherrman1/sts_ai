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
            self.assertNotIn("rng", json.dumps(row).lower())
        self.assertEqual(rows[0]["evaluators"][0]["combatEntryHash"], "entry-1")
        self.assertEqual(rows[1]["evaluators"][0]["latencyMicros"], 0)
        self.assertGreaterEqual(rows[0]["evaluators"][0]["deathProbability"], 0.0)
        self.assertLessEqual(rows[0]["evaluators"][0]["deathProbability"], 1.0)

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
                 "observation": dict(base, combatEntryHash="smoke")}
        writhing = dict(base, encounter="WRITHING_MASS", potions=["Potion Slot"] * 5)
        writhing_wire = dict(smoke, sequence=2, observationHash="writhing",
                             observation=dict(writhing, combatEntryHash="writhing"))
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
