"""Checks for tools/combat_parity.py and the combat_parity_probe executable.

The probe tests need COMBAT_PARITY_PROBE (set by ctest); without it they skip.
No Java capture exists yet, so the probe tests use a real live observation
fixture with synthetic hidden RNG and draw order. They prove the plumbing
(exact draw order, RNG seeding, skip reasons), not Java/native parity.
"""

from __future__ import annotations

import copy
import json
import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))

import combat_parity  # noqa: E402

FIXTURE = ROOT / "tests" / "fixtures" / "live_slime_boss_split.json"
DEFEND = "sa/t=1/s=1/c=104_17_0_1_1_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=0/sel="
END_TURN = "sa/t=5/s=0/c=0_0_0_0_0_0_0_0/o=0/p=0_-1/x=-1/d=0/k=0/task=0/sel="
STREAMS = ("aiRng", "cardRandomRng", "cardRng", "eventRng", "merchantRng", "miscRng",
           "monsterHpRng", "monsterRng", "potionRng", "relicRng", "shuffleRng", "treasureRng")


def observation() -> dict:
    return json.loads(FIXTURE.read_text())


def rng(obs: dict, *, order=None) -> dict:
    draw = obs["silverRoot"]["combat"]["draw"]
    uuids = [card["uuid"] for card in draw]
    return {"schema": "sts_java_rng_v1", "available": True,
            "streams": {name: {"counter": i, "seed0": str(1000003 + 7 * i), "seed1": str(2000003 + 11 * i)}
                        for i, name in enumerate(STREAMS)},
            "drawPileUuids": uuids if order is None else order(uuids)}


def silver_row(step: int, obs: dict, *, action=END_TURN, post_combat=True, outcome=None, source="silver"):
    return {"step": step, "inspector_boundary": "combat", "inspector_session": "s",
            "decision_source": source, "live_observation": obs, "preRng": rng(obs),
            "silver_evaluator": {"selectedAction": action, "selectedLabel": "End Turn"},
            "post_screen_kind": {"combat": post_combat, "terminal": outcome is not None, "outcome": outcome}}


class ExtractTest(unittest.TestCase):
    def test_pairs_with_next_observation_and_skips_confirmation(self):
        obs = observation()
        confirm = {"step": 1, "inspector_boundary": "combat", "live_observation": obs,
                   "silver_evaluator": {"mode": "native_pass_through"}}
        rows = [silver_row(0, obs), confirm, silver_row(2, obs)]
        steps, skipped = combat_parity.extract_steps(rows)
        self.assertEqual([s["step"] for s in steps], [0])
        self.assertEqual(steps[0]["postBoundary"], "combat")
        self.assertEqual(skipped["TRACE_ENDED"], 1)

    def test_gap_and_fallback(self):
        obs = observation()
        rows = [silver_row(0, obs), {"step": 1, "decision_source": "run_control"},
                silver_row(2, obs, source="deterministic_fallback")]
        steps, skipped = combat_parity.extract_steps(rows)
        self.assertEqual(steps, [])
        self.assertEqual(skipped["GAP_IN_TRACE"], 1)
        self.assertEqual(skipped["NO_SEMANTIC_ACTION"], 1)

    def test_requires_parity_screen_kind(self):
        row = silver_row(0, observation())
        del row["post_screen_kind"]
        steps, skipped = combat_parity.extract_steps([row])
        self.assertEqual(steps, [])
        self.assertEqual(skipped["NO_POST_SCREEN_KIND"], 1)

    def test_combat_end_and_death(self):
        obs = observation()
        steps, _ = combat_parity.extract_steps([silver_row(0, obs, post_combat=False)])
        self.assertEqual(steps[0]["postBoundary"], "ooc")
        steps, _ = combat_parity.extract_steps([silver_row(0, obs, post_combat=False, outcome="death")])
        self.assertEqual(steps[0]["postBoundary"], "death")


