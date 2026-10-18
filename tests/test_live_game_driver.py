import asyncio
import gzip
import json
import tempfile
import unittest
from pathlib import Path

from tools.live_game_driver import (
    CandidateEnumerationError, Driver, DriverError, InspectorSnapshot, InspectorReader, IntegrationFailure,
    LegalAction, TraceWriter, build_legal_actions, choose_deterministic_action,
    map_silver_action, map_ooc_action, normalize_game_state, state_identity, transition_identity, main,
    _is_combat, card_reward_reveal_action, boss_completion_proceed_action, victory_dialogue_action,
    hand_selection_transaction, grid_selection_transaction,
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


def ooc_inspector_file(directory, screen, status="UNSUPPORTED", **fields):
    path = Path(directory) / "latest.json"
    selected = fields.pop("selectedLiveAction", {"kind": "choose", "choiceIndex": 1})
    evaluator = {"id": "live_ooc_decision_v1", "policy": "mcts_ctm", "status": status,
                 "reason": "fixture", "selectedSemanticKey": "choice:1",
                 "selectedLiveAction": selected, "latencyMicros": 12, "scorerLatencyMicros": 5,
                 "candidateSummaries": [{"semanticKey": "choice:1", "q": 1.0, "visits": 1,
                                          "visitShare": 1.0, "prior": 1.0, "liveAction": selected}], **fields}
    path.write_text(json.dumps({"session": "s", "sequence": 1, "observationHash": "h",
        "observation": {"boundary": "ooc", "ooc": {"schemaVersion": 1,
            "screen": {"CARD_REWARD": "card_reward", "MAP": "map", "SHOP_ROOM": "shop_room",
                       "SHOP_SCREEN": "shop"}.get(screen.get("screen_type"), "event"),
            "publicState": {}, "liveChoices": [], "mcpState": screen}},
        "response": {"ready": True, "session": "s", "sequence": 1, "observationHash": "h",
                     "advisor": {"evaluators": [evaluator]}}}))
    return path


class LiveGameDriverTest(unittest.TestCase):
    def test_transition_timeout_is_forwarded_and_preserved_for_reproduction(self):
        from contextlib import asynccontextmanager
        from unittest.mock import patch
        @asynccontextmanager
        async def connection(url):
            yield FakeClient({"screen_type": "GAME_OVER", "screen_state": {"victory": False}}, [])
        with tempfile.TemporaryDirectory() as directory, \
                patch("tools.live_game_driver.connected_mcp", connection), \
                patch("tools.live_game_driver.Driver", wraps=Driver) as factory:
            self.assertEqual(main(["--transition-timeout", "45", "--trace", str(Path(directory)/"trace")]), 0)
            self.assertEqual(factory.call_args.kwargs["poll_timeout"], 45)
            self.assertIn("--transition-timeout 45.0", factory.call_args.kwargs["reproduction_command"])

    def test_transition_timeout_rejects_unbounded_or_nonpositive_budgets(self):
        import contextlib, io
        for value in ("0", "-1", "nan", "inf"):
            with self.subTest(value=value), contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as error:
                    main(["--transition-timeout", value])
                self.assertEqual(error.exception.code, 2)

    def test_inspector_reader_waits_for_delayed_matching_response(self):
        async def delayed_write(path):
            await asyncio.sleep(0.02)
            path.write_text(json.dumps({"session": "s", "sequence": 1, "observationHash": "h",
                                        "observation": {"boundary": "combat", "combat": {
                                            "hand": [{"uuid": "strike-1"}],
                                            "monsters": [{"id": "Cultist", "hp": 20}]}},
                                        "response": {"ready": True, "session": "s", "sequence": 1,
                                                      "observationHash": "h", "advisor": {"evaluators": [
                                                          {"id": "silver_player_decision_v2", "status": "UNSUPPORTED",
                                                           "reason": "delayed-test"}]}}}))

        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.json"
            async def exercise():
                writer = asyncio.create_task(delayed_write(path))
                snapshot = await InspectorReader(path, timeout=0.2, poll_interval=0.001).read_for(
                    {"screen_type": "NONE", "room_phase": "COMBAT",
                     "hand": [{"uuid": "strike-1"}],
                     "monsters": [{"id": "Cultist", "current_hp": 20}]})
                await writer
                return snapshot

            snapshot = asyncio.run(exercise())
            self.assertEqual((snapshot.session, snapshot.sequence, snapshot.observation_hash), ("s", 1, "h"))

    def test_duplicate_cards_preserve_uuid_and_single_target(self):
        actions = [a for a in build_legal_actions(combat_screen(), ["play_card"])
                   if a.semantic.get("card_uuid", "").startswith("strike-")]
        self.assertEqual([a.mcp_arguments for a in actions], [{"card_index": 1, "target_index": 1}, {"card_index": 2, "target_index": 1}])
        self.assertEqual(choose_deterministic_action(combat_screen(), actions).semantic["card_uuid"], "strike-1")

    def test_nested_game_state_potions_are_candidates(self):
        nested = {"ready_for_command": True, "in_game": True, "game_state": {
            "potions": [{"id": "Fire Potion", "requires_target": True, "can_use": True}],
            "combat_state": {"monsters": [{"id": "Cultist", "current_hp": 10}]}}}
        self.assertEqual(normalize_game_state(nested)["potions"][0]["id"], "Fire Potion")
        actions = build_legal_actions({"screen_type": "NONE", "room_phase": "COMBAT"}, ["use_potion"], nested)
        self.assertEqual(actions[0].mcp_arguments, {"potion_slot": 1, "target_index": 1})

    def test_potion_candidates_require_advertised_legality(self):
        screen = {"screen_type": "NONE", "room_phase": "COMBAT", "potions": [
            {"id": "Block Potion", "can_discard": True},
            {"id": "Dexterity Potion", "can_use": True},
        ], "monsters": [{"name": "Cultist", "current_hp": 10}]}
        self.assertEqual([a.mcp_arguments for a in build_legal_actions(screen, ["use_potion"])], [{"potion_slot": 2}])
        self.assertEqual([a.mcp_arguments for a in build_legal_actions(screen, ["discard_potion"])], [{"potion_slot": 1}])

    def test_discard_targeted_potion_never_requires_a_monster(self):
        for monsters in ([], [{"id": "Cultist", "current_hp": 20}]):
            screen = {"screen_type": "COMBAT_REWARD", "potions": [
                {"id": "Fire Potion", "can_discard": True, "requires_target": True}],
                "monsters": monsters}
            actions = build_legal_actions(screen, ["discard_potion"])
            self.assertEqual([a.mcp_arguments for a in actions], [{"potion_slot": 1}])

    def test_hand_selection_transaction_preserves_uuid_order_and_stops_on_drift(self):
        import itertools
        contracts = (("FORETHOUGHT", "unique.ForethoughtAction", 99),
                     ("GAMBLE", "unique.GamblingChipAction", 99),
                     ("EXHAUST_MANY", "common.ExhaustAction", 3),
                     ("EXHAUST_MANY", "common.ExhaustAction", 5),
                     ("EXHAUST_MANY", "common.ExhaustAction", 99))
        for selected, (task, owner, count) in itertools.product(([], ["a", "c"], ["a", "b", "c"], list("abcde")), contracts):
            if len(selected) > count:
                continue
            for drift in (False, True):
                if not selected and drift:
                    continue
                with self.subTest(task=task, count=count, selected=selected, drift=drift), tempfile.TemporaryDirectory() as directory:
                    cards = [{"uuid": uuid, "id": "Strike_R"} for uuid in ("a", "b", "c", "d", "e")]
                    screen = dict(screen_type="HAND_SELECT", room_phase="COMBAT", ready_for_command=True,
                                  can_proceed=True, hand=list(cards), choice_list=["Strike"]*5,
                                  screen_state=dict(hand=list(cards), selected=[], max_cards=count, can_pick_zero=True))
                    observation = dict(combat=dict(hand=cards, cardSelect=dict(
                        task=task, origin="HAND_SELECT", canPickAnyNumber=True, canPickZero=True,
                        pickCount=count, selectedCount=0, selectedBits=0,
                        actionClass="com.megacrit.cardcrawl.actions." + owner,
                        liveChoices=[dict(uuid=c["uuid"], choiceIndex=i+1) for i,c in enumerate(cards)])))
                    action = hand_selection_transaction(dict(kind="card_select",cardUuids=selected), observation, screen)
                    class SelectingClient(FakeClient):
                        async def call(self, tool, arguments=None):
                            if tool == "choose":
                                self.calls.append((tool, arguments))
                                current = self.states[0]
                                index = arguments["choice_index"]-1
                                card = current["hand"].pop(index)
                                current["screen_state"]["hand"] = list(current["hand"])
                                current["screen_state"]["selected"].append(card)
                                current["choice_list"].pop(index)
                                if len(current["screen_state"]["selected"]) == count:
                                    current["choice_list"] = []
                                if drift:
                                    current["screen_state"]["selected"][0] = {"uuid": "unexpected"}
                                return {"success": True}
                            return await super().call(tool,arguments)
                    client = SelectingClient(screen,["choose","confirm","select_cards"])
                    driver = Driver(client,InspectorReader(inspector_file(directory)),TraceWriter(Path(directory)/"trace"))
                    async def exercise():
                        # A ready snapshot is owned by the caller, not the MCP response object.
                        import copy
                        first = copy.deepcopy(screen)
                        return await driver.execute_hand_selection_transaction(action,first,
                            {"tools":["choose","confirm"]},{})
                    if drift:
                        with self.assertRaises(IntegrationFailure):
                            asyncio.run(exercise())
                        self.assertFalse(any(tool=="confirm" for tool,_ in client.calls))
                    else:
                        asyncio.run(exercise())
                        calls=[(tool,args) for tool,args in client.calls if tool in {"choose","confirm","select_cards"}]
                        remaining=list("abcde")
                        expected=[]
                        for uuid in selected:
                            index=remaining.index(uuid)
                            expected.append(("choose",{"choice_index":index+1}))
                            remaining.pop(index)
                        self.assertEqual(calls,expected+[("confirm",{})])
                        self.assertEqual([card["uuid"] for card in client.states[0]["screen_state"]["selected"]],selected)
                    for bad in (["c","a"],["a","a"],["absent"]):
                        with self.assertRaises(IntegrationFailure):
                            hand_selection_transaction(dict(kind="card_select",cardUuids=bad),observation,screen)

    def test_hand_selection_transaction_rejects_wrong_owner_partial_or_excess_picks(self):
        import copy
        cards = [{"uuid": str(i), "id": "Strike_R"} for i in range(5)]
        screen = dict(screen_type="HAND_SELECT", room_phase="COMBAT", hand=cards, choice_list=["Strike"]*5,
                      screen_state=dict(hand=cards, selected=[], max_cards=3, can_pick_zero=True))
        selection = dict(task="EXHAUST_MANY", origin="HAND_SELECT", canPickAnyNumber=True, canPickZero=True,
                         pickCount=3, selectedCount=0, selectedBits=0,
                         actionClass="com.megacrit.cardcrawl.actions.common.ExhaustAction",
                         liveChoices=[dict(uuid=c["uuid"], choiceIndex=i+1) for i,c in enumerate(cards)])
        observation = dict(combat=dict(hand=cards, cardSelect=selection))
        wanted = dict(kind="card_select", cardUuids=["0", "2", "4"])
        hand_selection_transaction(wanted, observation, screen)
        source_owned = copy.deepcopy(observation)
        source_owned["combat"]["cardSelect"]["continuation"] = "source_card_actions"
        source_owned["combat"]["pendingActionQueue"] = [{"kind": 12, "amount": 0, "status": 0, "sourceMonster": False}]
        source_owned["combat"]["pendingCardQueue"] = []
        hand_selection_transaction(wanted, source_owned, screen)
        for field, value in (("pendingActionQueue", []), ("pendingActionQueue", None),
                             ("pendingCardQueue", None)):
            with self.subTest(queue=field, value=value), self.assertRaises(IntegrationFailure):
                changed = copy.deepcopy(source_owned)
                changed["combat"][field] = value
                hand_selection_transaction(wanted, changed, screen)
        for field, value in (("actionClass", "com.megacrit.cardcrawl.actions.unique.GamblingChipAction"),
                             ("selectedCount", 1), ("selectedBits", False), ("pickCount", 4),
                             ("canPickZero", False), ("canPickAnyNumber", False)):
            with self.subTest(field=field), self.assertRaises(IntegrationFailure):
                changed = copy.deepcopy(observation)
                changed["combat"]["cardSelect"][field] = value
                hand_selection_transaction(wanted, changed, screen)
        with self.assertRaises(IntegrationFailure):
            hand_selection_transaction(dict(kind="card_select",cardUuids=["0","1","2","3"]), observation, screen)
        screen["screen_state"]["max_cards"] = 5
        with self.assertRaises(IntegrationFailure):
            hand_selection_transaction(wanted, observation, screen)

    def test_liquid_memories_grid_pair_preserves_order_and_stops_on_drift(self):
        import copy
        for wanted in (["a", "c"], ["c", "a"]):
            for drift in (None, "selected", "cards", "limit", "closed", "command"):
                with self.subTest(wanted=wanted, drift=drift), tempfile.TemporaryDirectory() as directory:
                    cards = [{"uuid": uuid, "id": "Strike_R"} for uuid in ("c", "a", "b")]
                    screen = dict(screen_type="GRID", room_phase="COMBAT", ready_for_command=True,
                                  choice_list=["Strike"]*3, can_proceed=False,
                                  screen_state=dict(cards=cards, selected_cards=[], num_cards=2,
                                      any_number=False, for_upgrade=False, for_transform=False, for_purge=False, confirm_up=False))
                    selection = dict(task="LIQUID_MEMORIES_POTION", origin="GRID",
                                     actionClass="com.megacrit.cardcrawl.actions.common.BetterDiscardPileToHandAction",
                                     pickCount=2, selectedCount=0, selectedBits=0, canPickZero=False,
                                     canPickAnyNumber=False, setCostToZero=True, newCost=0, optional=False, continuation="none",
                                     liveChoices=[dict(uuid=c["uuid"],choiceIndex=i+1) for i,c in enumerate(cards)])
                    observation = dict(combat=dict(discard=list(reversed(cards)),cardSelect=selection))
                    if wanted[0] == "c":
                        selection["continuation"]="public_actions"
                        observation["combat"]["pendingActionQueue"]=[dict(kind="DRAW",amount=1)]
                    action = grid_selection_transaction(dict(kind="grid_card_select",cardUuids=wanted),observation,screen)
                    class SelectingGridClient(FakeClient):
                        async def call(self, tool, arguments=None):
                            if tool == "choose":
                                self.calls.append((tool,arguments))
                                current = self.states[0]
                                state = current["screen_state"]
                                state["selected_cards"].append(state["cards"][arguments["choice_index"]-1])
                                if len(state["selected_cards"]) == 2:
                                    current["screen_type"] = "NONE"
                                elif drift == "selected": state["selected_cards"] = [{"uuid":"unexpected"}]
                                elif drift == "cards": state["cards"] = list(reversed(state["cards"]))
                                elif drift == "limit": state["num_cards"] = 1
                                elif drift == "closed": current["screen_type"] = "NONE"
                                elif drift == "command": self.commands = []
                                return {"success":True}
                            return await super().call(tool,arguments)
                    client = SelectingGridClient(copy.deepcopy(screen),["choose"])
                    driver = Driver(client,InspectorReader(inspector_file(directory)),TraceWriter(Path(directory)/"trace"))
                    async def exercise():
                        return await driver.execute_grid_selection_transaction(action,copy.deepcopy(screen),{"tools":["choose"]},{})
                    if drift:
                        with self.assertRaises(DriverError): asyncio.run(exercise())
                        self.assertEqual(len([c for c in client.calls if c[0]=="choose"]),1)
                    else:
                        asyncio.run(exercise())
                        self.assertEqual([c for c in client.calls if c[0] in {"choose","confirm","proceed"}],
                                         [("choose",{"choice_index":"cab".index(uuid)+1}) for uuid in wanted])
                    for bad in (["a"],["a","a"],["a","absent"],[]):
                        with self.assertRaises(IntegrationFailure):
                            grid_selection_transaction(dict(kind="grid_card_select",cardUuids=bad),observation,screen)
                    for key,bad in (("actionClass","unknown"),("pickCount",1),("selectedCount",1),
                                    ("optional",True),("newCost",1),("continuation","end_turn")):
                        changed=copy.deepcopy(observation);changed["combat"]["cardSelect"][key]=bad
                        with self.assertRaises(IntegrationFailure):
                            grid_selection_transaction(dict(kind="grid_card_select",cardUuids=wanted),changed,screen)

    def test_start_game_requires_character_and_none_is_not_combat(self):
        with self.assertRaises(CandidateEnumerationError):
            build_legal_actions({"screen_type": "MAIN_MENU"}, ["start_game"])
        self.assertEqual(build_legal_actions({"screen_type": "MAIN_MENU", "character": "IRONCLAD"}, ["start_game"])[0].mcp_arguments,
                         {"character": "IRONCLAD"})
        self.assertFalse(_is_combat({"screen_type": "NONE"}))
        self.assertTrue(_is_combat({"screen_type": "NONE", "room_phase": "COMBAT"}))

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

    def test_unknown_hand_selection_in_monster_and_event_combat_falls_back_once(self):
        fixture = Path(__file__).parent / "fixtures/live_combat_boundaries/fresh-a0.jsonl.failure.json.gz"
        with gzip.open(fixture, "rt") as stream:
            recorded_screen = json.load(stream)["screen"]
        for room_type in ("MonsterRoom", "EventRoom"):
            with self.subTest(room_type=room_type), tempfile.TemporaryDirectory() as directory:
                screen = {**recorded_screen, "room_type": room_type}
                self.assertTrue(screen["screen_state"]["can_pick_zero"])
                client = FakeClient(screen, ["choose", "confirm"])
                path = inspector_file(directory, reason="silver_unmapped_selection_task")
                raw = json.loads(path.read_text())
                raw["observation"]["combat"] = {"hand": screen["hand"], "cardSelect": {
                    "task": "", "canPickZero": True}}
                path.write_text(json.dumps(raw))
                trace = Path(directory) / "trace"
                driver = Driver(client, InspectorReader(path), TraceWriter(trace), max_steps=1)
                asyncio.run(driver.run())
                self.assertEqual([(tool, args) for tool, args in client.calls
                                  if tool in {"choose", "confirm"}], [("choose", {"choice_index": 1})])
                self.assertEqual(driver.counters["silver_unsupported"], 1)
                self.assertEqual(driver.counters["deterministic_fallback_combat"], 1)
                self.assertEqual(driver.counters["ooc_v4_unsupported"], 0)
                row = json.loads(trace.read_text().splitlines()[0])
                self.assertEqual(row["inspector_boundary"], "combat")
                self.assertEqual(row["fallback_reason"], "silver_unsupported:silver_unmapped_selection_task")

    def test_parity_trace_records_observation_rng_and_post_screen(self):
        fixture = Path(__file__).parent / "fixtures/live_combat_boundaries/fresh-a0.jsonl.failure.json.gz"
        with gzip.open(fixture, "rt") as stream:
            screen = {**json.load(stream)["screen"], "room_type": "MonsterRoom"}
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(screen, ["choose", "confirm"])
            path = inspector_file(directory, reason="silver_unmapped_selection_task")
            raw = json.loads(path.read_text())
            raw["observation"]["combat"] = {"hand": screen["hand"], "cardSelect": {"task": "", "canPickZero": True}}
            raw["debugRng"] = {"schema": "sts_java_rng_v1", "available": True, "streams": {}, "drawPileUuids": []}
            path.write_text(json.dumps(raw))
            trace = Path(directory) / "trace"
            driver = Driver(client, InspectorReader(path), TraceWriter(trace), max_steps=1, parity_trace=True)
            asyncio.run(driver.run())
            row = json.loads(trace.read_text().splitlines()[0])
            self.assertEqual(row["live_observation"], raw["observation"])
            self.assertEqual(row["preRng"], raw["debugRng"])
            self.assertEqual(set(row["post_screen_kind"]), {"combat", "terminal", "outcome", "screen_type"})

    def test_policy_is_deterministic(self):
        screen = {"screen_type": "CARD_REWARD", "choice_list": ["Bash"], "ready_for_command": True}
        actions = build_legal_actions(screen, ["proceed", "choose"])
        self.assertEqual(choose_deterministic_action(screen, actions).id, choose_deterministic_action(screen, actions).id)

    def test_reward_collects_before_proceed(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Gold"], "ready_for_command": True}
        actions = build_legal_actions(screen, ["proceed", "choose"])
        self.assertEqual(choose_deterministic_action(screen, actions).mcp_tool, "choose")

    def test_card_reveal_waits_for_parent_rewards(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Gold", "Anchor", "Card"],
                  "ready_for_command": True}
        game = {"screen_state": {"rewards": [
            {"reward_type": "GOLD"}, {"reward_type": "RELIC"}, {"reward_type": "CARD"}]}}
        candidates = build_legal_actions(screen, ["choose"])
        self.assertIsNone(card_reward_reveal_action(screen, game, candidates))
        without_gold = [candidate for candidate in candidates if candidate.mcp_arguments != {"choice_index": 1}]
        self.assertEqual(card_reward_reveal_action(screen, game, without_gold).mcp_arguments,
                         {"choice_index": 3})
        card_only = [candidate for candidate in candidates if candidate.mcp_arguments == {"choice_index": 3}]
        self.assertEqual(card_reward_reveal_action(screen, game, card_only).mcp_arguments,
                         {"choice_index": 3})

    def test_full_belt_card_reveal_preserves_parent_potion(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Speed Potion", "Card"], "ready_for_command": True}
        game = {"screen_state": {"rewards": [{"reward_type": "POTION"}, {"reward_type": "CARD"}]},
                "potions": [{"id": "Fire Potion", "can_discard": True}] * 3}
        candidates = build_legal_actions(screen, ["choose", "discard_potion"], game)
        self.assertEqual(card_reward_reveal_action(screen, game, candidates).mcp_arguments, {"choice_index": 2})
        game["potions"][0] = {"id": "Potion Slot"}
        self.assertIsNone(card_reward_reveal_action(screen, game, candidates))
        game.pop("potions")
        self.assertIsNone(card_reward_reveal_action(screen, game, candidates))
        game["potions"] = [{"id": "Potion Slot"}] * 3
        game["relics"] = [{"id": "Sozu"}]
        self.assertEqual(card_reward_reveal_action(screen, game, candidates).mcp_arguments, {"choice_index": 2})
        game.pop("relics")
        game["potions"] = [{"id": "Potion Slot"}, {"id": "Fire Potion"}, {"id": "Fire Potion"}]
        game["screen_state"]["rewards"].insert(1, {"reward_type": "POTION"})
        screen["choice_list"] = ["Speed Potion", "Weak Potion", "Card"]
        candidates = build_legal_actions(screen, ["choose"], game)
        self.assertEqual(card_reward_reveal_action(screen, game, candidates).mcp_arguments, {"choice_index": 3})

    def test_card_reveal_breaks_public_relic_potion_ordering_deadlock(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Preserved Insect", "Fairy in a Bottle", "card"],
                  "ready_for_command": True}
        game = {"screen_state": {"rewards": [{"reward_type": "RELIC"}, {"reward_type": "POTION"}, {"reward_type": "CARD"}]},
                "potions": [{"id": "Potion Slot"}] * 3}
        candidates = build_legal_actions(screen, ["choose", "proceed"], game)
        self.assertEqual(card_reward_reveal_action(screen, game, candidates).mcp_arguments, {"choice_index": 3})
        # Without the relic, the existing qualified forced-potion path applies.
        without_relic = [c for c in candidates if c.mcp_arguments != {"choice_index": 1}]
        self.assertIsNone(card_reward_reveal_action(screen, game, without_relic))
        game.pop("potions")
        self.assertIsNone(card_reward_reveal_action(screen, game, candidates))

    def test_multiple_card_groups_reveal_first_undeclined_physical_occurrence(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Gold", "Card", "Card", "Card"],
                  "ready_for_command": True}
        game = {"screen_state": {"rewards": [{"reward_type": kind} for kind in ("GOLD","CARD","CARD","CARD")]}}
        candidates = build_legal_actions(screen, ["choose", "proceed"])
        self.assertIsNone(card_reward_reveal_action(screen, game, candidates))
        remaining = [c for c in candidates if c.mcp_arguments.get("choice_index") != 1]
        for index in (2, 3, 4):
            self.assertEqual(card_reward_reveal_action(screen, game, remaining).mcp_arguments, {"choice_index": index})
            remaining = [c for c in remaining if c.mcp_arguments.get("choice_index") != index]
        self.assertIsNone(card_reward_reveal_action(screen, game, remaining))

    def test_strict_declined_card_returns_to_parent_potion_decision(self):
        with tempfile.TemporaryDirectory() as directory:
            screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Speed Potion", "Card"], "ready_for_command": True}
            game = {"screen_state": {"rewards": [{"reward_type": "POTION"}, {"reward_type": "CARD"}]},
                    "potions": [{"id": "Fire Potion", "can_discard": True}] * 3}
            client = FakeClient(screen, ["choose", "discard_potion"], game_state=game)
            path = ooc_inspector_file(directory, screen, "OK", selectedLiveAction={"kind": "discard_potion", "potionSlot": 1})
            raw = json.loads(path.read_text())
            raw["observation"]["ooc"]["screen"] = "combat_reward"
            raw["observation"]["ooc"]["rewardOccurrences"] = [{"index": 0, "type": "POTION", "identity": "p1"},
                                                               {"index": 1, "type": "CARD", "identity": "c1"}]
            path.write_text(json.dumps(raw))
            driver = Driver(client, InspectorReader(path, timeout=.01, poll_interval=.001),
                            TraceWriter(Path(directory) / "trace"), max_steps=1, strict_ooc=True)
            driver.declined_rewards.add(("s", "c1"))
            asyncio.run(driver.run())
            self.assertIn(("discard_potion", {"potion_slot": 1}), client.calls)
            self.assertFalse(any(tool == "choose" for tool, _ in client.calls))

    def test_shop_leaves(self):
        screen = {"screen_type": "SHOP_SCREEN", "ready_for_command": True}
        actions = build_legal_actions(screen, ["cancel", "proceed"])
        self.assertEqual(choose_deterministic_action(screen, actions).mcp_tool, "cancel")

    def test_shop_fallback_does_not_buy_prismatic_shard(self):
        screen = {"screen_type": "SHOP_SCREEN", "ready_for_command": True}
        actions = [
            LegalAction("choose", "Buy Prismatic Shard", "choose", {"choice_index": 1},
                        {"kind": "choose", "choice": "PRISMATIC_SHARD"}),
            LegalAction("cancel", "Leave shop", "cancel", {}, {"kind": "cancel"}),
        ]
        self.assertEqual(choose_deterministic_action(screen, actions).mcp_tool, "cancel")

    def test_state_identity_ignores_readiness(self):
        self.assertEqual(state_identity({"step": 1, "ready_for_command": True}), state_identity({"step": 1, "ready_for_command": False}))
        self.assertNotEqual(transition_identity({"screen_type": "NONE"}, {"player": {"block": 0}}),
                            transition_identity({"screen_type": "NONE"}, {"player": {"block": 5}}))

    def test_combat_pile_display_reset_preserves_intrinsic_state(self):
        from copy import deepcopy
        screen = {"screen_type": "NONE", "room_phase": "COMBAT", "ready_for_command": True}
        first = {"cost": 1, "damage": 6, "has_target": True, "id": "Strike_R",
                 "is_playable": True, "name": "Strike", "type": "ATTACK", "uuid": "strike-1"}
        moving = {**first, "uuid": "strike-2", "damage": 4, "base_damage": 6}
        piles = {"discard_pile": [first, moving], "draw_pile": [], "exhaust_pile": [],
                 "hand": [{**first, "uuid": "in-hand"}], "player": {"energy": 1, "current_hp": 81}}
        # Full MCP reads retain combat_state and its flattened pile aliases.
        before = {**deepcopy(piles), "combat_state": deepcopy(piles), "current_hp": 81}
        after = deepcopy(before)
        for container in (after, after["combat_state"]):
            container["discard_pile"][1]["damage"] = 6
            del container["discard_pile"][1]["base_damage"]
        baseline = transition_identity(screen, before)
        self.assertEqual(baseline, transition_identity(screen, after))
        self.assertEqual(before["discard_pile"][1]["damage"], 4)  # normalization is pure
        for field, value in (("damage", 9), ("cost", 0), ("uuid", "different"), ("id", "Bash")):
            changed = deepcopy(after)
            changed["discard_pile"][1][field] = value
            self.assertNotEqual(baseline, transition_identity(screen, changed), field)
        for change in ("hand", "hp", "energy", "order", "exhaust", "ambiguous_zero"):
            changed = deepcopy(before)
            if change == "hand":
                changed["hand"][0]["damage"] = 4
                changed["hand"][0]["base_damage"] = 6
            elif change == "hp": changed["current_hp"] = 80
            elif change == "energy": changed["player"]["energy"] = 0
            elif change == "order": changed["discard_pile"].reverse()
            elif change == "exhaust": changed["exhaust_pile"] = [moving]
            else: changed["discard_pile"][1]["damage"] = 0
            self.assertNotEqual(baseline, transition_identity(screen, changed), change)
        self.assertNotEqual(transition_identity({"screen_type": "MAP"}, before),
                            transition_identity({"screen_type": "MAP"}, after))

    def test_draw_discard_cached_block_and_magic_resets(self):
        for pile in ("draw_pile", "discard_pile"):
            for stat in ("block", "magic_number"):
                with self.subTest(pile=pile, stat=stat):
                    before = {pile: [{"id": "test", "uuid": "physical", stat: 4, "base_" + stat: 6}]}
                    after = {pile: [{"id": "test", "uuid": "physical", stat: 6}]}
                    self.assertEqual(transition_identity(combat_screen(), before), transition_identity(combat_screen(), after))

    def test_inspector_compares_full_live_monsters_and_ignores_dead_slots(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "latest.json"
            path.write_text(json.dumps({"session": "s", "sequence": 1, "observationHash": "h",
                                        "observation": {"boundary": "combat", "combat": {"monsters": [
                                            {"id": 7, "hp": 20}, {"id": 8, "hp": 0, "dead": True}]}},
                                        "response": {"ready": True, "session": "s", "sequence": 1,
                                                      "observationHash": "h", "advisor": {"evaluators": []}}}))
            snapshot = InspectorSnapshot.load(path)
            snapshot.validate_current({"session": "s", "sequence": 1, "observationHash": "h",
                                       "monsters": [{"id": 7, "curHp": 20}],
                                       "screen_monsters": [{"name": "Cultist", "current_hp": 20}]})

    def test_transient_ready_state_waits_for_advance(self):
        with tempfile.TemporaryDirectory() as directory:
            states = [
                {"screen_type": "CARD_REWARD", "choice_list": ["Bash"], "ready_for_command": True},
                {"screen_type": "CARD_REWARD", "choice_list": ["Bash"], "ready_for_command": False},
                {"screen_type": "CARD_REWARD", "choice_list": ["Bash", "Gold"], "ready_for_command": True},
            ]
            client = FakeClient([states[0], *states], ["choose"])
            driver = Driver(client, InspectorReader(ooc_inspector_file(directory, states[0])), TraceWriter(Path(directory) / "trace"), poll_timeout=.2, poll_interval=.001)
            self.assertTrue(asyncio.run(driver.step(0)))
            self.assertEqual(client.calls[-1][0], "get_available_commands")

    def test_debug_spawn_intent_waits_before_inspector_and_action(self):
        with tempfile.TemporaryDirectory() as directory:
            debug = combat_screen(session="s", sequence=1, observationHash="h", monsters=[
                {"id": "JawWorm", "name": "Jaw Worm", "current_hp": 41, "intent": "DEBUG", "is_gone": False}])
            ready = {**debug, "monsters": [{**debug["monsters"][0], "intent": "ATTACK", "move": {"damage": 11}}]}
            client = FakeClient([debug, ready], ["play_card"])
            reader = InspectorReader(inspector_file(directory), timeout=.01)
            original = reader.read_for
            reads = []
            async def verified_read(state, previous=None):
                reads.append(state)
                self.assertEqual(state["monsters"][0]["intent"], "ATTACK")
                self.assertFalse(any(tool == "play_card" for tool, _ in client.calls))
                return await original(state, previous)
            reader.read_for = verified_read
            driver = Driver(client, reader, TraceWriter(Path(directory) / "trace"),
                            max_steps=1, poll_timeout=.05, poll_interval=.001)
            asyncio.run(driver.run())
            self.assertEqual(len(reads), 1)
            self.assertEqual(sum(tool == "play_card" for tool, _ in client.calls), 1)
            self.assertEqual([tool for tool, _ in client.calls][:2], ["get_screen_state", "get_screen_state"])

    def test_only_active_debug_intents_delay_readiness(self):
        for intent, monster_fields in (("NONE", {}), ("UNKNOWN", {}), ("DEBUG", {"is_gone": True}),
                                       ("DEBUG", {"current_hp": 0}), ("DEBUG", {"half_dead": True})):
            with self.subTest(intent=intent, fields=monster_fields), tempfile.TemporaryDirectory() as directory:
                screen = combat_screen(monsters=[{"current_hp": 41, "intent": intent, **monster_fields}])
                client = FakeClient(screen, ["end_turn"])
                driver = Driver(client, InspectorReader(Path(directory) / "missing"),
                                TraceWriter(Path(directory) / "trace"), poll_timeout=.01, poll_interval=.001)
                actual, _ = asyncio.run(driver.read_ready_state())
                self.assertEqual(actual, screen)
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(combat_screen(monsters=[{"current_hp": 41, "intent": "DEBUG"}]), ["end_turn"])
            driver = Driver(client, InspectorReader(Path(directory) / "missing"),
                            TraceWriter(Path(directory) / "trace"), poll_timeout=.005, poll_interval=.001)
            with self.assertRaises(DriverError):
                asyncio.run(driver.run())
            self.assertFalse(any(tool == "end_turn" for tool, _ in client.calls))

    def test_full_game_debug_intent_also_waits_before_returning_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            screen = combat_screen(monsters=[{"current_hp": 41, "intent": "ATTACK"}])
            client = FakeClient(screen, ["end_turn"], game_state={})
            original = client.call
            reads = []
            async def call(tool, arguments=None):
                if tool == "get_game_state":
                    reads.append(tool)
                    return {"monsters": [{"current_hp": 41, "intent": "DEBUG" if len(reads) == 1 else "ATTACK"}]}
                return await original(tool, arguments)
            client.call = call
            driver = Driver(client, InspectorReader(Path(directory) / "missing"),
                            TraceWriter(Path(directory) / "trace"), poll_timeout=.05, poll_interval=.001)
            _, _, game = asyncio.run(driver.read_ready_snapshot())
            self.assertEqual(game["monsters"][0]["intent"], "ATTACK")
            self.assertEqual(len(reads), 2)
            self.assertFalse(any(tool == "end_turn" for tool, _ in client.calls))

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
            driver = Driver(client, InspectorReader(ooc_inspector_file(directory, client.states[0])), TraceWriter(path), dry_run=True)
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


class OocDriverTest(unittest.TestCase):
    def test_empty_rewards_sole_action_has_no_search_samples(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": [], "can_proceed": True,
                  "room_phase": "COMPLETE", "ready_for_command": True}
        for defect in (None, "marker", "multiple", "visits", "budget", "distribution", "action", "semantics", "share"):
            with self.subTest(defect=defect), tempfile.TemporaryDirectory() as directory:
                action = {"kind": "proceed"}
                candidate = {"semanticKey": "sole:proceed", "q": 0, "visits": 0,
                             "visitShare": 0, "prior": 1, "liveAction": action}
                path = ooc_inspector_file(directory, screen, "OK", selectedSemanticKey="sole:proceed",
                    selectedLiveAction=action, candidateSummaries=[candidate], mode="native_pass_through",
                    valueSemantics="forced_no_search", model={"selection": "sole_legal_action", "simulations": 0,
                                                               "configuredSimulations": 512})
                raw = json.loads(path.read_text())
                raw["observation"]["ooc"]["screen"] = "combat_reward"
                evaluator = raw["response"]["advisor"]["evaluators"][0]
                if defect == "marker": evaluator["model"].pop("selection")
                elif defect == "multiple": evaluator["candidateSummaries"].append({**candidate, "semanticKey": "other"})
                elif defect == "visits": evaluator["candidateSummaries"][0]["visits"] = 1
                elif defect == "budget": evaluator["model"]["simulations"] = 512
                elif defect == "distribution": evaluator["valueDistribution"] = {"count": 0}
                elif defect == "action": evaluator["selectedLiveAction"] = {"kind": "skip"}
                elif defect == "semantics": evaluator["valueSemantics"] = "mean_backed_up_value_0_1"
                elif defect == "share": evaluator["candidateSummaries"][0]["visitShare"] = 1
                path.write_text(json.dumps(raw))
                if defect is not None:
                    with self.assertRaises(DriverError): InspectorSnapshot.load(path).ooc_evaluator("mcts_ctm")
                    continue
                client = FakeClient(screen, ["proceed"])
                driver = Driver(client, InspectorReader(path, timeout=.01, poll_interval=.001),
                                TraceWriter(Path(directory) / "trace"), max_steps=1)
                driver.strict_ooc = True
                asyncio.run(driver.run())
                self.assertEqual([call for call in client.calls if call[0] == "proceed"], [("proceed", {})])
                self.assertEqual(driver.counters["deterministic_fallback_ooc"], 0)

    def test_startup_waits_for_menu_without_fixed_delay_or_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            menu = {"screen_type": "MAIN_MENU", "in_game": False, "ready_for_command": False}
            client = FakeClient([menu, {**menu, "ready_for_command": True}], ["continue_game"])
            driver = Driver(client, InspectorReader(Path(directory) / "missing"),
                            TraceWriter(Path(directory) / "trace"), poll_timeout=.0001,
                            poll_interval=.001, startup_timeout=.1)
            screen, commands = asyncio.run(driver.read_ready_state())
            self.assertTrue(screen["ready_for_command"])
            self.assertEqual(sum(tool == "get_screen_state" for tool, _ in client.calls), 2)
            self.assertFalse(any(tool == "continue_game" for tool, _ in client.calls))

    def screen(self):
        return {"screen_type": "CARD_REWARD", "choice_list": ["Bash", "Bash"], "ready_for_command": True}

    def make(self, directory, status="OK", **fields):
        client = FakeClient(self.screen(), ["choose", "skip"])
        path = ooc_inspector_file(directory, self.screen(), status, **fields)
        driver = Driver(client, InspectorReader(path, timeout=.01, poll_interval=.001),
                        TraceWriter(Path(directory) / "trace"), max_steps=1)
        return driver, client, path

    def test_ok_exact_duplicate_occurrence_never_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, client, _ = self.make(directory, selectedLiveAction={"kind": "choose", "choiceIndex": 2})
            asyncio.run(driver.run())
            self.assertEqual([call for call in client.calls if call[0] == "choose"], [("choose", {"choice_index": 2})])
            summary = driver.summary()
            self.assertEqual(summary["outcome"], "max_steps")
            self.assertEqual(summary["counters"]["ooc_v4_ok"], 1)
            self.assertEqual(summary["counters"]["deterministic_fallback_ooc"], 0)
            self.assertEqual(summary["latency"]["ooc_v4_micros"]["p95"], 12)
            self.assertEqual(summary["latency"]["ooc_scorer_micros"]["p95"], 5)
            self.assertEqual(summary["latency"]["driver_step_micros"]["count"], 1)

    def test_explicit_unsupported_fallback_and_reason_count(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, client, _ = self.make(directory, "UNSUPPORTED")
            asyncio.run(driver.run())
            self.assertEqual(driver.counters["ooc_v4_unsupported"], 1)
            self.assertEqual(driver.counters["deterministic_fallback_ooc"], 1)
            self.assertEqual(driver.unsupported["ooc_v4:fixture"], 1)
            self.assertEqual(driver.summary()["latency"]["ooc_v4_micros"]["count"], 0)
            self.assertEqual(driver.summary()["latency"]["ooc_scorer_micros"]["count"], 0)
            decision = json.loads(driver.trace.path.read_text().splitlines()[0])
            self.assertEqual(decision["ooc_v4_latency_micros"], 12)
            self.assertEqual(decision["ooc_scorer_latency_micros"], 5)

    def test_card_reward_fallback_preserves_hidden_card_open(self):
        with tempfile.TemporaryDirectory() as directory:
            screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["card"],
                      "ready_for_command": True}
            path = ooc_inspector_file(directory, screen, "UNSUPPORTED")
            raw = json.loads(path.read_text())
            raw["observation"]["ooc"]["screen"] = "combat_reward"
            raw["observation"]["ooc"]["rewardOccurrences"] = [
                {"index": 0, "type": "CARD", "identity": "card-1"}]
            raw["observation"]["ooc"]["liveChoices"] = [
                {"liveAction": {"kind": "proceed"},
                 "nativeAction": {"kind": "skip", "index": 0, "group": 0}}]
            path.write_text(json.dumps(raw))
            snapshot = InspectorSnapshot.load(path)
            driver = Driver(FakeClient(screen, ["choose", "proceed"]), InspectorReader(path),
                            TraceWriter(Path(directory) / "trace"))
            action, _ = driver.fallback_action(
                screen, {}, build_legal_actions(screen, ["choose", "proceed"]), snapshot)
            self.assertEqual(action.mcp_arguments, {"choice_index": 1})

    def test_full_potion_fallback_filters_only_potion_and_preserves_card(self):
        with tempfile.TemporaryDirectory() as directory:
            screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["add potion", "card"],
                      "ready_for_command": True}
            path = ooc_inspector_file(directory, screen, "UNSUPPORTED")
            raw = json.loads(path.read_text())
            ooc = raw["observation"]["ooc"]
            ooc["screen"] = "combat_reward"
            ooc["publicState"] = {"potionCapacity": 3,
                                   "potions": ["LiquidMemories", "ColorlessPotion", "StrengthPotion"]}
            ooc["rewardOccurrences"] = [
                {"index": 0, "type": "POTION", "identity": "potion-1"},
                {"index": 1, "type": "CARD", "identity": "card-1"}]
            ooc["liveChoices"] = [
                {"liveAction": {"kind": "proceed"},
                 "nativeAction": {"kind": "skip", "index": 0, "group": 0}}]
            path.write_text(json.dumps(raw))
            snapshot = InspectorSnapshot.load(path)
            driver = Driver(FakeClient(screen, ["choose", "proceed"]), InspectorReader(path),
                            TraceWriter(Path(directory) / "trace"))
            actions = build_legal_actions(screen, ["choose", "proceed"])
            action, _ = driver.fallback_action(screen, {}, actions, snapshot)
            self.assertEqual(action.mcp_arguments, {"choice_index": 2})

    def test_mixed_reward_unsupported_fallback_collects_gold_before_card(self):
        with tempfile.TemporaryDirectory() as directory:
            screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Gold", "Anchor", "Card"],
                      "ready_for_command": True}
            client = FakeClient(screen, ["choose"], game_state={"screen_state": {"rewards": [
                {"reward_type": "GOLD"}, {"reward_type": "RELIC"}, {"reward_type": "CARD"}]}})
            path = ooc_inspector_file(directory, screen, "UNSUPPORTED")
            raw = json.loads(path.read_text())
            ooc = raw["observation"]["ooc"]
            ooc["screen"] = "combat_reward"
            ooc["rewardOccurrences"] = [
                {"index": 0, "type": "GOLD", "identity": "gold-1"},
                {"index": 1, "type": "RELIC", "identity": "relic-1"},
                {"index": 2, "type": "CARD", "identity": "card-1"}]
            path.write_text(json.dumps(raw))
            driver = Driver(client, InspectorReader(path, timeout=.01, poll_interval=.001),
                            TraceWriter(Path(directory) / "trace"), max_steps=1)
            asyncio.run(driver.run())
            self.assertEqual([call for call in client.calls if call[0] == "choose"],
                             [("choose", {"choice_index": 1})])

    def test_mixed_key_reward_does_not_precede_card_reveal(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Gold", "Emerald Key", "Card"],
                  "ready_for_command": True}
        game = {"screen_state": {"rewards": [
            {"reward_type": "GOLD"}, {"reward_type": "EMERALD_KEY"}, {"reward_type": "CARD"}]}}
        candidates = build_legal_actions(screen, ["choose"])
        self.assertIsNone(card_reward_reveal_action(screen, game, candidates))
        self.assertEqual(card_reward_reveal_action(screen, game, candidates[1:]).mcp_arguments,
                         {"choice_index": 3})

    def test_stolen_gold_reward_precedes_card_reveal(self):
        screen = {"screen_type": "COMBAT_REWARD", "choice_list": ["Stolen Gold", "Card"],
                  "ready_for_command": True}
        game = {"screen_state": {"rewards": [
            {"reward_type": "STOLEN_GOLD"}, {"reward_type": "CARD"}]}}
        candidates = build_legal_actions(screen, ["choose"])
        self.assertIsNone(card_reward_reveal_action(screen, game, candidates))
        self.assertEqual(card_reward_reveal_action(screen, game, candidates[1:]).mcp_arguments,
                         {"choice_index": 2})

    def test_strict_unsupported_failure_packet_no_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, client, _ = self.make(directory, "UNSUPPORTED")
            driver.strict_ooc = True
            with self.assertRaises(DriverError):
                asyncio.run(driver.run())
            self.assertFalse(any(tool in {"choose", "skip"} for tool, _ in client.calls))
            packet = json.loads(driver.failure_path.read_text())
            self.assertEqual(packet["schemaVersion"], 1)
            self.assertEqual(packet["inspector"]["sequence"], 1)
            self.assertEqual(packet["decision"]["ooc_evaluator"]["status"], "UNSUPPORTED")
            self.assertEqual(packet["summary"]["steps"], 0)
            self.assertFalse(list(Path(directory).glob("*.tmp-*")))

    def test_stale_malformed_missing_policy_errors_never_mutate(self):
        for corruption in ("stale_choices", "stale_sequence", "policy", "missing", "nonfinite", "wrong_boundary"):
            with self.subTest(corruption=corruption), tempfile.TemporaryDirectory() as directory:
                driver, client, path = self.make(directory)
                raw = json.loads(path.read_text())
                evaluator = raw["response"]["advisor"]["evaluators"][0]
                if corruption == "stale_choices":
                    raw["observation"]["ooc"]["mcpState"]["choice_list"] = ["Other"]
                elif corruption == "stale_sequence":
                    driver.previous_inspector = ("s", 1)
                elif corruption == "policy":
                    evaluator["policy"] = "other"
                elif corruption == "missing":
                    evaluator.pop("selectedLiveAction")
                elif corruption == "nonfinite":
                    evaluator["candidateSummaries"][0]["q"] = float("nan")
                else:
                    raw["observation"]["boundary"] = "combat"
                path.write_text(json.dumps(raw))
                with self.assertRaises(DriverError):
                    asyncio.run(driver.run())
                self.assertFalse(any(tool in {"choose", "skip"} for tool, _ in client.calls))
                packet = json.loads(driver.failure_path.read_text())
                self.assertEqual(packet["summary"]["outcome"], "error")
                self.assertIsNotNone(packet["inspector_snapshot"])

    def test_in_combat_card_reward_consumes_silver_boundary(self):
        with tempfile.TemporaryDirectory() as directory:
            screen = {**self.screen(), "room_phase": "COMBAT",
                      "session": "s", "sequence": 1, "observationHash": "h"}
            self.assertTrue(_is_combat(screen))
            for kind in ("NONE", "GRID", "HAND_SELECT"):
                self.assertTrue(_is_combat({**screen, "screen_type": kind}))
            client = FakeClient(screen, ["choose"])
            path = inspector_file(directory, "UNSUPPORTED", reason="silver_unmapped_selection_task")
            driver = Driver(client, InspectorReader(path), TraceWriter(Path(directory) / "trace"), max_steps=1)
            asyncio.run(driver.run())
            self.assertEqual(driver.counters["silver_unsupported"], 1)
            self.assertEqual(driver.counters["ooc_v4_unsupported"], 0)
            self.assertEqual([(t, a) for t, a in client.calls if t == "choose"],
                             [("choose", {"choice_index": 1})])

    def test_top_level_advisor_error_reports_root_cause_without_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, client, path = self.make(directory)
            raw = json.loads(path.read_text())
            raw["response"]["advisor"] = {"kind": "error", "status": "ERROR", "code": "UNSUPPORTED",
                                          "message": "encounter identity is not canonical"}
            path.write_text(json.dumps(raw))
            with self.assertRaisesRegex(DriverError, "advisor error UNSUPPORTED: encounter identity"):
                asyncio.run(driver.run())
            with self.assertRaisesRegex(DriverError, "advisor error UNSUPPORTED: encounter identity"):
                InspectorSnapshot.load(path).silver_evaluator()
            self.assertFalse(any(tool in {"choose", "skip"} for tool, _ in client.calls))
            self.assertEqual(driver.counters["deterministic_fallback_ooc"], 0)
            self.assertIn("encounter identity", json.loads(driver.failure_path.read_text())["reason"])

    def test_zero_multiple_or_malformed_mapping_stops(self):
        candidates = build_legal_actions(self.screen(), ["choose", "skip"])
        for selected, actions in [({"kind": "choose", "choiceIndex": 3}, candidates),
                                  ({"kind": "choose", "choiceIndex": 1}, candidates + candidates),
                                  ({"kind": "choose", "choiceIndex": True}, candidates),
                                  ({"kind": "skip", "ignored": 1}, candidates),
                                  ({"kind": "choose", "label": "Bash"}, candidates)]:
            with self.subTest(selected=selected), self.assertRaises(IntegrationFailure):
                map_ooc_action(selected, actions)

    def test_mapping_failure_record_has_candidates_and_no_call(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, client, _ = self.make(directory, selectedLiveAction={"kind": "choose", "choiceIndex": 5})
            with self.assertRaises(IntegrationFailure):
                asyncio.run(driver.run())
            packet = json.loads(driver.failure_path.read_text())
            self.assertEqual(packet["decision"]["mapping_match_count"], 0)
            self.assertEqual(packet["summary"]["counters"]["mapping_failures"], 1)
            self.assertFalse(any(tool == "choose" for tool, _ in client.calls))

    def test_map_coordinates_resolve_exact_visible_candidate(self):
        screen = {"screen_type": "MAP", "choice_list": [{"x": 1, "y": 2}, {"x": 3, "y": 2}]}
        actions = build_legal_actions(screen, ["choose"])
        self.assertEqual(map_ooc_action({"kind": "map", "x": 3, "y": 2}, actions).mcp_arguments, {"choice_index": 2})
        with self.assertRaises(IntegrationFailure):
            map_ooc_action({"kind": "map", "x": 9, "y": 2}, actions)

    def test_single_screen_compound_and_controls(self):
        for kind in ("skip", "proceed", "cancel", "confirm"):
            candidate = map_ooc_action({"kind": kind}, build_legal_actions({}, [kind]))
            self.assertEqual(candidate.mcp_tool, kind)
            self.assertEqual(candidate.mcp_arguments, {})
        with tempfile.TemporaryDirectory() as directory:
            driver, client, _ = self.make(directory)
            driver.max_steps = 1
            asyncio.run(driver.run())
            self.assertEqual(len([tool for tool, _ in client.calls if tool in {"choose", "skip"}]), 1)

    def test_summary_uses_actual_top_level_mcp_hp_shape(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, _, _ = self.make(directory)
            driver.last_screen = {"screen_type": "MAP", "current_hp": 81,
                                  "max_hp": 81, "floor": 1, "gold": 99}
            driver.last_game = {"act": 1}
            summary = driver.summary()
            self.assertEqual(summary["hp"], 81)
            self.assertEqual(summary["floor"], 1)
            self.assertEqual(summary["act"], 1)
            driver.last_screen = {"current_health": 42}
            self.assertEqual(driver.summary()["hp"], 42)

    def test_terminal_and_zero_limit_exit_cleanly_without_advisor(self):
        for terminal in ("DEATH", "VICTORY", "RUN_COMPLETE"):
            with self.subTest(terminal=terminal), tempfile.TemporaryDirectory() as directory:
                client = FakeClient({"screen_type": terminal, "ready_for_command": False}, [])
                trace = TraceWriter(Path(directory) / "trace")
                driver = Driver(client, InspectorReader(Path(directory) / "missing"), trace)
                asyncio.run(driver.run())
                self.assertEqual(driver.steps, 0)
                self.assertNotEqual(driver.outcome, "error")
                self.assertIsNone(driver.failure_path)
                self.assertEqual(json.loads(trace.path.read_text())["record_type"], "summary")
        with tempfile.TemporaryDirectory() as directory:
            driver, client, _ = self.make(directory)
            driver.max_steps = 0
            asyncio.run(driver.run())
            self.assertEqual(driver.outcome, "max_steps")
            self.assertFalse(client.calls)

    def test_actual_game_over_boolean_distinguishes_death_and_victory(self):
        for victory in (False, True):
            with self.subTest(victory=victory), tempfile.TemporaryDirectory() as directory:
                screen = {"screen_type": "GAME_OVER", "screen_state": {"victory": victory, "score": 116},
                          "screen_name": "VICTORY" if victory else "DEATH", "ready_for_command": True}
                client = FakeClient(screen, ["proceed"])
                driver = Driver(client, InspectorReader(Path(directory) / "missing"),
                                TraceWriter(Path(directory) / "trace"))
                asyncio.run(driver.run())
                self.assertEqual(driver.outcome, "victory" if victory else "death")
                self.assertFalse(any(tool == "proceed" for tool, _ in client.calls))
                self.assertIsNone(driver.failure_path)

    def test_save_controls_never_destroy_existing_run(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, _, _ = self.make(directory)
            menu = {"screen_type": "MAIN_MENU"}
            commands = {"available_tools": ["start_game", "continue_game"]}
            self.assertEqual(driver.menu_action(menu, commands).mcp_tool, "continue_game")
            driver.new_run = True
            with self.assertRaises(DriverError):
                driver.menu_action(menu, commands)
            with self.assertRaises(DriverError):
                driver.menu_action(self.screen(), {"available_tools": ["choose"]})
            driver.character, driver.ascension, driver.seed = "IRONCLAD", 7, "abc"
            self.assertEqual(driver.menu_action(menu, {"available_tools": ["start_game"]}).mcp_arguments,
                             {"character": "IRONCLAD", "ascension": 7, "seed": "abc"})
            driver.new_run, driver.character = False, None
            with self.assertRaises(DriverError):
                driver.menu_action(menu, {"available_tools": ["start_game"]})

    def test_state_change_during_advisor_wait_stops_before_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, client, _ = self.make(directory)
            client.states = [self.screen(), {**self.screen(), "choice_list": ["Other"]}]
            with self.assertRaisesRegex(DriverError, "changed while awaiting"):
                asyncio.run(driver.run())
            self.assertFalse(any(tool in {"choose", "skip"} for tool, _ in client.calls))
            self.assertIsNotNone(driver.failure_path)

    def test_cached_pile_stat_appearance_restarts_decision_before_clicking(self):
        for drift in ("display", "hp", "hand", "cost", "uuid", "zero", "positive_change", "oscillating"):
            with self.subTest(drift=drift), tempfile.TemporaryDirectory() as directory:
                from copy import deepcopy
                screen = combat_screen(session="s", sequence=1, observationHash="h")
                before = {"current_hp": 80, "discard_pile": [
                    {"id": "Anger", "uuid": "anger-copy", "cost": 0}]}
                after = deepcopy(before)
                after["discard_pile"][0]["damage"] = 6
                if drift == "hp": after["current_hp"] = 79
                if drift == "hand": after["hand"] = [{"uuid": "another-card"}]
                if drift in {"cost", "uuid"}: after["discard_pile"][0][drift] = "changed"
                if drift == "zero": after["discard_pile"][0]["damage"] = 0
                if drift == "positive_change":
                    before["discard_pile"][0]["damage"] = 6
                    after["discard_pile"][0]["damage"] = 9
                client = FakeClient(screen, ["play_card"], game_state=before)
                original = client.call
                reads = []
                async def call(tool, arguments=None):
                    if tool == "get_game_state":
                        reads.append(tool)
                        if drift == "oscillating":
                            return deepcopy(before if len(reads) % 2 else after)
                        return deepcopy(before if len(reads) == 1 else after)
                    return await original(tool, arguments)
                client.call = call
                reader = InspectorReader(inspector_file(directory, "OK", selectedLiveAction={
                    "kind": "card", "cardUuid": "strike-1", "targetIndex": 1}), timeout=.02)
                original_read = reader.read_for
                advisor_reads = []
                async def read_for(state, previous=None):
                    advisor_reads.append(state)
                    self.assertFalse(any(tool == "play_card" for tool, _ in client.calls))
                    return await original_read(state, previous)
                reader.read_for = read_for
                trace = TraceWriter(Path(directory) / "trace")
                driver = Driver(client, reader, trace, strict_silver=True, max_steps=1,
                                poll_interval=.001, poll_timeout=.05)
                if drift == "display":
                    asyncio.run(driver.run())
                    self.assertEqual(len(advisor_reads), 2)
                    self.assertEqual(sum(tool == "play_card" for tool, _ in client.calls), 1)
                    rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
                    self.assertEqual(rows[0]["decision_source"], "combat_display_refresh")
                    self.assertNotIn("executed_mcp_tool", rows[0])
                    self.assertEqual(driver.counters["silver_ok"], 1)
                else:
                    with self.assertRaisesRegex(DriverError, "changed while awaiting"):
                        asyncio.run(driver.run())
                    self.assertFalse(any(tool == "play_card" for tool, _ in client.calls))
                    self.assertEqual(len(advisor_reads), 4 if drift == "oscillating" else 1)

    def test_missing_ooc_snapshot_cannot_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, client, path = self.make(directory)
            path.unlink()
            with self.assertRaises(DriverError):
                asyncio.run(driver.run())
            self.assertEqual(driver.counters["deterministic_fallback_ooc"], 0)
            self.assertFalse(any(tool in {"choose", "skip"} for tool, _ in client.calls))

    def test_dry_run_idle_menu_inspects_without_selecting_or_starting(self):
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient({"screen_type": "MAIN_MENU", "ready_for_command": True}, ["start_game"])
            trace = TraceWriter(Path(directory) / "trace")
            driver = Driver(client, InspectorReader(Path(directory) / "missing"), trace,
                            dry_run=True, max_steps=1)
            asyncio.run(driver.run())
            rows = [json.loads(line) for line in trace.path.read_text().splitlines()]
            self.assertEqual(rows[0]["decision_source"], "menu_inspection")
            self.assertEqual(rows[0]["screen"]["screen_type"], "MAIN_MENU")
            self.assertEqual(rows[0]["available_commands"]["available_tools"], [{"tool": "start_game"}])
            self.assertNotIn("executed_mcp_tool", rows[0])
            self.assertNotIn("selected_candidate", rows[0])
            self.assertEqual(rows[-1]["outcome"], "dry_run")
            self.assertEqual(driver.steps, 0)
            self.assertFalse(any(tool == "start_game" for tool, _ in client.calls))
            # The probe exception must not authorize an actual implicit start.
            driver.dry_run = False
            with self.assertRaisesRegex(DriverError, "starting requires"):
                asyncio.run(driver.step(0))
            self.assertFalse(any(tool == "start_game" for tool, _ in client.calls))

    def test_start_and_continue_each_execute_only_one_mcp_command(self):
        for command in ("start_game", "continue_game"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                client = FakeClient({"screen_type": "MAIN_MENU", "ready_for_command": True}, [command])
                driver = Driver(client, InspectorReader(Path(directory) / "missing"),
                                TraceWriter(Path(directory) / "trace"), max_steps=1,
                                new_run=command == "start_game", ascension=3, seed="123")
                asyncio.run(driver.run())
                mutations = [(tool, args) for tool, args in client.calls if tool == command]
                self.assertEqual(len(mutations), 1)
                if command == "start_game":
                    self.assertEqual(mutations[0][1], {"character": "IRONCLAD", "ascension": 3, "seed": "123"})
                self.assertEqual(driver.summary()["outcome"], "max_steps")

    def test_differential_run_control_needs_no_native_decision(self):
        for command in ("start_game", "continue_game"):
            with self.subTest(command=command), tempfile.TemporaryDirectory() as directory:
                client = FakeClient({"screen_type": "MAIN_MENU", "ready_for_command": True}, [command])
                driver = Driver(client, InspectorReader(Path(directory) / "missing"),
                                TraceWriter(Path(directory) / "trace"), max_steps=1, differential_trace=True,
                                new_run=command == "start_game", ascension=3, seed="123")
                asyncio.run(driver.run())
                mutations = [(tool, args) for tool, args in client.calls if tool == command]
                self.assertEqual(len(mutations), 1)
                if command == "start_game":
                    self.assertEqual(mutations[0][1], {"character": "IRONCLAD", "ascension": 3, "seed": "123"})
                self.assertEqual(driver.summary()["outcome"], "max_steps")

    def test_strict_completed_act_three_boss_proceeds_without_policy(self):
        screen = {"screen_type": "COMPLETE", "screen_name": "NONE", "room_type": "MonsterRoomBoss",
                  "room_phase": "COMPLETE", "ready_for_command": True, "in_game": True,
                  "is_screen_up": False, "can_cancel": False, "can_proceed": True,
                  "current_hp": 33, "max_hp": 68, "floor": 50}
        victory = {"screen_type": "GAME_OVER", "screen_state": {"victory": True},
                   "ready_for_command": True, "current_hp": 33}
        class CompletionClient(FakeClient):
            async def call(self, tool, arguments=None):
                if tool == "proceed":
                    self.calls.append((tool, arguments or {})); self.states = [victory]
                    return {"success": True}
                return await super().call(tool, arguments)
        with tempfile.TemporaryDirectory() as directory:
            client = CompletionClient(screen, ["proceed"], game_state={"act": 3, "floor": 50, "current_hp": 33})
            reader = InspectorReader(Path(directory) / "absent")
            async def no_policy(*args, **kwargs):
                raise AssertionError("completed boss navigation asked a policy")
            reader.read_for = no_policy
            trace = TraceWriter(Path(directory) / "trace")
            driver = Driver(client, reader, trace, strict_silver=True, strict_ooc=True, max_steps=2)
            asyncio.run(driver.run())
            self.assertEqual(driver.outcome, "victory")
            self.assertEqual([tool for tool, _ in client.calls if tool == "proceed"], ["proceed"])
            self.assertEqual(list(trace.recent)[0]["decision_source"], "boss_completion")
            self.assertEqual(driver.counters["deterministic_fallback_ooc"], 0)

    def test_boss_completion_navigation_rejects_other_surfaces(self):
        screen = {"screen_type": "COMPLETE", "screen_name": "NONE", "room_type": "MonsterRoomBoss",
                  "room_phase": "COMPLETE", "ready_for_command": True, "in_game": True,
                  "is_screen_up": False, "can_cancel": False, "can_proceed": True,
                  "current_hp": 33, "floor": 50}
        game = {"act": 3, "floor": 50, "current_hp": 33}
        candidates = build_legal_actions(screen, ["proceed"], game)
        self.assertIsNotNone(boss_completion_proceed_action(screen, game, candidates))
        for ascension in (None, 0, 19, 20):
            second_boss = boss_completion_proceed_action({**screen, "floor": 51},
                    {**game, "floor": 51, "ascension_level": ascension}, candidates)
            self.assertEqual(second_boss is not None, ascension == 20)
        for key, value in [("screen_type", "NONE"), ("room_type", "MonsterRoom"),
                           ("room_phase", "COMBAT"), ("ready_for_command", False),
                           ("can_cancel", True), ("can_proceed", False), ("is_screen_up", True),
                           ("choice_list", ["reward"]), ("choice_list", None), ("floor", 49)]:
            with self.subTest(key=key, value=value):
                self.assertIsNone(boss_completion_proceed_action({**screen, key: value}, game, candidates))
        for update in ({"act": 2}, {"act": 4}, {"current_hp": 0}, {"current_hp": 34}, {"floor": 51}):
            self.assertIsNone(boss_completion_proceed_action(screen, {**game, **update}, candidates))
        self.assertIsNone(boss_completion_proceed_action(screen, game, candidates + candidates))

    def test_differential_boss_completion_keeps_native_boundary(self):
        screen = {"screen_type": "COMPLETE", "screen_name": "NONE", "room_type": "MonsterRoomBoss",
                  "room_phase": "COMPLETE", "ready_for_command": True, "in_game": True,
                  "is_screen_up": False, "can_cancel": False, "can_proceed": True,
                  "current_hp": 33, "floor": 50}
        with tempfile.TemporaryDirectory() as directory:
            client = FakeClient(screen, ["proceed"], game_state={"act": 3, "floor": 50})
            reader = InspectorReader(Path(directory) / "absent")
            async def native_boundary(*args, **kwargs):
                raise DriverError("native completion boundary")
            reader.read_for = native_boundary
            driver = Driver(client, reader, TraceWriter(Path(directory) / "trace"), differential_trace=True)
            with self.assertRaisesRegex(DriverError, "native completion boundary"):
                asyncio.run(driver.run())
            self.assertFalse(any(tool == "proceed" for tool, _ in client.calls))

    def test_victory_dialogue_requires_exact_public_story_surface(self):
        screen = {"screen_type": "EVENT", "room_type": "VictoryRoom", "room_phase": "EVENT",
                  "ready_for_command": True, "in_game": True, "can_cancel": False, "can_proceed": False,
                  "floor": 51, "choice_list": ["[Continue]"], "screen_state": {"event_id": "Spire Heart",
                  "options": [{"choice_index": 0, "disabled": False}]}}
        game = {"act": 3, "floor": 51, "ascension_level": 0}
        candidates = build_legal_actions(screen, ["choose"], game)
        self.assertIsNotNone(victory_dialogue_action(screen, game, candidates))
        self.assertIsNotNone(victory_dialogue_action({**screen, "floor": 52},
                {**game, "floor": 52, "ascension_level": 20}, candidates))
        for key, value in [("room_type", "EventRoom"), ("can_cancel", True), ("floor", 50),
                           ("ready_for_command", False), ("choice_list", ["Continue", "Leave"])]:
            self.assertIsNone(victory_dialogue_action({**screen, key: value}, game, candidates))
        for state in ({"event_id": "MindBloom", "options": screen["screen_state"]["options"]},
                      {"event_id": "Spire Heart", "options": [{"choice_index": 1, "disabled": False}]},
                      {"event_id": "Spire Heart", "options": [{"choice_index": 0, "disabled": True}]}):
            self.assertIsNone(victory_dialogue_action({**screen, "screen_state": state}, game, candidates))

    def test_strict_victory_story_advances_without_a_policy(self):
        screen = {"screen_type": "EVENT", "room_type": "VictoryRoom", "room_phase": "EVENT",
                  "ready_for_command": True, "in_game": True, "can_cancel": False, "can_proceed": False,
                  "floor": 51, "choice_list": ["[Continue]"], "screen_state": {"event_id": "Spire Heart",
                  "options": [{"choice_index": 0, "disabled": False}]}}
        class StoryClient(FakeClient):
            async def call(self, tool, arguments=None):
                if tool == "choose":
                    self.calls.append((tool, arguments or {}))
                    self.states = [{"screen_type": "GAME_OVER", "screen_state": {"victory": True},
                                    "ready_for_command": True}]
                    return {"success": True}
                return await super().call(tool, arguments)
        with tempfile.TemporaryDirectory() as directory:
            client = StoryClient(screen, ["choose"], game_state={"act": 3, "floor": 51, "ascension_level": 0})
            reader = InspectorReader(Path(directory) / "absent")
            async def no_policy(*args, **kwargs):
                raise AssertionError("victory story asked a policy")
            reader.read_for = no_policy
            trace = TraceWriter(Path(directory) / "trace")
            driver = Driver(client, reader, trace, strict_ooc=True, strict_silver=True)
            asyncio.run(driver.run())
            self.assertEqual(driver.outcome, "victory")
            self.assertEqual(list(trace.recent)[0]["decision_source"], "victory_dialogue")
            self.assertEqual(driver.counters["deterministic_fallback_ooc"], 0)

    def test_actual_shop_room_alias_and_enter_once_then_leave(self):
        with tempfile.TemporaryDirectory() as directory:
            room = {"screen_type": "SHOP_ROOM", "screen_name": "NONE", "room_type": "ShopRoom",
                    "room_phase": "COMPLETE", "choice_list": ["shop"], "current_hp": 86,
                    "max_hp": 88, "floor": 4, "gold": 154, "ready_for_command": True,
                    "can_cancel": False, "can_proceed": True, "in_game": True}
            shop = {**room, "screen_type": "SHOP_SCREEN", "choice_list": ["offer"],
                    "can_cancel": True, "can_proceed": False}
            states = [room, shop, {**shop, "gold": 129, "choice_list": []},
                      {**room, "gold": 129}, {"screen_type": "RUN_COMPLETE"}]
            command_sets = [["choose", "proceed"], ["choose", "cancel"], ["cancel"], ["choose", "proceed"], []]
            selections = [None, {"kind": "choose", "choiceIndex": 1}, {"kind": "cancel"}, None]
            class ShopClient(FakeClient):
                def __init__(self):
                    super().__init__(room, command_sets[0], game_state={"act": 1})
                    self.index = 0
                    self.tool_names |= {"cancel"}
                async def call(self, tool, arguments=None):
                    self.calls.append((tool, arguments or {}))
                    if tool == "get_screen_state": return states[self.index]
                    if tool == "get_game_state": return {"act": 1}
                    if tool == "get_available_commands": return {"available_tools": command_sets[self.index]}
                    self.index += 1
                    return {"success": True}
            client = ShopClient()
            reader = InspectorReader(Path(directory) / "latest.json", timeout=.01)
            original = reader.read_for
            async def capture(state, previous=None):
                selected = selections[client.index]
                path = ooc_inspector_file(directory, states[client.index], "OK" if selected else "UNSUPPORTED",
                                          **({"selectedLiveAction": selected} if selected else {}))
                raw = json.loads(path.read_text())
                raw["sequence"] = raw["response"]["sequence"] = client.index + 1
                raw["observation"]["ooc"]["publicState"] = {"act": 1, "floor": 4,
                    "hp": 86, "maxHp": 88, "gold": states[client.index]["gold"]}
                path.write_text(json.dumps(raw))
                return await original(state, previous)
            reader.read_for = capture
            driver = Driver(client, reader, TraceWriter(Path(directory) / "trace"), strict_ooc=True)
            asyncio.run(driver.run())
            mutations = [(tool, arguments) for tool, arguments in client.calls if tool in {"choose", "cancel", "proceed"}]
            self.assertEqual(mutations, [("choose", {"choice_index": 1}), ("choose", {"choice_index": 1}),
                                         ("cancel", {}), ("proceed", {})])
            self.assertEqual(driver.entered_shop_rooms, {(1, 4)})
            self.assertEqual(driver.counters["ooc_v4_ok"], 2)
            self.assertEqual(driver.counters["deterministic_fallback_ooc"], 0)
            self.assertEqual(driver.counters["ooc_v4_unsupported"], 0)

    def test_shop_entry_is_not_recorded_on_dry_run_or_failed_call(self):
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as directory:
                screen = {"screen_type": "SHOP_ROOM", "floor": 4, "choice_list": ["shop"], "ready_for_command": True}
                client = FakeClient(screen, ["choose", "proceed"], game_state={"act": 1})
                original = client.call
                async def call(tool, arguments=None):
                    if tool == "choose":
                        client.calls.append((tool, arguments or {}))
                        return {"success": False, "error": "fixture"}
                    return await original(tool, arguments)
                client.call = call
                path = ooc_inspector_file(directory, screen)
                raw = json.loads(path.read_text())
                raw["observation"]["ooc"]["publicState"] = {"act": 1, "floor": 4}
                path.write_text(json.dumps(raw))
                driver = Driver(client, InspectorReader(path), TraceWriter(Path(directory) / "trace"), dry_run=dry_run)
                if dry_run:
                    asyncio.run(driver.run())
                    self.assertFalse(any(tool == "choose" for tool, _ in client.calls))
                else:
                    with self.assertRaisesRegex(DriverError, "MCP action failed"):
                        asyncio.run(driver.run())
                self.assertEqual(driver.entered_shop_rooms, set())

    def test_strict_shop_navigation_rejects_ambiguous_or_nonmerchant_choices(self):
        for choices in (["shop", "buy"], ["purchase"], []):
            with self.subTest(choices=choices), tempfile.TemporaryDirectory() as directory:
                screen = {"screen_type": "SHOP_ROOM", "floor": 4,
                          "choice_list": choices, "ready_for_command": True}
                client = FakeClient(screen, ["choose", "proceed"], game_state={"act": 1})
                driver = Driver(client, InspectorReader(Path(directory) / "absent.json"),
                                TraceWriter(Path(directory) / "trace"), strict_ooc=True)
                with self.assertRaisesRegex(IntegrationFailure, "exact single shop entry"):
                    asyncio.run(driver.run())
                self.assertFalse(any(tool in {"choose", "proceed"} for tool, _ in client.calls))
                self.assertEqual(driver.entered_shop_rooms, set())

    def test_skipped_reward_is_not_reopened_and_distinct_identical_group_survives(self):
        with tempfile.TemporaryDirectory() as directory:
            parent = {"screen_type": "COMBAT_REWARD", "choice_list": ["card", "card"], "ready_for_command": True}
            card = self.screen()
            states = [parent, card, parent, card, parent, {"screen_type": "RUN_COMPLETE"}]
            command_sets = [["choose", "proceed"], ["choose", "skip"], ["choose", "proceed"],
                            ["choose", "skip"], ["choose", "proceed"], []]
            class RewardClient(FakeClient):
                def __init__(self):
                    super().__init__(parent, ["choose", "skip", "proceed"])
                    self.index = 0
                async def call(self, tool, arguments=None):
                    self.calls.append((tool, arguments or {}))
                    if tool == "get_screen_state": return states[self.index]
                    if tool == "get_available_commands": return {"available_tools": command_sets[self.index]}
                    self.index += 1
                    return {"success": True}
            client = RewardClient()
            reader = InspectorReader(Path(directory) / "latest.json", timeout=.01)
            original = reader.read_for
            async def capture(state, previous=None):
                is_card = client.index in (1, 3)
                path = ooc_inspector_file(directory, states[client.index], "OK" if is_card else "UNSUPPORTED",
                                          selectedLiveAction={"kind": "skip"})
                raw = json.loads(path.read_text())
                raw["sequence"] = raw["response"]["sequence"] = client.index + 1
                ooc = raw["observation"]["ooc"]
                ooc["screen"] = "card_reward" if is_card else "combat_reward"
                if is_card:
                    ooc["rewardIdentity"] = "a" if client.index == 1 else "b"
                else:
                    ooc["rewardOccurrences"] = [{"index": 0, "type": "CARD", "identity": "a"},
                                                {"index": 1, "type": "CARD", "identity": "b"}]
                path.write_text(json.dumps(raw))
                return await original(state, previous)
            reader.read_for = capture
            driver = Driver(client, reader, TraceWriter(Path(directory) / "trace"))
            asyncio.run(driver.run())
            self.assertEqual([(t, a) for t, a in client.calls if t in {"choose", "skip", "proceed"}],
                             [("choose", {"choice_index": 1}), ("skip", {}),
                              ("choose", {"choice_index": 2}), ("skip", {}), ("proceed", {})])
            self.assertEqual(driver.declined_rewards, {("s", "a"), ("s", "b")})
            # Reward-list indices may shift; identity, not the old index, binds a skip.
            path = ooc_inspector_file(directory, parent)
            raw = json.loads(path.read_text())
            raw["observation"]["ooc"]["rewardOccurrences"] = [
                {"index": 0, "identity": "fresh"}, {"index": 1, "identity": "a"}]
            path.write_text(json.dumps(raw))
            action, _ = driver.fallback_action(parent, {}, build_legal_actions(parent, ["choose", "proceed"]),
                                                InspectorSnapshot.load(path))
            self.assertEqual(action.mcp_arguments, {"choice_index": 1})

    def test_skip_is_not_recorded_on_dry_run_or_failed_call(self):
        for dry_run in (True, False):
            with self.subTest(dry_run=dry_run), tempfile.TemporaryDirectory() as directory:
                driver, client, path = self.make(directory, selectedLiveAction={"kind": "skip"})
                raw = json.loads(path.read_text())
                raw["observation"]["ooc"]["rewardIdentity"] = "reward-a"
                path.write_text(json.dumps(raw))
                driver.dry_run = dry_run
                original = client.call
                async def call(tool, arguments=None):
                    if tool == "skip": return {"success": False, "error": "fixture"}
                    return await original(tool, arguments)
                client.call = call
                if dry_run: asyncio.run(driver.run())
                else:
                    with self.assertRaisesRegex(DriverError, "MCP action failed"):
                        asyncio.run(driver.run())
                self.assertFalse(driver.declined_rewards)
                self.assertFalse(driver.ooc_actions_seen)

    def test_repeated_ooc_state_action_stops_before_second_mutation(self):
        with tempfile.TemporaryDirectory() as directory:
            driver, client, path = self.make(directory)
            asyncio.run(driver.step(0))
            # A round trip returns to the original screen with a fresh observation.
            client.states = [self.screen()]
            raw = json.loads(path.read_text())
            raw["sequence"] = raw["response"]["sequence"] = 2
            path.write_text(json.dumps(raw))
            driver.max_steps = None
            with self.assertRaisesRegex(DriverError, "repeated OOC state/action cycle"):
                asyncio.run(driver.run())
            self.assertEqual(sum(tool == "choose" for tool, _ in client.calls), 1)
            packet = json.loads(driver.failure_path.read_text())
            self.assertNotIn("executed_mcp_tool", packet["decision"])
            self.assertEqual(packet["summary"]["outcome"], "error")

    def test_failure_reproduction_preserves_endpoint_policy_and_strict_flags(self):
        from contextlib import asynccontextmanager, redirect_stderr
        from unittest.mock import patch
        import io
        import shlex
        with tempfile.TemporaryDirectory() as directory:
            _, client, original = self.make(directory, "UNSUPPORTED")
            path = Path(directory) / "inspector snapshot's $(literal).json"
            original.rename(path)
            endpoint = "http://127.0.0.1:8181/mcp?mode=debug&name=two words"
            @asynccontextmanager
            async def connection(url):
                self.assertEqual(url, endpoint)
                yield client
            trace = str(Path(directory) / "failure-trace")
            with patch("tools.live_game_driver.connected_mcp", connection), redirect_stderr(io.StringIO()):
                code = main(["--mcp-url", endpoint, "--inspector", str(path), "--trace", trace,
                             "--inspector-timeout", "1.25", "--max-steps", "7", "--continue-run",
                             "--strict-ooc", "--strict-silver", "--ooc-policy", "v4_q"])
            self.assertEqual(code, 2)
            packet = json.loads(Path(trace + ".failure.json").read_text())
            command = packet["reproduction_command"]
            tokens = shlex.split(command)
            for flag, expected in (("--mcp-url", endpoint), ("--inspector", str(path)),
                                   ("--inspector-timeout", "1.25"), ("--max-steps", "7"),
                                   ("--ooc-policy", "v4_q")):
                self.assertEqual(tokens[tokens.index(flag) + 1], expected)
            for flag in ("--continue-run", "--run-until-error", "--strict-ooc", "--strict-silver"):
                self.assertIn(flag, tokens)
            self.assertNotIn("--new-run", tokens)
            self.assertIn(shlex.quote(str(path)), command)
            self.assertFalse(any(tool in {"choose", "skip"} for tool, _ in client.calls))

    def test_strict_modes_are_the_default_and_can_be_turned_off(self):
        from unittest.mock import patch
        seen = []
        def capture(coroutine):
            seen.append(coroutine.cr_frame.f_locals["args"])
            coroutine.close()
            return 0
        with patch("tools.live_game_driver.asyncio.run", capture):
            main([])
            main(["--no-strict-ooc", "--no-strict-silver"])
        self.assertEqual([(a.strict_ooc, a.strict_silver) for a in seen], [(True, True), (False, False)])

    def test_process_failure_returns_nonzero_and_packet(self):
        from contextlib import asynccontextmanager, redirect_stderr
        from unittest.mock import patch
        import io
        with tempfile.TemporaryDirectory() as directory:
            driver, client, path = self.make(directory)
            raw = json.loads(path.read_text())
            raw["observation"]["ooc"]["mcpState"]["choice_list"] = ["stale"]
            path.write_text(json.dumps(raw))
            @asynccontextmanager
            async def connection(url):
                yield client
            stderr = io.StringIO()
            trace = str(Path(directory) / "process-trace")
            with patch("tools.live_game_driver.connected_mcp", connection), redirect_stderr(stderr):
                code = main(["--inspector", str(path), "--trace", trace, "--inspector-timeout", ".001", "--max-steps", "1"])
            self.assertNotEqual(code, 0)
            self.assertTrue(Path(trace + ".failure.json").exists())
            self.assertIn("LIVE_DRIVER_ERROR type=DriverError step=0", stderr.getvalue())
            self.assertFalse(any(tool in {"choose", "skip"} for tool, _ in client.calls))


if __name__ == "__main__":
    unittest.main()
