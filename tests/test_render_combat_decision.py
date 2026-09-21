import json
import tempfile
import unittest
from pathlib import Path

from tools.render_combat_decision import RenderError, load_differential_trace, load_snapshot, load_trace, main, render_html


def evaluator(**extra):
    value = {
        "id": "silver_player_decision_v2",
        "status": "OK",
        "requestedSimulations": 1000,
        "additionalSimulations": 700,
        "totalSimulations": 1000,
        "rootVisits": 1000,
        "selectedAction": "attack:2",
        "selectedLabel": "Bash",
        "selectedLiveAction": {"kind": "card", "cardUuid": "bash-1", "targetIndex": 1},
        "legalActions": ["attack:1", "attack:2"],
        "decisionInTurn": 0,
        "reroot": {"exact": True, "equivalentCopy": False, "fallback": False, "inheritedVisits": 42},
        "rootActionSummaries": [
            {"fingerprint": "attack:1", "label": "Strike", "liveAction": {"kind": "card", "cardUuid": "strike-1"},
             "edgeVisits": 600, "visitShare": 0.6, "selectionQValid": False},
            {"fingerprint": "attack:2", "label": "Bash", "liveAction": {"kind": "card", "cardUuid": "bash-1"},
             "edgeVisits": 400, "visitShare": 0.4, "selectionQValid": True, "selectionQ": 0.73},
        ],
    }
    value.update(extra)
    return value


def snapshot_data(**extra):
    observation = {
        "boundary": "combat",
        "act": 1,
        "floor": 12,
        "hp": 55,
        "maxHp": 80,
        "turn": 3,
        "combat": {
            "block": 6, "energy": 2,
            "monsters": [{"id": "Cultist", "hp": 20, "maxHp": 48, "block": 0,
                          "intent": "ATTACK", "intentDamage": 6}],
            "hand": [{"id": "Bash", "name": "Bash", "uuid": "bash-1", "upgraded": False, "cost": 2}],
            "draw": ["Strike", "Defend"], "discard": [], "exhaust": [],
            "potions": ["Fire Potion"], "relics": ["Burning Blood"],
        },
        "silverRoot": {"encounter": "Cultist"},
    }
    observation.update(extra.pop("observation", {}))
    return {
        "session": "run-1", "sequence": 7, "observationHash": "hash-7", "observation": observation,
        "response": {"ready": True, "session": "run-1", "sequence": 7, "observationHash": "hash-7",
                      "advisor": {"evaluators": [evaluator(**extra)]}},
    }


