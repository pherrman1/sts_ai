import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from tools.live_game_driver import (
    Driver,
    DriverError,
    InspectorSnapshot,
    IntegrationFailure,
    InspectorReader,
    LegalAction,
    TraceWriter,
    build_legal_actions,
    map_silver_action,
)


def combat_screen():
    return {
        "screen_type": "NONE",
        "room_phase": "COMBAT",
        "hand": [
            {"id": "Strike_R", "name": "Strike", "uuid": "strike-1", "has_target": True},
            {"id": "Strike_R", "name": "Strike", "uuid": "strike-2", "has_target": True},
            {"id": "Defend_R", "name": "Defend", "uuid": "defend-1", "has_target": False},
        ],
        "monsters": [
            {"id": "Cultist", "current_hp": 20},
            {"id": "JawWorm", "current_hp": 0, "is_gone": True},
        ],
    }


class FakeClient:
    def __init__(self, screen, commands):
        self.screen = screen
        self.commands = commands
        self.tool_names = {"get_screen_state", "get_available_commands", *commands}
        self.calls = []

    async def call(self, tool, arguments=None):
        self.calls.append((tool, arguments or {}))
        if tool == "get_screen_state":
            return self.screen
        if tool == "get_available_commands":
            return {"available_tools": [{"tool": name} for name in self.commands]}
        if tool in {"choose", "play_card", "end_turn"}:
            self.screen = {**self.screen, "step": self.screen.get("step", 0) + 1}
            return {"success": True}
        raise AssertionError(tool)


class FakeJev:
    def __init__(self, choice="a0"):
        self.choice = choice
        self.calls = 0

    async def choose(self, state, candidates):
        self.calls += 1
        if self.choice not in {candidate.id for candidate in candidates}:
            raise DriverError(f"JEV selected illegal candidate {self.choice!r}")
        return {"choice": self.choice, "probabilities": {self.choice: 1.0},
                "confidence": 1.0, "latency_ms": 0.1}


