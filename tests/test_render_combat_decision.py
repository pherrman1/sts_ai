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
            "hand": [{"id": "Bash", "name": "Bash", "uuid": "bash-1", "upgraded": False,
                      "cost": 2, "costForTurn": 2}],
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

    def test_card_panel_prefers_current_playable_cost(self):
        with tempfile.TemporaryDirectory() as directory:
            value = snapshot_data()
            value["observation"]["combat"]["hand"][0]["costForTurn"] = 0
            source = load_snapshot(self.write_json(directory, "latest.json", value))
            rendered = render_html(source)
            self.assertIn("<td>Bash</td><td>bash-1</td><td>no</td><td>0</td>", rendered)

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

    def test_applied_silver_prior_is_rendered_separately_from_q_and_visits(self):
        with tempfile.TemporaryDirectory() as directory:
            value = snapshot_data(priorModel={
                "loaded": True, "applied": True, "status": "APPLIED",
                "artifactSha256": "prior-artifact-sha", "scope": "root_only", "puctC": 2.5,
            })
            summaries = value["response"]["advisor"]["evaluators"][0]["rootActionSummaries"]
            summaries[0].update(priorLogit=2.4483, prior=0.8244)
            summaries[1].update(priorLogit=-0.4521, prior=0.1756)
            source = load_snapshot(self.write_json(directory, "latest.json", value))
            rendered = render_html(source)
            self.assertIn("prior logit", rendered)
            self.assertIn("root P(a|state)", rendered)
            self.assertIn("Loaded SilverPriorNet root policy", rendered)
            self.assertIn("2.4483", rendered)
            self.assertIn("0.8244", rendered)
            self.assertIn("prior-artifact-sha", rendered)

    def test_malformed_visit_share_is_preserved_but_bar_is_safe(self):
        with tempfile.TemporaryDirectory() as directory:
            value = snapshot_data()
            value["response"]["advisor"]["evaluators"][0]["rootActionSummaries"][0]["visitShare"] = 1.5
            source = load_snapshot(self.write_json(directory, "latest.json", value))
            rendered = render_html(source)
            self.assertIn(">1.5</span>", rendered)
            self.assertIn("width:100.000%", rendered)

    def test_debug_tree_renders_expandable_graph_and_state_toggle(self):
        with tempfile.TemporaryDirectory() as directory:
            value = snapshot_data()
            value["response"]["advisor"]["evaluators"][0]["tree"] = {
                "accepted": True, "truncated": False, "rootId": 1,
                "retainedNodeCount": 3, "retainedEdgeCount": 3,
                "nodes": [
                    {"id": 1, "parentId": 0, "depth": 0, "isChanceNode": False,
                     "hasState": True, "stateHash": 11, "simulationCount": 10,
                     "victoryCount": 4, "evaluationSum": 7.5,
                     "state": {"turn": 3, "player": {"curHp": 55}}},
                    {"id": 2, "parent