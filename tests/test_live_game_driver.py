import asyncio
import json
import tempfile
import unittest
from pathlib import Path

from tools.live_game_driver import (
    Driver, DriverError, InspectorSnapshot, InspectorReader, IntegrationFailure,
    LegalAction, TraceWriter, build_legal_actions, choose_deterministic_action,
    map_silver_action, normalize_game_state, state_identity,
)


def combat_screen(**extra):
    return {"screen_type": "NONE", "room_phase": "COMBAT", "ready_for_command": True,
            "hand": [
                {"id": "Strike_R", "name": "Strike", "uuid": "strike-1", "has_target": True},
                {"id": "Strike_R", "name": "Strike", "uuid": "strike-2", "has_target": True},
                {"id": "Defend_R", "name": "Defend", "uuid": "defend-1", "has_target": False},
            ], "monsters": [{"id": "Cultist", "current_hp": 20}, {"id": "JawWorm", "current_hp": 0}], **extra}


class FakeClient:
    def __init__(self, states, commands, game_state=None):
        self.states = list(states) if isinstance(states, list) else [states]
        self.commands = commands
        self.game_state = game_state
        self.tool_names = {"get_screen_state", "get_available_commands", *commands}
        if game_state is not None:
            self.tool_names.add("get_game_state")
        self.calls = []

    async def call(self, tool, arguments=None):
        self.calls.append((tool, arguments or {}))
        if tool == "get_screen_state":
            return self.states.pop(0) if len(self.states) > 1 else self.states[0]
        if tool == "get_available_commands":
            return {"ready_for_command": True, "available_tools": [{"tool": name} for name in self.commands]}
        if tool == "get_game_state":
            return self.game_state
        if tool in self.commands:
            if len(self.states) == 1:
                self.states[0] = {**self.states[0], "step": self.states[0].get("step", 0) + 1}
            return {"success": True}
        raise AssertionError(tool)


def inspector_file(directory, status="UNSUPPORTED", **fields):
    path = Path(directory) / "latest.json"
    evaluator = {"id": "silver_player_decision_v2", "status": status, "reason": "test", **fields}
    path.write_text(json.dumps({"session": "s", "sequence": 1, "observationHash": "h",
                                "observation": {"boundary": "combat"},
                                "response": {"ready": True, "session": "s", "sequence": 1,
                                              "observationHash": "h", "advisor": {"evaluators": [evaluator]}}}))
    return path