class LiveGameDriverTest(unittest.TestCase):
    def test_duplicate_cards_preserve_uuid_and_single_target(self):
        actions = [action for action in build_legal_actions(combat_screen(), ["play_card"])
                   if action.semantic.get("card_uuid", "").startswith("strike-")]
        self.assertEqual([action.mcp_arguments for action in actions], [
            {"card_index": 1, "target_index": 1},
            {"card_index": 2, "target_index": 1},
        ])
        self.assertIn("uuid=strike-1", actions[0].human_description)
        self.assertIn("uuid=strike-2", actions[1].human_description)

    def test_untargeted_card_and_end_turn(self):
        actions = build_legal_actions(combat_screen(), ["play_card", "end_turn"])
        self.assertEqual(actions[2].mcp_tool, "play_card")
        self.assertEqual(actions[2].mcp_arguments, {"card_index": 3})
        self.assertEqual(actions[3].mcp_tool, "end_turn")
        self.assertEqual(actions[3].mcp_arguments, {})

    def test_reward_and_event_choices_are_concrete(self):
        screen = {"screen_type": "CARD_REWARD", "choice_list": ["Bash", "Skip"]}
        actions = build_legal_actions(screen, ["choose", "skip"])
        self.assertEqual([action.mcp_arguments for action in actions],
                         [{"choice_index": 1}, {"choice_index": 2}, {}])

    def test_targeted_potion_has_one_candidate_per_live_target(self):
        screen = {"screen_type": "NONE", "room_phase": "COMBAT",
                  "potions": [{"id": "Fire Potion", "requires_target": True}],
                  "monsters": [{"id": "Cultist", "current_hp": 10},
                                {"id": "JawWorm", "current_hp": 0}]}
        actions = build_legal_actions(screen, ["use_potion"])
        self.assertEqual([action.mcp_arguments for action in actions],
                         [{"potion_slot": 1, "target_index": 1}])

    def test_select_cards_uses_explicit_server_options(self):
        screen = {"screen_type": "HAND_SELECT", "selection_options": [
            {"drop": [1]}, {"keep": [2, 3]},
        ]}
        actions = build_legal_actions(screen, ["select_cards"])
        self.assertEqual([action.mcp_arguments for action in actions],
                         [{"drop": [1]}, {"keep": [2, 3]}])

    def test_end_turn_has_stable_silver_fingerprint(self):
        actions = build_legal_actions({"screen_type": "NONE", "room_phase": "COMBAT"}, ["end_turn"])
        self.assertEqual(map_silver_action(actions[0].silver_fingerprint, actions).id, "a0")

    def test_silver_mapping_requires_exactly_one(self):
        candidates = [LegalAction("a0", "Strike", "play_card", {}, silver_fingerprint="fp-0")]
        self.assertEqual(map_silver_action("fp-0", candidates).id, "a0")
        with self.assertRaises(IntegrationFailure):
            map_silver_action("missing", candidates)
        ambiguous = candidates + [LegalAction("a1", "Strike copy", "play_card", {}, silver_fingerprint="fp-0")]
        with self.assertRaises(IntegrationFailure):
            map_silver_action("fp-0", ambiguous)

    def test_inspector_identity_and_stale_hash_fail_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.json"
            path.write_text(json.dumps({
                "protocol": "sts_model_inspector_latest_v1", "session": "s", "sequence": 2,
                "observationHash": "h2", "observation": {"boundary": "combat"},
                "response": {"ready": True, "session": "s", "sequence": 2,
                              "observationHash": "h2", "advisor": {"evaluators": []}},
            }))
            snapshot = InspectorSnapshot.load(path)
            with self.assertRaises(DriverError):
                snapshot.validate_current({"session": "s", "sequence": 1, "observationHash": "h1"})

    def test_explicit_unsupported_uses_jev_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.json"
            path.write_text(json.dumps({
                "session": "s", "sequence": 1, "observationHash": "h",
                "observation": {"boundary": "combat", "combat": {
                    "hand": combat_screen()["hand"],
                    "monsters": [{"id": "Cultist", "hp": 20},
                                  {"id": "JawWorm", "hp": 0}],
                }},
                "response": {"ready": True, "session": "s", "sequence": 1,
                              "observationHash": "h", "advisor": {"evaluators": [
                                  {"id": "silver_player_decision_v2", "status": "UNSUPPORTED",
                                   "reason": "smoke_bomb"}]}}},
            ))
            client = FakeClient(combat_screen(), ["play_card"])
            jev = FakeJev()
            with tempfile.TemporaryDirectory() as traces:
                driver = Driver(client, jev, InspectorReader(path, timeout=0.01),
                                TraceWriter(Path(traces) / "trace.jsonl"), dry_run=True)
                self.assertFalse(asyncio.run(driver.step(0)))
            self.assertEqual(jev.calls, 1)
            self.assertFalse(any(call[0] == "play_card" for call in client.calls))

    def test_jev_cannot_execute_outside_candidate_set(self):
        client = FakeClient({"screen_type": "CARD_REWARD", "choice_list": ["Bash"]}, ["choose"])
        jev = FakeJev("not-a0")
        with tempfile.TemporaryDirectory() as traces:
            driver = Driver(client, jev, InspectorReader(Path(traces) / "missing"),
                            TraceWriter(Path(traces) / "trace.jsonl"), dry_run=True)
            with self.assertRaises(DriverError):
                asyncio.run(driver.step(0))
        self.assertFalse(any(call[0] == "choose" for call in client.calls))

    def test_dry_run_performs_no_mutating_mcp_call(self):
        client = FakeClient({"screen_type": "CARD_REWARD", "choice_list": ["Bash"]}, ["choose"])
        with tempfile.TemporaryDirectory() as traces:
            path = Path(traces) / "trace.jsonl"
            driver = Driver(client, FakeJev(), InspectorReader(Path(traces) / "missing"),
                            TraceWriter(path), dry_run=True)
            self.assertFalse(asyncio.run(driver.step(0)))
            rows = [json.loads(line) for line in path.read_text().splitlines()]
        self.assertEqual([call[0] for call in client.calls], ["get_screen_state", "get_available_commands"])
        self.assertTrue(rows[0]["dry_run"])

    def test_trace_redacts_typesafe_api_key(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace.jsonl"
            TraceWriter(path, "secret-token").write({"TYPESAFE_API_KEY": "secret-token",
                                                       "result": "secret-token"})
            text = path.read_text()
        self.assertNotIn("secret-token", text)

    def test_mcp_state_advances_after_one_action(self):
        client = FakeClient({"screen_type": "CARD_REWARD", "choice_list": ["Bash"]}, ["choose"])
        with tempfile.TemporaryDirectory() as traces:
            driver = Driver(client, FakeJev(), InspectorReader(Path(traces) / "missing"),
                            TraceWriter(Path(traces) / "trace.jsonl"), poll_timeout=0.05)
            self.assertTrue(asyncio.run(driver.step(0)))
        self.assertEqual([call[0] for call in client.calls],
                         ["get_screen_state", "get_available_commands", "choose", "get_screen_state"])


if __name__ == "__main__":
    unittest.main()
