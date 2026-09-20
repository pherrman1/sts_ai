import tempfile
import unittest
from pathlib import Path

from tools.differential_replay import replay
from tools.differential_rng import inspect_vanilla_rng
from tools.differential_trace import (
    DifferentialTraceError, DifferentialTraceWriter, action_identity, compare_legal_actions,
    compare_states, field_diffs, read_trace, resolve_unique_action,
)


def combat(fp):
    return {"silver_fingerprint": fp, "semantic": {"kind": "card"}}


def ooc(key):
    return {"semanticKey": key, "semantic": {"kind": "choose"}}


class DifferentialTraceTests(unittest.TestCase):
    def test_schema_round_trip_and_self_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            writer = DifferentialTraceWriter(path, run_id="run-1", provenance={"seed": 42})
            writer.write_decision({
                "step": 0, "pre_action_state": {"hp": 80, "ready_for_command": True},
                "post_action_state": {"hp": 75}, "legal_candidates": [combat("a")],
                "selected_candidate": combat("a"), "executed_mcp_tool": "play_card",
                "executed_mcp_arguments": {"card_index": 1}}, boundary="combat")
            writer.write_summary({"outcome": "complete"})
            rows = read_trace(path)
            self.assertEqual(rows[0]["schemaVersion"], 1)
            native = [{"state": {"hp": 80}, "legalActions": [combat("a")],
                       "after": {"hp": 75}}]
            self.assertEqual(replay(path, native)["category"], "RUN_COMPLETE_EQUIVALENT")

    def test_precise_state_and_rng_diffs(self):
        self.assertEqual(field_diffs({"player": {"hp": 80}}, {"player": {"hp": 79}})[0].path,
                         "player.hp")
        result = compare_states({"hp": 80}, {"hp": 80},
                                java_rng={"ai": [1, 2, 3]}, native_rng={"ai": [1, 2, 4]},
                                state_before_equal=True)
        self.assertEqual(result["category"], "RNG_CONSUMPTION_DIVERGENCE")

    def test_missing_ambiguous_and_legal_set_mismatch(self):
        self.assertEqual(compare_legal_actions([ooc("a")], [ooc("b")], "ooc")["category"],
                         "LEGAL_ACTION_SET_DIVERGENCE")
        with self.assertRaisesRegex(DifferentialTraceError, "NOT_FOUND"):
            resolve_unique_action("a", [ooc("b")], "ooc")
        with self.assertRaisesRegex(DifferentialTraceError, "AMBIGUOUS"):
            resolve_unique_action("a", [ooc("a"), ooc("a")], "ooc")

    def test_public_state_never_requires_hidden_rng(self):
        self.assertEqual(compare_states({"hp": 1, "debugRng": {"x": 1}},
                                         {"hp": 1, "debugRng": {"x": 2}})["category"], "EQUIVALENT")

    def test_vanilla_rng_preflight(self):
        jar = Path.home() / ".local/share/Steam/steamapps/common/SlayTheSpire/desktop-1.0.jar"
        result = inspect_vanilla_rng(jar)
        self.assertTrue(result["available"], result)
        self.assertEqual(result["captureContract"],
                         ["counter", "random.getState(0)", "random.getState(1)"])

    def test_identity_requires_native_replayable_key(self):
        with self.assertRaises(DifferentialTraceError):
            action_identity({"semantic": {"kind": "choose"}}, "ooc")


if __name__ == "__main__":
    unittest.main()