class DiffTest(unittest.TestCase):
    def test_ignores_bookkeeping_and_labels_hand_order(self):
        a = {"hand": [{"id": 1, "uniqueId": 3}, {"id": 2, "uniqueId": 4}], "isolatedSearchSeed": 1, "x": 1}
        b = {"hand": [{"id": 2, "uniqueId": 9}, {"id": 1, "uniqueId": 8}], "isolatedSearchSeed": 2, "x": 2}
        diffs = combat_parity.diff(combat_parity.normalize(a), combat_parity.normalize(b))
        self.assertEqual([d["path"] for d in diffs], ["hand(order)", "x"])

    def test_field_group(self):
        self.assertEqual(combat_parity.field_group("monsters[2].curHp"), "monsters[].curHp")


PROBE = os.environ.get("COMBAT_PARITY_PROBE")


@unittest.skipUnless(PROBE and Path(PROBE).exists(), "COMBAT_PARITY_PROBE not built")
class ProbeTest(unittest.TestCase):
    def probe(self, steps):
        return combat_parity.run_probe(Path(PROBE), steps)

    def step(self, obs, preRng, **extra):
        return {"step": 0, "session": "s", "pre": obs, "preRng": preRng, "action": END_TURN, **extra}

    def test_end_turn_draws_from_the_given_top(self):
        obs = observation()
        for order in (None, lambda u: list(reversed(u))):
            r = rng(obs, order=order)
            # The game side of a compared step is the imported state with the
            # given order, so it shows the native ids of that order.
            step = self.step(obs, r, postBoundary="combat", post=copy.deepcopy(obs), postRng=r)
            result = self.probe([step])[0]
            self.assertEqual(result["status"], "COMPARED", result)
            key = lambda c: (c["id"], c["upgraded"])
            given = [key(c) for c in result["game"]["drawPile"]["knownTop"]]
            self.assertEqual(len(given), len(r["drawPileUuids"]))
            self.assertEqual([key(c) for c in result["native"]["hand"]], list(reversed(given[-5:])))
            self.assertEqual([key(c) for c in result["native"]["drawPile"]["knownTop"]], given[:-5])

    def test_draw_order_changes_the_successor_and_is_deterministic(self):
        obs = observation()
        forward = self.step(obs, rng(obs), postBoundary="ooc")
        backward = self.step(obs, rng(obs, order=lambda u: list(reversed(u))), postBoundary="ooc")
        a, b, a2 = self.probe([forward, backward, forward])
        self.assertEqual(a, a2)
        self.assertNotEqual(a["native"]["hand"], b["native"]["hand"])

    def test_rng_is_seeded_from_the_game(self):
        obs = observation()
        r = rng(obs)
        result = self.probe([self.step(obs, r, postBoundary="ooc")])[0]
        # Streams the monster turn does not touch keep the game's values.
        self.assertEqual(result["nativeRng"]["shuffleRng"]["seed0"], r["streams"]["shuffleRng"]["seed0"])
        self.assertEqual(result["nativeRng"]["shuffleRng"]["counter"], r["streams"]["shuffleRng"]["counter"])

    def test_compared_step_reports_differences(self):
        obs = observation()
        r = rng(obs)
        # Using the pre state as the "game" successor must mismatch.
        step = self.step(obs, r, postBoundary="combat", post=copy.deepcopy(obs), postRng=r)
        result = self.probe([step])[0]
        self.assertEqual(result["status"], "COMPARED", result)
        verdict = combat_parity.compare(step, result)
        self.assertEqual(verdict["verdict"], "MISMATCH")
        self.assertTrue(any(d["path"] == "turn" for d in verdict["diffs"]))

    def test_run_writes_report(self):
        import tempfile
        obs = observation()
        rows = [silver_row(0, obs), silver_row(1, obs, post_combat=False)]
        with tempfile.TemporaryDirectory() as tmp:
            trace = Path(tmp) / "trace.jsonl"
            trace.write_text("".join(json.dumps(r) + "\n" for r in rows))
            out = Path(tmp) / "out"
            self.assertEqual(combat_parity.main(["run", str(trace), "--probe", PROBE, "--out-dir", str(out)]), 0)
            summary = json.loads((out / "summary.json").read_text())
            self.assertEqual(summary["verdicts"], {"MISMATCH": 2})
            self.assertIn("encounter", summary["coverage"])
            self.assertIn("Mismatched fields", (out / "REPORT.md").read_text())

    def defend_step(self, mutate=None, post_rng=None):
        """Defend on the fixture with a hand-written correct game successor."""
        obs = observation()
        r = rng(obs)
        post = copy.deepcopy(obs)
        combat = post["silverRoot"]["combat"]
        card = combat["hand"].pop(next(i for i, c in enumerate(combat["hand"]) if c["id"] == "Defend_R"))
        combat["discard"].append({**card, "location": "DISCARD"})
        combat["block"] += 5
        combat["energy"] -= 1
        combat["cardsPlayedThisTurn"] += 1
        combat["skillsPlayedThisTurn"] += 1
        if mutate:
            mutate(combat)
        return {"step": 0, "session": "s", "pre": obs, "preRng": r, "action": DEFEND,
                "postBoundary": "combat", "post": post, "postRng": post_rng or r}

    def test_positive_control_matches(self):
        step = self.defend_step()
        verdict = combat_parity.compare(step, self.probe([step])[0])
        self.assertEqual(verdict["verdict"], "MATCH", verdict.get("diffs"))
        # Native-only bookkeeping is reported, not judged.
        self.assertIn("loopCount", [d["path"] for d in verdict["unobservable"]])

    def test_one_wrong_field_is_the_only_mismatch(self):
        step = self.defend_step(mutate=lambda c: c.update(block=c["block"] + 1))
        verdict = combat_parity.compare(step, self.probe([step])[0])
        self.assertEqual([d["path"] for d in verdict["diffs"]], ["player.block"])

    def test_non_combat_stream_use_is_a_mismatch(self):
        obs = observation()
        post_rng = copy.deepcopy(rng(obs))
        post_rng["streams"]["cardRng"]["counter"] += 1
        step = self.defend_step(post_rng=post_rng)
        verdict = combat_parity.compare(step, self.probe([step])[0])
        self.assertEqual([d["path"] for d in verdict["diffs"]], ["rng.cardRng(not simulated in combat)"])

    def test_action_found_despite_other_importer_ids(self):
        # The advisor imported more rows than the probe, so its ids differ.
        step = {**self.defend_step(), "action": DEFEND.replace("c=104_17_", "c=104_40_")}
        self.assertEqual(self.probe([step])[0]["status"], "COMPARED")
        uuid = next(c["uuid"] for c in step["pre"]["silverRoot"]["combat"]["hand"] if c["id"] == "Defend_R")
        step["liveAction"] = {"kind": "card", "cardUuid": uuid}
        self.assertEqual(self.probe([step])[0]["status"], "COMPARED")

    def test_removed_status_leaves_no_payload(self):
        # Native clears No Draw at end of turn by its bit only; the projection
        # must not export the stale amount a fresh import would not have.
        obs = observation()
        obs["silverRoot"]["combat"]["playerPowers"].append({"id": "No Draw", "amount": -1})
        r = rng(obs)
        result = self.probe([self.step(obs, r, postBoundary="ooc")])[0]
        player = result["native"]["player"]
        self.assertEqual(player["statusMap"], [[status, amount] for status, amount in player["statusMap"] if status != 16])
        self.assertEqual(result["native"]["cardSelect"]["task"], 0)

    def test_skip_reasons(self):
        obs = observation()
        no_rng = self.probe([self.step(obs, None, postBoundary="ooc")])[0]
        self.assertEqual(no_rng["category"], "EXACT_STATE_UNAVAILABLE")
        missing = self.probe([{**self.step(obs, rng(obs), postBoundary="ooc"), "action": "nope"}])[0]
        self.assertEqual(missing["category"], "RECORDED_ACTION_NOT_FOUND")
        self.assertIn(END_TURN, missing["legalActions"])
        bad_order = self.probe([self.step(obs, rng(obs, order=lambda u: u[:-1]), postBoundary="ooc")])[0]
        self.assertEqual(bad_order["category"], "EXACT_ORDER_UNAVAILABLE")


if __name__ == "__main__":
    unittest.main()
