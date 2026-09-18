import json
import subprocess
import sys
import unittest


class AdvisorProtocolTest(unittest.TestCase):
    def run_advisor(self, rows):
        proc = subprocess.run(
            [sys.argv[1]], input="\n".join(rows) + "\n", text=True,
            capture_output=True, check=True)
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


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit("usage: live_advisor_protocol.py ADVISOR_BINARY")
    unittest.main(argv=[sys.argv[0]])