class LiveGameDriverTest(unittest.TestCase):
    def test_duplicate_cards_preserve_uuid_and_single_target(self):
        actions = [a for a in build_legal_actions(combat_screen(), ["play_card"])
                   if a.semantic.get("card_uuid", "").startswith("strike-")]
        self.assertEqual([a.mcp_arguments for a in actions], [{"card_index": 1, "target_index": 1}, {"card_index": 2, "target_index": 1}])
        self.assertEqual(choose_deterministic_action(combat_screen(), actions).semantic["card_uuid"], "strike-1")

    def test_nested_game_state_potions_are_candidates(self):
        nested = {"ready_for_command": True, "in_game": True, "game_state": {
            "potions": [{"id": "Fire Potion", "requires_target": True}],
            "combat_state": {"monsters": [{"id": "Cultist", "current_hp": 10}]}}}
        self.assertEqual(normalize_game_state(nested)["potions"][0]["id"], "Fire Potion")
        actions = build_legal_actions({"screen_type": "NONE", "room_phase": "COMBAT"}, ["use_potion"], nested)
        self.assertEqual(actions[0].mcp_arguments, {"potion_slot": 1, "target_index": 1})

    def test_selected_live_action_maps_duplicate_uuid(self):
        actions = build_legal_actions(combat_screen(), ["play_card"])
        self.assertEqual(map_silver_action({"kind": "card", "cardUuid": "strike-2", "targetIndex": 1}, actions).mcp_arguments,
                         {"card_index": 2, "target_index": 1})
        with self.assertRaises(IntegrationFailure):
            map_silver_action({"kind": "card", "cardUuid": "wrong", "targetIndex": 1}, actions)

    def test_selected_live_action_ambiguous_and_label_only_fail(self):
        candidates = [LegalAction("a0", "same", "play_card", {}, {"kind": "card", "card_uuid": "x"}),
                      LegalAction("a1", "same", "play_card", {}, {"kind": "card", "card_uuid": "x"})]
        with self.assertRaises(IntegrationFailure):
            map_silver_action({"kind": "card", "cardUuid": "x"}, candidates)
        with self.assertRaises(IntegrationFailure):
            map_silver_action("same", candidates)

    def test_silver_ok_does_not_fallback_when_mapping_missing(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(combat_screen(session="s", sequence=1, observationHash="h"), ["play_card"])
            path = inspector_file(directory, "OK", selectedAction="diagnostic-only")
            driver = Driver(client, InspectorReader(path, timeout=.01), TraceWriter(Path(directory) / "trace"), dry_run=True)
            with self.assertRaises(IntegrationFailure):
                asyncio.run(driver.step(0))
            self.assertFalse(any(call[0] == "play_card" for call in client.calls))

    def test_unsupported_combat_chooses_first_card_then_end_turn(self):
        cards = build_legal_actions(combat_screen(), ["play_card", "end_turn"])
        self.assertEqual(choose_deterministic_action(combat_screen(), cards).mcp_tool, "play_card")
        self.assertEqual(choose_deterministic_action(combat_screen(hand=[]), build_legal_actions(combat_screen(hand=[]), ["play_card", "end_turn"])).mcp_tool, "end_turn")

    def test_strict_unsupported_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(combat_screen(), ["play_card"])
            driver = Driver(client, InspectorReader(inspector_file(directory), timeout=.01), TraceWriter(Path(directory) / "trace"), strict_silver=True, dry_run=False)
            with self.assertRaises(DriverError):
                asyncio.run(driver.step(0))
            self.assertFalse(any(call[0] == "play_card" for call in client.calls))

    def test_policy_is_deterministic(self):
        screen = {"screen_type": "CARD_REWARD", "choice_list": ["Bash"], "ready_for_command": True}
        actions = build_legal_actions(screen, ["proceed", "choose"])
        self.assertEqual(choose_deterministic_action(screen, actions).id, choose_deterministic_action(screen, actions).id)

    def test_reward_collects_before_proceed(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Gold"], "ready_for_command": True}
        actions = build_legal_actions(screen, ["proceed", "choose"])
        self.assertEqual(choose_deterministic_action(screen, actions).mcp_tool, "choose")

    def test_shop_leaves(self):
        screen = {"screen_type": "SHOP_SCREEN", "ready_for_command": True}
        actions = build_legal_actions(screen, ["cancel", "proceed"])
        self.assertEqual(choose_deterministic_action(screen, actions).mcp_tool, "cancel")

    def test_state_identity_ignores_readiness(self):
        self.assertEqual(state_identity({"step": 1, "ready_for_command": True}), state_identity({"step": 1, "ready_for_command": False}))

    def test_transient_ready_state_waits_for_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            states = [
                {"screen_type": "CARD_REWARD", "choice_list": ["Bash"], "ready_for_command": True},
                {"screen_type": "CARD_REWARD", "choice_list": ["Bash"], "ready_for_command": False},
                {"screen_type": "CARD_REWARD", "choice_list": ["Bash", "Gold"], "ready_for_command": True},
            ]
            client = FakeClient(states, ["choose"])
            driver = Driver(client, InspectorReader(Path(directory) / "missing"), TraceWriter(Path(directory) / "trace"), poll_timeout=.2, poll_interval=.001)
            self.assertTrue(asyncio.run(driver.step(0)))
            self.assertEqual(client.calls[-1][0], "get_available_commands")

    def test_wait_ready_timeout_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient({"screen_type": "CARD_REWARD", "choice_list": ["Bash"], "ready_for_command": False}, ["choose"])
            driver = Driver(client, InspectorReader(Path(directory) / "missing"), TraceWriter(Path(directory) / "trace"), dry_run=True, poll_timeout=.01, poll_interval=.001)
            with self.assertRaises(DriverError):
                asyncio.run(driver.step(0))

    def test_dry_run_never_mutates(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient({"screen_type": "CARD_REWARD", "choice_list": ["Bash"], "ready_for_command": True}, ["choose"])
            path = Path(directory) / "trace"
            driver = Driver(client, InspectorReader(Path(directory) / "missing"), TraceWriter(path), dry_run=True)
            self.assertFalse(asyncio.run(driver.step(0)))
            self.assertFalse(any(call[0] == "choose" for call in client.calls))
            self.assertTrue(json.loads(path.read_text())["dry_run"])

    def test_inspector_identity_fails_closed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = inspector_file(directory)
            snapshot = InspectorSnapshot.load(path)
            with self.assertRaises(DriverError):
                snapshot.validate_current({"session": "s", "sequence": 2, "observationHash": "h"})

    def test_trace_redacts_secret_named_fields(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "trace"
            TraceWriter(path).write({"api_key": "secret", "result": "secret"})
            self.assertIn('[REDACTED]', path.read_text())


if __name__ == "__main__":
    unittest.main()
