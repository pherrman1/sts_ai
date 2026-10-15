import copy
import unittest

try:
    from tools.combat_predictor_input_contract import (
        FIELD_SCHEMA_HASH, SCHEMA_VERSION, validate_predictor_input,
    )
except ModuleNotFoundError:
    from combat_predictor_input_contract import (
        FIELD_SCHEMA_HASH, SCHEMA_VERSION, validate_predictor_input,
    )


def sample():
    return {
        "schemaVersion": SCHEMA_VERSION,
        "fieldSchemaHash": FIELD_SCHEMA_HASH,
        "globals": {
            "characterClass": 0, "ascension": 0, "act": 1, "floor": 1,
            "curHp": 80, "maxHp": 80, "gold": 99, "encounter": 1,
            "roomClass": 4, "lastRoom": 1, "potionCount": 0,
            "potionCapacity": 3, "potionKeepValue": 4.0,
            "isBurningElite": False,
        },
        "cards": [{"cardId": 1, "upgraded": False, "misc": 0, "bottleBinding": -1}],
        "relics": [{"relicId": 1, "data": 0, "orderIndex": 0}],
        "potions": [{"slot": i, "potionId": 1} for i in range(5)],
    }


class TestCombatPredictorInputContract(unittest.TestCase):
    def test_accepts_typed_v1_input(self):
        self.assertIsNotNone(validate_predictor_input(sample()))

    def test_rejects_hidden_or_future_fields(self):
        for field in ("aiRng", "runSeed", "futureEncounterQueues"):
            candidate = copy.deepcopy(sample())
            candidate[field] = 1
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, "keys mismatch"):
                validate_predictor_input(candidate)

    def test_rejects_hidden_field_inside_globals(self):
        candidate = copy.deepcopy(sample())
        candidate["globals"]["shuffleRng"] = 1
        with self.assertRaisesRegex(ValueError, "keys mismatch"):
            validate_predictor_input(candidate)

    def test_rejects_noncanonical_cards_and_wrong_slots(self):
        candidate = copy.deepcopy(sample())
        candidate["cards"].append({"cardId": 0, "upgraded": False,
                                   "misc": 0, "bottleBinding": -1})
        with self.assertRaisesRegex(ValueError, "canonical"):
            validate_predictor_input(candidate)
        candidate = sample()
        candidate["potions"][0]["slot"] = 1
        with self.assertRaisesRegex(ValueError, "slots"):
            validate_predictor_input(candidate)


if __name__ == "__main__":
    unittest.main()
