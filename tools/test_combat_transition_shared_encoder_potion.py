import unittest

import numpy as np
import torch

from tools import combat_transition_shared_encoder_potion as experiment
from tools import combat_transition_potion_trajectory as trajectory
from tools import combat_transition_stochastic_hp as stochastic_hp


class SharedEncoderPotionTests(unittest.TestCase):
    def test_candidate_and_decoder_initialization_are_structural(self):
        width = 10
        classes = np.arange(-160, 144, dtype=np.int64)
        delta_values = np.arange(11, dtype=np.int64)
        source = stochastic_hp.new_model(
            torch, np.zeros(width, np.float32), np.ones(width, np.float32),
            len(delta_values), classes, experiment.RECIPE["seed"]
        )
        max_head = torch.nn.Linear(64, len(delta_values))
        model, loaded_head = experiment.model_from_candidate(
            {"stateDict": source.state_dict(), "maxHpHeadStateDict": max_head.state_dict()},
            len(delta_values), classes, "cpu"
        )
        self.assertEqual(experiment.state_digest(model.state_dict()), experiment.state_digest(source.state_dict()))
        self.assertTrue(torch.equal(loaded_head.weight, max_head.weight))

        decoder = trajectory.new_decoder(len(delta_values))
        loaded_decoder = experiment.potion_from_component(
            {"headStateDicts": [decoder.state_dict()]}, len(delta_values), "cpu"
        )
        self.assertEqual(experiment.state_digest(loaded_decoder.state_dict()), experiment.state_digest(decoder.state_dict()))

    def test_fixed_order_and_calibration_selection_are_deterministic(self):
        train = np.arange(20_000, dtype=np.int64)
        first, first_digest = experiment.fixed_order(train)
        second, second_digest = experiment.fixed_order(train)
        self.assertEqual(first_digest, second_digest)
        for a, b in zip(first, second):
            np.testing.assert_array_equal(a, b)

    def test_pr197_preservation_gate_is_strict(self):
        teacher = {
            "maxHP": {"overall": {"nll": 1., "accuracy": .9, "expectedPostMaxHpMae": .1},
                      "slices": {"nonzeroDelta": {"rows": 1, "nll": 1., "accuracy": .8}}},
            "HP": {"overall": {"nll": 1., "crps": 1., "expectedMae": .1},
                   "slices": {"damage": {"rows": 1, "nll": 1., "crps": 1., "expectedMae": .1}}},
        }
        student = {
            "maxHP": {"overall": {"nll": 1.02, "accuracy": .895, "expectedPostMaxHpMae": .201},
                      "slices": {"nonzeroDelta": {"rows": 1, "nll": 1., "accuracy": .75}}},
            "HP": {"overall": {"nll": 1.02, "crps": 1.02, "expectedMae": .25},
                   "slices": {"damage": {"rows": 1, "nll": 1., "crps": 1., "expectedMae": .1}}},
        }
        eligible, gates = experiment.gate_eligible(teacher, student)
        self.assertFalse(eligible)
        self.assertGreater(gates["maxHpExpectedMaeDelta"], .1)


if __name__ == "__main__":
    unittest.main()
