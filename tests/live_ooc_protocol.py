"""Native projection -> advisor provider -> structured one-screen action contract."""
import copy
from concurrent.futures import ThreadPoolExecutor
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

    def run_rows(self, observations, model=True, policy=None, floor_model=True,
                 timeout=120, label="advisor request", debug_tree=False, tree_cap=None, differential=False):
        env = os.environ.copy()
        env.pop("STS_CTM_MODEL", None)
        env.pop("STS_LIVE_OOC_MODEL", None)
        env.pop("STS_OOC_DEBUG_TREE", None)
        env.pop("STS_OOC_DEBUG_TREE_NODE_CAP", None)
        env.pop("STS_DIFFERENTIAL_TRACE", None)
        if differential:
            env["STS_DIFFERENTIAL_TRACE"] = "1"
        if debug_tree:
            env["STS_OOC_DEBUG_TREE"] = "1"
        if tree_cap is not None:
            env["STS_OOC_DEBUG_TREE_NODE_CAP"] = str(tree_cap)
        if model:
            env["STS_LIVE_OOC_MODEL"] = str(self.model)
        if self.ctm:
            env["STS_CTM_MODEL"] = str(self.ctm)
        if self.win:
            env["STS_LIVE_OOC_WIN_MODEL"] = str(self.win)
        env.pop("STS_LIVE_OOC_FLOOR_MODEL", None)
        if floor_model:
            env["STS_LIVE_OOC_FLOOR_MODEL"] = "models/v_rich_trees.txt"
        if policy:
            env["STS_LIVE_OOC_POLICY"] = policy
        requests = [dict(protocol="sts_model_inspector_v1", kind="observation", session="ooc-protocol",
                         sequence=i + 1, observationHash=f"fixture-{i}", observation=observation)
                    for i, observation in enumerate(observations)]
        try:
            proc = subprocess.run([str(self.advisor)], input="".join(json.dumps(r) + "\n" for r in requests),
                                  text=True, capture_output=True, env=env, check=True,
                                  timeout=timeout)
        except subprocess.TimeoutExpired as error:
            self.fail(f"advisor timed out after {timeout}s for {label}: {error}")
        rows = [json.loads(line) for line in proc.stdout.splitlines()]
        self.assertEqual(len(rows), len(requests))
        for request, row in zip(requests, rows):
            for key in ("session", "sequence", "observationHash"):
                self.assertEqual(row[key], request[key])
        return rows

    def test_all_native_parity_fixtures(self):
        # Broad fixture coverage checks the public mapping/protocol contract.
        # Keep it on the cheap V4 path; dedicated tests below retain the small
        # set of full 512-simulation MCTS checks.
        fixtures = list(self.fixtures.values())
        with ThreadPoolExecutor(max_workers=4) as pool:
            responses = list(pool.map(
                lambda row: self.run_rows([row], policy="v4", timeout=20,
                                           label=row["fixture"])[0], fixtures))
        for fixture, response in zip(fixtures, responses):
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["id"], "live_ooc_decision_v1")
            self.assertEqual(evaluator["policy"], "v4_q")
            if fixture["fixture"].startswith("unsupported_"):
                self.assertEqual(evaluator["status"], "UNSUPPORTED")
                continue
            if evaluator["status"] == "UNSUPPORTED":
                # V4 intentionally has a narrower screen contract than the
                # MCTS adapter. Broad coverage records that the fixture is
                # classified safely; dedicated tests assert exact reasons for
                # boundaries that are part of this protocol's contract.
                continue
            self.assertEqual(evaluator["status"], "OK", response)
            self.assertIn("selectedLiveAction", evaluator)

    def test_full_belt_potion_replacement_uses_exact_slot_actions(self):
        observation = self.fixtures["full_belt_potion_reward"]
        response, = self.run_rows([observation])
        evaluator = response["evaluators"][0]
        self.assertEqual(evaluator["status"], "OK", response)
        actions = [c["liveAction"] for c in evaluator["candidateSummaries"]]
        capacity = observation["ooc"]["publicState"]["potionCapacity"]
        self.assertEqual([a["potionSlot"] for a in actions if a["kind"] == "discard_potion"],
                         list(range(1, capacity+1)))
        self.assertTrue(all(abs(c["prior"] - 1/len(actions)) < 1e-12
                            for c in evaluator["candidateSummaries"]))
        response, = self.run_rows([observation], policy="v4")
        self.assertEqual(response["evaluators"][0]["reason"], "POTION_REPLACEMENT_REQUIRES_MCTS")

    def test_selector_preview_scores_confirm_or_return_to_original_grid(self):
        observation = next(row for name,row in self.fixtures.items()
                           if name.startswith("selector_preview_") and row["ooc"]["details"]["type"] == "upgrade")
        first, = self.run_rows([observation], policy="v4")
        evaluator = first["evaluators"][0]
        self.assertEqual(evaluator["status"], "OK", first)
        self.assertIn(evaluator["selectedLiveAction"]["kind"], ("proceed", "cancel"))
        self.assertEqual(evaluator["mode"], "selector_preview_policy")
        variants=[]
        for card in observation["ooc"]["details"]["cards"]:
            variant=copy.deepcopy(observation)
            variant["ooc"]["details"]["previewDeckIndex"]=card["deckIndex"]
            variants.append(variant)
        decisions=self.run_rows(variants,policy="v4")
        self.assertEqual(sum(row["evaluators"][0].get("selectedLiveAction",{}).get("kind")=="proceed"
                             for row in decisions),1,
                         "preview did not retain one consistent preferred target")
        response, = self.run_rows([observation], policy="v4", differential=True)
        self.assertEqual(response["evaluators"][0]["reason"], "DIFFERENTIAL_SELECTOR_PREVIEW_UNREPRESENTABLE")

    def test_searing_blow_upgrades_remain_supported(self):
        response, = self.run_rows([self.fixtures["upgraded_searing_blow"]],
                                  policy="v4")
        self.assertEqual(response["evaluators"][0]["status"], "OK")
        self.assertIn("selectedLiveAction", response["evaluators"][0])

    def test_neow_dialogue_is_forced_without_model_or_reward_history(self):
        observations = []
        for phase, transition in (("0", "neow_intro"), ("1", "neow_intro"), ("99", "event_leave")):
            observation = copy.deepcopy(self.fixtures["neow"])
            ooc = observation["ooc"]
            ooc["screen"] = "event"
            ooc["publicState"]["rewardPityHistoryComplete"] = False
            ooc["event"] = dict(id="Neow", phase=phase, options=[dict(index=0, disabled=False)])
            ooc["details"].pop("neow", None)
            ooc["details"]["mechanicalTransition"] = transition
            ooc["liveChoices"] = [dict(nativeAction=dict(kind="option", index=0, group=0),
                                       liveAction=dict(kind="choose", choiceIndex=1))]
            observations.append(observation)
        for policy in ("v4", "mcts"):
            for response in self.run_rows(observations, model=False, policy=policy):
                evaluator, = response["evaluators"]
                self.assertEqual(evaluator["status"], "OK", response)
                self.assertEqual(evaluator["valueSemantics"], "forced_no_search")
                self.assertEqual(evaluator["selectedLiveAction"], dict(kind="choose", choiceIndex=1))
                self.assertEqual(len(evaluator["candidateSummaries"]), 1)
        for response in self.run_rows(observations, model=False, differential=True):
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["status"], "UNSUPPORTED")
            self.assertEqual(evaluator["reason"], "DIFFERENTIAL_MECHANICAL_EVENT_UNREPRESENTABLE")
            self.assertNotIn("selectedLiveAction", evaluator)

    def test_boss_map_and_result_confirmation_need_no_search_or_models(self):
        observations = [self.fixtures["forced_boss_map"], self.fixtures["forced_selector_confirmation"]]
        for policy in ("v4", "mcts"):
            responses = self.run_rows(observations, model=False, floor_model=False, policy=policy)
            for response, action in zip(responses, (dict(kind="choose", choiceIndex=1), dict(kind="proceed"))):
                evaluator, = response["evaluators"]
                self.assertEqual(evaluator["status"], "OK", response)
                self.assertEqual(evaluator["valueSemantics"], "forced_no_search")
                self.assertEqual(evaluator["selectedLiveAction"], action)
                self.assertEqual(len(evaluator["candidateSummaries"]), 1)
                self.assertNotIn("endpointHpDistribution", evaluator)
        for response in self.run_rows(observations, model=False, differential=True):
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["status"], "UNSUPPORTED")
            self.assertEqual(evaluator["reason"], "DIFFERENTIAL_FORCED_OOC_UNREPRESENTABLE")
            self.assertNotIn("selectedLiveAction", evaluator)

    def test_forge_and_writing_results_are_forced_without_models(self):
        observations = [self.fixtures["event_forge_leave"], self.fixtures["event_writing_leave"]]
        for policy in ("v4", "mcts"):
            for response in self.run_rows(observations, model=False, floor_model=False, policy=policy):
                evaluator, = response["evaluators"]
                self.assertEqual(evaluator["status"], "OK", response)
                self.assertEqual(evaluator["valueSemantics"], "forced_no_search")
                self.assertEqual(evaluator["selectedLiveAction"], dict(kind="choose", choiceIndex=1))
                self.assertNotIn("endpointHpDistribution", evaluator)

    def test_forced_public_continuations_reject_alternative_choices(self):
        variants = []
        for name in ("forced_boss_map", "forced_selector_confirmation"):
            original = self.fixtures[name]
            for field, value in (("can_cancel", True), ("ready_for_command", False)):
                observation = copy.deepcopy(original)
                observation["ooc"]["mcpState"][field] = value
                variants.append(observation)
            observation = copy.deepcopy(original)
            observation["ooc"]["liveChoices"].append(observation["ooc"]["liveChoices"][0])
            variants.append(observation)
        observation = copy.deepcopy(self.fixtures["forced_boss_map"])
        observation["ooc"]["publicState"]["map"]["y"] = 13
        variants.append(observation)
        observation = copy.deepcopy(self.fixtures["forced_selector_confirmation"])
        observation["ooc"]["details"]["confirmScreenUp"] = True
        variants.append(observation)
        for response in self.run_rows(variants, model=False):
            self.assertEqual(response["status"], "ERROR", response)

    def test_neow_dialogue_rejects_phase_and_mapping_mismatch(self):
        observation = copy.deepcopy(self.fixtures["neow"])
        ooc = observation["ooc"]
        ooc["screen"] = "event"
        ooc["event"] = dict(id="Neow", phase="3", options=[dict(index=0, disabled=False)])
        ooc["details"]["mechanicalTransition"] = "neow_intro"
        ooc["liveChoices"] = [dict(nativeAction=dict(kind="option", index=0, group=0),
                                   liveAction=dict(kind="choose", choiceIndex=1))]
        variants = [copy.deepcopy(observation)]
        ooc["event"]["phase"] = "1"
        for field, value in (("event", dict(id="Big Fish", phase="1", options=[dict(index=0, disabled=False)])),
                             ("liveChoices", [])):
            variant = copy.deepcopy(observation)
            variant["ooc"][field] = value
            variants.append(variant)
        for response in self.run_rows(variants, model=False):
            self.assertEqual(response["status"], "ERROR", response)

    def test_world_of_goop_result_is_forced_without_initial_gold_loss(self):
        observation = copy.deepcopy(self.fixtures["event_world_of_goop"])
        ooc = observation["ooc"]
        ooc["event"] = dict(id="World of Goop", phase="RESULT", options=[dict(index=0, disabled=False)])
        ooc["details"].pop("goldLoss", None)
        ooc["details"]["mechanicalTransition"] = "event_leave"
        ooc["liveChoices"] = [dict(nativeAction=dict(kind="option", index=0, group=0),
                                   liveAction=dict(kind="choose", choiceIndex=1))]
        response, = self.run_rows([observation], model=False)
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["valueSemantics"], "forced_no_search")
        self.assertEqual(evaluator["selectedLiveAction"], dict(kind="choose", choiceIndex=1))

    def test_vanilla_dialogue_pages_are_forced_without_models(self):
        observations = []
        for event, phase, transition in (("The Cleric", "99", "event_leave"),
                ("Designer", "INTRO", "event_continue"),
                ("Sensory Stone", "ACCEPT", "event_continue"),
                ("Match and Keep", "RULE_EXPLANATION", "event_continue"),
                ("Wheel of Change", "SPIN_READY", "event_continue")):
            observation = copy.deepcopy(self.fixtures["neow"])
            ooc = observation["ooc"]
            ooc["details"].update(event=event, eventContract="vanilla_v1", mechanicalTransition=transition)
            if phase == "SPIN_READY":
                ooc["details"].update(startSpin=True, buttonPressed=False, bounceTimer=0)
            ooc["event"] = dict(id=event, phase=phase, options=[dict(index=0, disabled=False)])
            ooc["liveChoices"] = [dict(nativeAction=dict(kind="option", index=0, group=0),
                                       liveAction=dict(kind="choose", choiceIndex=1))]
            observations.append(observation)
        for response in self.run_rows(observations, model=False):
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["status"], "OK", response)
            self.assertEqual(evaluator["valueSemantics"], "forced_no_search")
        invalid = copy.deepcopy(observations)
        for observation in invalid:
            observation["ooc"]["event"]["phase"] = "FORGED"
        for response in self.run_rows(invalid, model=False):
            self.assertEqual(response["status"], "ERROR", response)
        invalid = copy.deepcopy(observations[-1])
        invalid["ooc"]["details"]["buttonPressed"] = True
        response, = self.run_rows([invalid], model=False)
        self.assertEqual(response["status"], "ERROR", response)

    def test_boss_chest_reveal_preserves_skip_without_hidden_offers(self):
        observation = copy.deepcopy(self.fixtures["neow"])
        ooc = observation["ooc"]
        ooc["screen"] = "treasure"
        ooc["details"] = dict(chestType="BossChest", opened=False, mechanicalTransition="boss_chest_reveal")
        ooc["mcpState"] = dict(screen_type="CHEST", ready_for_command=True, can_cancel=False, can_proceed=True, choice_list=["open"])
        ooc["liveChoices"] = [dict(nativeAction=dict(kind="option", index=0, group=0), liveAction=dict(kind="choose", choiceIndex=1)),
                              dict(nativeAction=dict(kind="option", index=1, group=0), liveAction=dict(kind="proceed"))]
        response, = self.run_rows([observation], model=False)
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["valueSemantics"], "public_reveal_no_search")
        for field, value in (("opened", True), ("relics", ["Black Blood"]), ("chestType", "SmallChest")):
            invalid = copy.deepcopy(observation)
            invalid["ooc"]["details"][field] = value
            response, = self.run_rows([invalid], model=False)
            self.assertEqual(response["status"], "ERROR", response)

    def test_selector_previews_choose_confirm_or_cancel(self):
        observations = [row for name, row in self.fixtures.items() if name.startswith("selector_preview_")]
        self.assertEqual(len(observations), 4)
        missing_choices = copy.deepcopy(observations[0])
        missing_choices["ooc"]["mcpState"].pop("choice_list")
        observations.append(missing_choices)
        for observation in observations:
            policy="v4" if observation["ooc"]["details"]["type"] == "upgrade" else "mcts"
            response, = self.run_rows([observation], policy=policy)
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["status"], "OK", response)
            self.assertIn(evaluator["selectedLiveAction"], [dict(kind="proceed"), dict(kind="cancel")])

    def test_match_public_board_first_click_needs_no_model(self):
        response, = self.run_rows([self.fixtures["match_public_0"]], model=False)
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["selectedLiveAction"], dict(kind="choose", choiceIndex=1))
        response, = self.run_rows([self.fixtures["match_public_2"]], policy="v4")
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertIn(evaluator["selectedLiveAction"], [c["liveAction"] for c in self.fixtures["match_public_2"]["ooc"]["liveChoices"]])

    def test_event_fights_require_public_pity_for_direct_policy(self):
        observations = [copy.deepcopy(self.fixtures[name]) for name in ("event_mushrooms", "event_sphere")]
        for observation in observations:
            observation["ooc"]["publicState"]["rewardPityHistoryComplete"] = False
        for response in self.run_rows(observations, policy="v4"):
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["status"], "UNSUPPORTED")
            self.assertEqual(evaluator["reason"], "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED")

    def test_library_uses_public_heal_and_marginalized_reward_pity(self):
        observation = copy.deepcopy(self.fixtures["event_library"])
        observation["ooc"]["publicState"]["rewardPityHistoryComplete"] = False
        direct, = self.run_rows([observation], policy="v4")
        self.assertEqual(direct["evaluators"][0]["status"], "UNSUPPORTED")
        self.assertEqual(direct["evaluators"][0]["reason"], "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED")
        trace, = self.run_rows([observation], policy="mcts", differential=True)
        self.assertEqual(trace["evaluators"][0]["reason"], "DIFFERENTIAL_HIDDEN_REWARD_PITY_UNREPRESENTABLE")
        sampled, = self.run_rows([observation], policy="mcts")
        evaluator, = sampled["evaluators"]
        self.assertEqual(evaluator["status"], "OK", sampled)
        self.assertIn(evaluator["selectedLiveAction"], [c["liveAction"] for c in observation["ooc"]["liveChoices"]])

    def test_library_result_is_forced_after_read_or_sleep(self):
        observation = copy.deepcopy(self.fixtures["event_library"])
        ooc = observation["ooc"]
        ooc["event"] = dict(id="The Library", phase="1", options=[dict(index=0, disabled=False)])
        ooc["details"].pop("hpAmount0")
        ooc["details"]["mechanicalTransition"] = "event_leave"
        ooc["liveChoices"] = [dict(nativeAction=dict(kind="option", index=0, group=0),
                                   liveAction=dict(kind="choose", choiceIndex=1))]
        response, = self.run_rows([observation], model=False)
        self.assertEqual(response["evaluators"][0]["status"], "OK", response)
        self.assertEqual(response["evaluators"][0]["valueSemantics"], "forced_no_search")

    def test_resumed_combat_class_history_fails_closed(self):
        observation = copy.deepcopy(self.fixtures["event_big_fish"])
        observation["ooc"]["publicState"]["combatHistoryComplete"] = False
        response, = self.run_rows([observation])
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "UNSUPPORTED")
        self.assertEqual(evaluator["reason"], "PUBLIC_COMBAT_CLASS_HISTORY_UNQUALIFIED")

    def test_missing_model_keeps_explicit_unsupported(self):
        response, = self.run_rows([self.fixtures["event_big_fish"]], model=False, policy="v4")
        self.assertEqual(response["evaluators"][0]["reason"], "MODEL_UNAVAILABLE")

    def test_compound_candidates_preserve_semantic_targets(self):
        rest, wall = self.run_rows([
            self.fixtures["rest_smith_lift_dig_remove_key"], self.fixtures["event_living_wall"]],
            policy="v4")
        selector, = self.run_rows([self.fixtures["upgrade_duplicate_physical_cards"]], policy="v4")
        for response in (wall,):
            evaluator = response["evaluators"][0]
            self.assertEqual(evaluator["status"], "OK")
            targeted = [c for c in evaluator["candidateSummaries"]
                        if c["semanticPayload"].get("type") in {"transaction", "deck_card", "event"}
                        or c["semanticPayload"].get("compoundTarget")]
            self.assertTrue(targeted)
            self.assertTrue(all("visits" in c and "prior" in c for c in targeted))
        self.assertEqual(selector["evaluators"][0]["status"], "OK")

    def test_compound_source_retains_target_before_selector_score(self):
        selector = self.fixtures["upgrade_duplicate_physical_cards"]
        standalone, = self.run_rows([selector], policy="v4")
        source, retained = self.run_rows([
            self.fixtures["event_living_wall"], selector], policy="v4")
        standalone_eval = standalone["evaluators"][0]
        source_eval = source["evaluators"][0]
        retained_eval = retained["evaluators"][0]
        self.assertEqual(source_eval["compoundPlan"]["status"], "PENDING")
        self.assertEqual(retained_eval["compoundPlan"]["status"], "APPLIED")
        self.assertEqual(retained_eval["compoundPlan"]["selectionMode"],
                         "retained_compound_target")
        self.assertNotEqual(standalone_eval["selectedSemanticKey"],
                            retained_eval["selectedSemanticKey"])
        chosen = next(c for c in retained_eval["candidateSummaries"]
                      if c["semanticKey"] == retained_eval["selectedSemanticKey"])
        self.assertEqual(chosen["visits"], max(c["visits"]
                                                for c in retained_eval["candidateSummaries"]))

    def test_semantic_only_roots_use_uniform_prior_and_checkpoint_leaf(self):
        rows = self.run_rows([self.fixtures["remove_selector"]])
        for response in rows:
            evaluator, = response["evaluators"]
            self.assertEqual(evaluator["status"], "OK", response)
            priors = [candidate["prior"] for candidate in evaluator["candidateSummaries"]]
            self.assertTrue(priors)
            self.assertTrue(all(abs(prior - priors[0]) < 1e-12 for prior in priors), response)
            self.assertLess(len(evaluator["candidateSummaries"]),
                            len(self.fixtures["remove_selector"]["ooc"]["liveChoices"]))
            strike_keys = [candidate["semanticKey"] for candidate in evaluator["candidateSummaries"]
                           if ":card=321:" in candidate["semanticKey"]
                           and ":upgraded=0:" in candidate["semanticKey"]]
            self.assertEqual(len(strike_keys), 1)
            self.assertIn(":occurrence=0", strike_keys[0])

    def test_map_root_runs_mcts_and_stops_after_the_transition(self):
        response, = self.run_rows([self.fixtures["map_multiple_children"]])
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["model"]["kind"], "ooc_mcts_ctm")
        self.assertGreaterEqual(len(evaluator["candidateSummaries"]), 2)
        chosen = next(c for c in evaluator["candidateSummaries"]
                      if c["semanticKey"] == evaluator["selectedSemanticKey"])
        self.assertEqual(chosen["visits"], max(c["visits"] for c in evaluator["candidateSummaries"]))
        self.assertEqual(evaluator["selectedLiveAction"]["kind"], "choose")
        self.assertIsInstance(evaluator["selectedLiveAction"]["choiceIndex"], int)
        self.assertEqual(evaluator["valueSemantics"], "mean_backed_up_value_0_1")
        root = evaluator["valueDistribution"]
        self.assertEqual(root["schema"], "ooc_value_distribution_v1")
        self.assertEqual(root["normalization"], "share_of_own_samples")
        self.assertEqual(len(root["bins"]), 22)
        self.assertEqual(sum(root["bins"]), root["count"])
        self.assertEqual(root["terminalDeaths"], root["bins"][0])
        self.assertEqual(root["terminalVictories"], root["bins"][21])
        combined = [0] * 22
        weighted = 0
        for candidate in evaluator["candidateSummaries"]:
            values = candidate["valueDistribution"]
            self.assertEqual(values["count"], candidate["visits"])
            self.assertEqual(sum(values["bins"]), values["count"])
            if values["count"]:
                self.assertAlmostEqual(values["mean"], candidate["q"])
                weighted += values["mean"] * values["count"]
            else:
                self.assertIsNone(values["mean"])
            combined = [a + b for a, b in zip(combined, values["bins"])]
        self.assertEqual(combined, root["bins"])
        self.assertAlmostEqual(root["mean"], weighted / root["count"])
        self.assertNotIn("tree", evaluator)

    def test_opt_in_mcts_tree_capture_is_bounded_and_keeps_root_scores(self):
        observation = self.fixtures["map_multiple_children"]
        baseline, = self.run_rows([observation])
        captured, = self.run_rows([observation], debug_tree=True, tree_cap=8)
        before = baseline["evaluators"][0]
        after = captured["evaluators"][0]
        self.assertEqual(after["status"], "OK", captured)
        self.assertEqual(after["selectedSemanticKey"], before["selectedSemanticKey"])
        self.assertEqual(after["candidateSummaries"], before["candidateSummaries"])
        tree = after["tree"]
        self.assertTrue(tree["accepted"])
        self.assertTrue(tree["truncated"])
        self.assertEqual(len(tree["nodes"]), 8)
        self.assertEqual(tree["nodes"][0]["visits"], 512)
        roots = [n for n in tree["nodes"] if n["kind"] == "chance" and n["depth"] == 0]
        self.assertEqual(len(roots), len(after["candidateSummaries"]))
        self.assertTrue(all(n["label"].startswith("Travel to Monster room at (") for n in roots))
        self.assertEqual(sum(n["selected"] for n in roots), 1)
        self.assertTrue(all(n["screen"] == "map" and n["floor"] == tree["nodes"][0]["floor"]
                            for n in roots))
        self.assertTrue(any(e["kind"] == "particle" for e in tree["edges"]))
        self.assertTrue(any(e["combatModelUsed"] and e["combatOutcome"] in ("death", "victory", "escape")
                            for e in tree["edges"] if e["kind"] == "particle"))
        # The live CTM must receive the trained/default potion keep value 4.
        # A missing callback supplied 0 and made even early hallway fights
        # almost uniformly sampled losses at full health.
        self.assertTrue(any(e["combatModelUsed"] and e["combatOutcome"] == "victory"
                            for e in tree["edges"] if e["kind"] == "particle"))

    def test_endpoint_hp_samples_partition_the_search(self):
        # Unqualified room-chance fixtures retain the bounded map checkpoint.
        # The qualified-horizon test separately proves expansion beyond it.
        rows = self.run_rows([self.fixtures["map_multiple_children"],
                              self.fixtures["card_reward_duplicate_take_skip"]])
        offsets = []
        for row in rows:
            evaluator = row["evaluators"][0]
            self.assertEqual(evaluator["status"], "OK", row)
            dist = evaluator["endpointHpDistribution"]
            self.assertEqual(dist["schema"], "ooc_endpoint_hp_distribution_v1")
            bins = dist["axisMaxHp"] + 1
            self.assertGreaterEqual(bins, dist["maxHp"] + 1)
            root = dist["root"]
            self.assertEqual(root["count"] + root["unresolved"],
                             sum(c["visits"] for c in evaluator["candidateSummaries"]))
            layers = [c["endpointHp"] for c in evaluator["candidateSummaries"]]
            for layer in [root] + layers:
                self.assertEqual(len(layer["hpCounts"]), bins)
                self.assertEqual(sum(layer["hpCounts"]), layer["count"])
                self.assertEqual(layer["hpCounts"][0], layer["deaths"])
                self.assertEqual(sum(layer["floorOffsets"].values()), layer["count"])
            for key in ("count", "deaths", "unresolved"):
                self.assertEqual(sum(layer[key] for layer in layers), root[key])
            self.assertEqual([sum(column) for column in zip(*(l["hpCounts"] for l in layers))],
                             root["hpCounts"])
            offsets.append(root["floorOffsets"])
        self.assertEqual(set(offsets[0]), {"1"})
        self.assertEqual(set(offsets[1]), {"0"})
        card = rows[1]["evaluators"][0]["endpointHpDistribution"]
        self.assertEqual(card["root"]["hpCounts"][card["currentHp"]], card["root"]["count"])

    def test_qualified_question_history_expands_downstream_map(self):
        observation = copy.deepcopy(self.fixtures["card_reward_duplicate_take_skip"])
        observation["ooc"]["publicState"].update(questionHistoryComplete=True, questionOutcomes=[])
        # Taking/skipping the final reward reaches a same-floor MAP. The old
        # hard leaf evaluated every sample there (offset zero); qualified
        # history must permit the planner to enter a subsequent room.
        response, = self.run_rows([observation], label="qualified downstream map")
        evaluator = response["evaluators"][0]
        self.assertEqual(evaluator["status"], "OK", response)
        offsets = evaluator["endpointHpDistribution"]["root"]["floorOffsets"]
        self.assertTrue(any(int(offset) > 0 for offset in offsets), offsets)

    def test_map_root_rejects_incomplete_offered_relic_history(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        observation["ooc"]["publicState"]["seenRelicsComplete"] = False
        response, = self.run_rows([observation])
        evaluator = response["evaluators"][0]
        self.assertEqual(evaluator["status"], "UNSUPPORTED")
        self.assertEqual(evaluator["reason"], "PUBLIC_SEEN_RELIC_HISTORY_UNQUALIFIED")

    def test_unqualified_pity_never_becomes_a_v4_midpoint(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        observation["ooc"]["publicState"]["rewardPityHistoryComplete"] = False
        v4_response, = self.run_rows([observation], policy="v4")
        v4 = v4_response["evaluators"][0]
        self.assertEqual(v4["status"], "UNSUPPORTED")
        self.assertEqual(v4["reason"], "PUBLIC_REWARD_PITY_HISTORY_UNQUALIFIED")

        mcts_response, = self.run_rows([observation])
        mcts = mcts_response["evaluators"][0]
        self.assertEqual(mcts["status"], "OK")
        priors = [candidate["prior"] for candidate in mcts["candidateSummaries"]]
        self.assertTrue(priors)
        self.assertTrue(all(abs(prior - priors[0]) < 1e-12 for prior in priors), mcts)

    def test_opened_boss_chest_is_native_proceed_passthrough(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        ooc = observation["ooc"]
        ooc["screen"] = "treasure"
        ooc["details"] = {"chestType": "BossChest", "opened": True}
        ooc["liveChoices"] = [{"liveAction": {"kind": "proceed"},
                               "nativeAction": {"kind": "option", "index": 0}}]
        self.assertNotIn("unsupportedReason", ooc)
        response, = self.run_rows([observation], policy="v4")
        evaluator = response["evaluators"][0]
        self.assertEqual(evaluator["status"], "OK")
        self.assertEqual(evaluator["mode"], "native_pass_through")
        self.assertEqual(evaluator["selectedLiveAction"], {"kind": "proceed"})

    def test_unopened_treasure_samples_contents_from_public_size(self):
        observation = copy.deepcopy(self.fixtures["treasure_open_leave"])
        observation["ooc"]["details"].update(chestType="MediumChest", chestSize=1)
        observation["ooc"]["publicState"]["rewardPityHistoryComplete"] = False
        direct, = self.run_rows([observation], policy="v4")
        self.assertEqual(direct["evaluators"][0]["status"], "UNSUPPORTED")
        self.assertEqual(direct["evaluators"][0]["reason"], "PUBLIC_TREASURE_CONTENTS_UNQUALIFIED")
        trace, = self.run_rows([observation], policy="mcts", differential=True)
        self.assertEqual(trace["evaluators"][0]["status"], "UNSUPPORTED")
        self.assertEqual(trace["evaluators"][0]["reason"], "DIFFERENTIAL_HIDDEN_TREASURE_UNREPRESENTABLE")
        sampled, = self.run_rows([observation], policy="mcts")
        evaluator, = sampled["evaluators"]
        self.assertEqual(evaluator["status"], "OK", sampled)
        captured = [row["liveAction"] for row in observation["ooc"]["liveChoices"]]
        self.assertIn(evaluator["selectedLiveAction"], captured)
        self.assertEqual(len(evaluator["candidateSummaries"]), 2)

    def test_hidden_card_group_still_passes_through_captured_gold(self):
        observation = copy.deepcopy(self.fixtures["rewards_without_cards"])
        ooc = observation["ooc"]
        ooc["screen"] = "combat_reward"
        ooc["unsupportedReason"] = "CARD_GROUP_NOT_REVEALED"
        # No model is configured: OK proves the gold path bypasses MCTS/V4.
        first, = self.run_rows([observation], model=False, policy="mcts")
        evaluator, = first["evaluators"]
        self.assertEqual(evaluator["status"], "OK", first)
        self.assertEqual(evaluator["mode"], "native_pass_through")
        self.assertEqual(evaluator["selectedSemanticKey"], "ooc-live:v1:take-gold")
        self.assertEqual(evaluator["selectedLiveAction"]["kind"], "choose")

        after_gold = copy.deepcopy(observation)
        after_gold["ooc"]["details"]["gold"] = []
        after_gold["ooc"]["liveChoices"] = [
            choice for choice in after_gold["ooc"]["liveChoices"]
            if choice["nativeAction"]["kind"] != "gold"
        ]
        second, = self.run_rows([after_gold], model=False, policy="mcts")
        second_evaluator, = second["evaluators"]
        self.assertEqual(second_evaluator["status"], "UNSUPPORTED", second)
        self.assertEqual(second_evaluator["reason"], "CARD_GROUP_NOT_REVEALED")

    def test_hidden_card_group_rejects_duplicate_gold_mapping(self):
        observation = copy.deepcopy(self.fixtures["rewards_without_cards"])
        ooc = observation["ooc"]
        ooc["screen"] = "combat_reward"
        ooc["unsupportedReason"] = "CARD_GROUP_NOT_REVEALED"
        gold_choice = next(choice for choice in ooc["liveChoices"]
                           if choice["nativeAction"]["kind"] == "gold")
        ooc["liveChoices"].append(copy.deepcopy(gold_choice))
        response, = self.run_rows([observation], model=False, policy="mcts")
        self.assertEqual(response["status"], "ERROR", response)

    def test_hidden_card_group_rejects_invalid_gold_mapping(self):
        for mutation in ("index", "action"):
            observation = copy.deepcopy(self.fixtures["rewards_without_cards"])
            ooc = observation["ooc"]
            ooc["screen"] = "combat_reward"
            ooc["unsupportedReason"] = "CARD_GROUP_NOT_REVEALED"
            gold_choice = next(choice for choice in ooc["liveChoices"]
                               if choice["nativeAction"]["kind"] == "gold")
            if mutation == "index":
                gold_choice["nativeAction"]["index"] = 255
            else:
                gold_choice["liveAction"] = {"kind": "proceed"}
            response, = self.run_rows([observation], model=False, policy="mcts")
            self.assertEqual(response["status"], "ERROR", response)

    def test_woman_in_blue_is_a_complete_live_mcts_root(self):
        response, = self.run_rows([self.fixtures["event_woman_in_blue"]])
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["model"]["kind"], "ooc_mcts_ctm")
        self.assertEqual(evaluator["model"]["simulations"], 512)
        self.assertEqual(len(evaluator["candidateSummaries"]), 4)
        self.assertEqual(
            {candidate["liveAction"]["choiceIndex"] for candidate in evaluator["candidateSummaries"]},
            {1, 2, 3, 4},
        )
        chosen = next(candidate for candidate in evaluator["candidateSummaries"]
                      if candidate["semanticKey"] == evaluator["selectedSemanticKey"])
        self.assertEqual(chosen["visits"], max(candidate["visits"]
                                                for candidate in evaluator["candidateSummaries"]))
        self.assertEqual(chosen["liveAction"], evaluator["selectedLiveAction"])

    def test_complete_history_map_root_scores_paths(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        observation["ooc"]["publicState"]["seenRelicsComplete"] = True
        response, = self.run_rows([observation])
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "OK", response)
        self.assertEqual(evaluator["model"]["simulations"], 512)
        self.assertGreater(len(evaluator["candidateSummaries"]), 1)
        self.assertEqual(sum(c["visits"] for c in evaluator["candidateSummaries"]), 512)

    def test_missing_floor_model_fails_closed(self):
        observation = copy.deepcopy(self.fixtures["map_multiple_children"])
        observation["ooc"]["publicState"]["seenRelicsComplete"] = True
        response, = self.run_rows([observation], floor_model=False)
        evaluator, = response["evaluators"]
        self.assertEqual(evaluator["status"], "UNSUPPORTED")
        self.assertEqual(evaluator["reason"], "OOC_FLOOR_MODEL_UNAVAILABLE")

    def test_capture_support_boundary(self):
        response, = self.run_rows([{"boundary": "ooc", "ooc": {
            "schemaVersion": 1, "screen": "selector", "unsupportedReason": "SELECTOR_CONFIRMATION_ONLY"}}],
                                  policy="v4")
        self.assertEqual(response["evaluators"][0]["status"], "UNSUPPORTED")

    def test_active_winged_is_bounded_to_non_map_roots(self):
        selector = copy.deepcopy(self.fixtures["upgrade_duplicate_physical_cards"])
        selector["ooc"]["publicState"]["relics"].append(
            {"id": "WingedGreaves", "data": 0, "liveCounter": 3})
        selector["ooc"]["publicState"]["acquiredRelics"].append("WingedGreaves")
        selector["ooc"]["unsupportedReason"] = \
            "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"
        response, = self.run_rows([selector])
        self.assertEqual(response["evaluators"][0]["status"], "OK", response)

        direct_map = copy.deepcopy(self.fixtures["map_multiple_children"])
        direct_map["ooc"]["publicState"]["relics"].append(
            {"id": "WingedGreaves", "data": 0, "liveCounter": 3})
        direct_map["ooc"]["publicState"]["acquiredRelics"].append("WingedGreaves")
        direct_map["ooc"]["unsupportedReason"] = \
            "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active"
        response, = self.run_rows([direct_map], policy="v4")
        self.assertEqual(response["evaluators"][0]["status"], "UNSUPPORTED")
        self.assertEqual(response["evaluators"][0]["reason"],
                         "RELIC_NATIVE_STATE_UNREPRESENTABLE:WingedGreaves:active")

    def test_schema_and_mapping_errors_cannot_fallback(self):
        base = self.fixtures["event_big_fish"]
        invalid_schema = copy.deepcopy(base)
        invalid_schema["ooc"]["publicState"].pop("pathVisits")
        missing = copy.deepcopy(base)
        missing["ooc"]["liveChoices"].pop()
        duplicate = copy.deepcopy(base)
        duplicate["ooc"]["liveChoices"].append(duplicate["ooc"]["liveChoices"][0])
        for model in (True, False):
            for response in self.run_rows([invalid_schema, missing, duplicate], model=model,
                                          policy="v4"):
                self.assertEqual(response["status"], "ERROR")
                self.assertNotIn("evaluators", response)

    def test_capture_integrity_error_overrides_unsupported(self):
        observation = {"boundary": "ooc", "ooc": {
            "schemaVersion": 1, "screen": "map", "captureError": "IllegalArgumentException:bad edge",
            "unsupportedReason": "MODEL_UNAVAILABLE"}}
        for model in (True, False):
            response, = self.run_rows([observation], model=model, policy="v4")
            self.assertEqual(response["status"], "ERROR")
            self.assertNotIn("evaluators", response)


if __name__ == "__main__":
    unittest.main(argv=[sys.argv[0]])
