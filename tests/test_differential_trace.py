import tempfile
import unittest
import os
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
                "post_action_state": {"hp": 75}, "differential_legal_actions": [combat("a")],
                "selected_candidate": combat("a"), "executed_mcp_tool": "play_card",
                "executed_mcp_arguments": {"card_index": 1}}, boundary="combat")
            writer.write_summary({"outcome": "max_steps"})
            rows = read_trace(path)
            self.assertEqual(rows[0]["schemaVersion"], 1)
            native = [{"state": {"hp": 80}, "legalActions": [combat("a")],
                       "after": {"hp": 75}}]
            self.assertEqual(replay(path, native)["category"], "BOUNDED_PREFIX_EQUIVALENT")

    def test_captured_neow_intro_reports_precise_unsupported_boundary(self):
        path = Path(__file__).parent / "fixtures/differential/neow-intro-unsupported.jsonl"
        self.assertEqual(replay(path, []), {
            "category": "UNSUPPORTED_BOUNDARY", "decisionIndex": 1,
            "reason": "ooc_v4:EVENT_PHASE_UNREPRESENTABLE:Neow:1"})

    def test_empty_trace_cannot_pass_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "empty.jsonl"
            writer = DifferentialTraceWriter(path, run_id="empty")
            writer.write_summary({"outcome": "unsupported_boundary"})
            self.assertEqual(replay(path, []), {
                "category": "TRACE_OR_SCHEMA_ERROR", "decisionCount": 0,
                "reason": "no_decisions_captured"})

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
        configured = os.environ.get("STS_VANILLA_JAR")
        if not configured:
            self.skipTest("set STS_VANILLA_JAR for the local installed-game integration probe")
        jar = Path(configured)
        result = inspect_vanilla_rng(jar)
        self.assertTrue(result["available"], result)
        self.assertEqual(result["captureContract"],
                         ["counter", "random.getState(0)", "random.getState(1)"])

    def test_identity_requires_native_replayable_key(self):
        with self.assertRaises(DifferentialTraceError):
            action_identity({"semantic": {"kind": "choose"}}, "ooc")

    def test_trace_unsupported_boundary_is_not_a_state_mismatch(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            writer = DifferentialTraceWriter(path, run_id="run-unsupported")
            writer._write({"record_type": "decision", "schema": "sts_differential_trace",
                           "schemaVersion": 1, "traceId": writer.run_id, "decisionIndex": 3,
                           "boundary": "ooc", "traceError": {
                               "category": "UNSUPPORTED_BOUNDARY", "reason": "selector_type:transform"}})
            writer.write_summary({"outcome": "unsupported_boundary"})
            result = replay(path, [])
            self.assertEqual(result["category"], "UNSUPPORTED_BOUNDARY")
            self.assertEqual(result["reason"], "selector_type:transform")

    def test_post_action_rng_only_difference_is_classified(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            writer = DifferentialTraceWriter(path, run_id="run-rng")
            writer.write_decision({"step": 0, "pre_action_state": {"hp": 80},
                "post_action_state": {"hp": 80}, "differential_legal_actions": [combat("a")],
                "selected_candidate": combat("a"), "preRng": {"ai": [0, "1", "2"]},
                "postRng": {"ai": [1, "3", "4"]}}, boundary="combat")
            writer.write_summary({"outcome": "max_steps"})
            result = replay(path, [{"state": {"hp": 80}, "legalActions": [combat("a")],
                "rng": {"ai": [0, "1", "2"]}, "after": {"hp": 80},
                "postRng": {"ai": [1, "3", "5"]}}])
            self.assertEqual(result["category"], "RNG_CONSUMPTION_DIVERGENCE")


if __name__ == "__main__":
    unittest.main()