class RenderCombatDecisionTest(unittest.TestCase):
    def write_json(self, directory, name, value):
        path = Path(directory) / name
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_valid_snapshot_renders_combat_state_and_all_actions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = self.write_json(directory, "latest.json", snapshot_data())
            source = load_snapshot(path)
            rendered = render_html(source)
            self.assertIn("Cultist", rendered)
            self.assertIn("Burning Blood", rendered)
            self.assertIn("Root action ranking", rendered)
            self.assertIn("Strike", rendered)
            self.assertIn("Bash", rendered)
            self.assertIn("<span>HP</span><b>55</b>", rendered)
            self.assertIn("<td>6</td></tr>", rendered)
            self.assertIn("<span>draw</span><b>2</b>", rendered)

    def test_selected_action_is_matched_by_fingerprint_not_visit_rank(self):
        with tempfile.TemporaryDirectory() as directory:
            source = load_snapshot(self.write_json(directory, "latest.json", snapshot_data()))
            rendered = render_html(source)
            self.assertEqual(rendered.count('class="selected-action"'), 1)
            self.assertIn("✓ selected", rendered)
            selected_row = rendered.split('class="selected-action"', 1)[1]
            self.assertIn("attack:2", selected_row)

    def test_q_validity_and_visit_shares_are_explicit(self):
        with tempfile.TemporaryDirectory() as directory:
            source = load_snapshot(self.write_json(directory, "latest.json", snapshot_data()))
            rendered = render_html(source)
            self.assertIn("unvisited / Q unavailable", rendered)
            self.assertIn("0.73", rendered)
            self.assertIn(">0.6</span>", rendered)
            self.assertIn("width:60.000%", rendered)

    def test_malformed_visit_share_is_preserved_but_bar_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            value = snapshot_data()
            value["response"]["advisor"]["evaluators"][0]["rootActionSummaries"][0]["visitShare"] = 1.5
            source = load_snapshot(self.write_json(directory, "latest.json", value))
            rendered = render_html(source)
            self.assertIn(">1.5</span>", rendered)
            self.assertIn("width:100.000%", rendered)

    def test_unsupported_response_is_first_class(self):
        with tempfile.TemporaryDirectory() as directory:
            value = snapshot_data(status="UNSUPPORTED", reason="silver_missing_predecessor")
            value["response"]["advisor"]["evaluators"][0].pop("rootActionSummaries")
            source = load_snapshot(self.write_json(directory, "latest.json", value))
            rendered = render_html(source)
            self.assertIn("UNSUPPORTED", rendered)
            self.assertIn("silver_missing_predecessor", rendered)
            self.assertIn("legal actions", rendered)

    def test_malformed_and_non_combat_snapshot_fail_clearly(self):
        with tempfile.TemporaryDirectory() as directory:
            malformed = Path(directory) / "bad.json"
            malformed.write_text("{", encoding="utf-8")
            with self.assertRaisesRegex(RenderError, "malformed JSON"):
                load_snapshot(malformed)
            non_combat = snapshot_data()
            non_combat["observation"]["boundary"] = "ooc"
            with self.assertRaisesRegex(RenderError, "not combat"):
                load_snapshot(self.write_json(directory, "ooc.json", non_combat))

    def test_multiple_silver_evaluators_fail_as_ambiguous(self):
        with tempfile.TemporaryDirectory() as directory:
            value = snapshot_data()
            value["response"]["advisor"]["evaluators"].append(evaluator())
            with self.assertRaisesRegex(RenderError, "multiple ambiguous"):
                load_snapshot(self.write_json(directory, "ambiguous.json", value))

    def test_hostile_strings_are_html_escaped(self):
        with tempfile.TemporaryDirectory() as directory:
            value = snapshot_data()
            value["response"]["advisor"]["evaluators"][0]["rootActionSummaries"][0]["label"] = "<script>alert(1)</script>"
            source = load_snapshot(self.write_json(directory, "hostile.json", value))
            rendered = render_html(source)
            self.assertNotIn("<script>alert(1)</script>", rendered)
            self.assertIn("&lt;script&gt;alert(1)&lt;/script&gt;", rendered)

    def test_trace_selects_exact_step_and_does_not_guess_missing_before_state(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            rows = [
                {"step": 4, "inspector_session": "run-1", "inspector_sequence": 7,
                 "inspector_observationHash": "hash-7", "silver_evaluator": evaluator(),
                 "post_action_state": {"player": {"current_hp": 49}},
                 "legal_candidates": [{"id": "a0"}], "executed_mcp_tool": "play_card", "executed_mcp_arguments": {"card_index": 1}},
                {"step": 5, "silver_evaluator": evaluator(selectedAction="attack:1"), "post_action_state": {"player": {"current_hp": 48}}},
            ]
            trace.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
            source = load_trace(trace, 4)
            rendered = render_html(source)
            self.assertEqual(source["raw"]["step"], 4)
            self.assertIn("post-action state only", rendered)
            self.assertIn("play_card", rendered)
            self.assertIn("run-1", rendered)

    def test_trace_duplicate_step_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "trace.jsonl"
            row = {"step": 4, "silver_evaluator": evaluator()}
            trace.write_text(json.dumps(row) + "\n" + json.dumps(row), encoding="utf-8")
            with self.assertRaisesRegex(RenderError, "exactly one"):
                load_trace(trace, 4)

    def test_differential_record_is_read_only_adapter(self):
        with tempfile.TemporaryDirectory() as directory:
            trace = Path(directory) / "differential.jsonl"
            record = {"record_type": "decision", "schema": "sts_differential_trace", "schemaVersion": 1,
                      "decisionIndex": 123, "boundary": "combat", "before": {"player": {"hp": 50}},
                      "after": {"player": {"hp": 44}}, "legalActions": [{"silver_fingerprint": "attack:1"}],
                      "selectedAction": {"identity": "silver:attack:1", "action": {"silver_fingerprint": "attack:1"}},
                      "mcpAction": {"tool": "play_card", "arguments": {"card_index": 1}},
                      "liveObservation": snapshot_data()["observation"]}
            trace.write_text(json.dumps(record), encoding="utf-8")
            source = load_differential_trace(trace, 123)
            rendered = render_html(source)
            self.assertIn("Before → after", rendered)
            self.assertIn("play_card", rendered)
            self.assertIn("Cultist", rendered)

    def test_differential_adapter_rejects_wrong_schema_and_ooc(self):
        with tempfile.TemporaryDirectory() as directory:
            base = {"record_type": "decision", "schema": "sts_differential_trace", "schemaVersion": 1,
                    "decisionIndex": 123, "boundary": "combat"}
            wrong_schema = dict(base, schema="other")
            path = self.write_jsonl(directory, "wrong-schema.jsonl", wrong_schema)
            with self.assertRaisesRegex(RenderError, "unsupported schema"):
                load_differential_trace(path, 123)
            ooc = dict(base, boundary="ooc")
            path = self.write_jsonl(directory, "ooc.jsonl", ooc)
            with self.assertRaisesRegex(RenderError, "not a combat"):
                load_differential_trace(path, 123)

    def write_jsonl(self, directory, name, *rows):
        path = Path(directory) / name
        path.write_text("\n".join(json.dumps(row) for row in rows), encoding="utf-8")
        return path

    def test_cli_writes_one_html_file(self):
        with tempfile.TemporaryDirectory() as directory:
            snapshot = self.write_json(directory, "latest.json", snapshot_data())
            output = Path(directory) / "decision.html"
            self.assertEqual(main(["--snapshot", str(snapshot), "--output", str(output)]), 0)
            self.assertTrue(output.is_file())
            self.assertTrue(output.read_text(encoding="utf-8").startswith("<!doctype html>"))


if __name__ == "__main__":
    unittest.main()
