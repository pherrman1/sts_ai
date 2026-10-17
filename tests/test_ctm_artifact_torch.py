"""Synthetic artifact reconstruction; no corpus, game seeds or model fitting."""
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest

import numpy as np
import torch

from tools import combat_transition_attention_ablation as attention
from tools import combat_transition_near_full_sampler as sampler
from tools import combat_transition_potion_trajectory as trajectory
from tools import combat_transition_sparse_evaluate as sparse
from tools import combat_transition_surrogate as surrogate
from tools import ctm_artifact_torch as loader
from tools import ctm_escape


def fixture(architecture="deepset"):
    tensors = {}
    def put(prefix, net):
        tensors.update({prefix + name: value.detach().cpu().numpy().copy()
                        for name, value in net.state_dict().items()})
    with torch.random.fork_rng(devices=[]):
        torch.manual_seed(5107)
        for index, group in enumerate(("survival", "max_hp", "hp", "potion_encoder")):
            mean = np.full(10, index + .25, np.float32)
            std = np.full(10, index + 1.5, np.float32)
            net = (surrogate.DeepSetsEncoder(torch.nn, torch, mean, std).net
                   if architecture == "deepset" else attention.AttentionEncoder(torch, mean, std).net)
            put(group + ".encoder.", net)
        put("survival.survival.", torch.nn.Linear(64, 1))
        put("max_hp.max_hp_delta.", torch.nn.Linear(64, 2))
        put("potion.", trajectory.new_decoder(2))
        ritual = sparse.net()
        ritual.context[0] = torch.nn.Linear(80, 64)
        put("ritual.", ritual)
        put("hp.delta_embedding.", torch.nn.Embedding(2, 8))
        hp = torch.nn.Sequential(torch.nn.Linear(73, 64), torch.nn.ReLU(), torch.nn.Linear(64, 3))
        put("hp.hp.", hp)
        put("escape.escape.", torch.nn.Linear(64, 1))
    metadata = dict(schema="COMBAT_TRANSITION_RUNTIME_V2", version=2,
                    hpClasses=[-1, 0, 1], maxHpClasses=[0, 3],
                    domain=dict(min=-1, max=1), capabilities=dict(escape={}))
    return metadata, tensors


class ArtifactTorchTest(unittest.TestCase):
    def test_exact_identity_required_before_load(self):
        metadata, tensors = fixture()
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.native"
            ctm_escape.write_artifact(path, metadata, tensors)
            digest = hashlib.sha256(path.read_bytes()).hexdigest()
            artifact = loader.load_artifact(path, digest)
            self.assertEqual(artifact.artifact_sha256, digest)
            for wrong in ("0" * 64, "", None):
                with self.subTest(wrong=wrong), self.assertRaisesRegex(ValueError, "SHA256"):
                    loader.load_artifact(path, wrong)
            path.write_bytes(path.read_bytes() + b"changed")
            with self.assertRaisesRegex(ValueError, "SHA256"):
                loader.load_artifact(path, digest)

    def test_all_encoders_keep_own_normalization_and_rng(self):
        for architecture in ("deepset", "attention"):
            metadata, tensors = fixture(architecture)
            before = torch.get_rng_state().clone()
            artifact = loader.ArtifactTorch(metadata, tensors, "synthetic")
            self.assertTrue(torch.equal(before, torch.get_rng_state()))
            for group, net in artifact.encoders.items():
                for key in ("scalar_mean", "scalar_inv"):
                    np.testing.assert_array_equal(net.state_dict()[key].numpy(),
                                                  tensors[group + ".encoder." + key])
                self.assertFalse(net.training)
                self.assertTrue(all(not parameter.requires_grad for parameter in net.parameters()))

    def test_partial_invalid_or_nonfinite_artifact_refused(self):
        metadata, tensors = fixture()
        for defect in ("normalization", "prefix", "hp_shape"):
            changed = copy.deepcopy(tensors)
            if defect == "normalization":
                changed["hp.encoder.scalar_inv"][0] = 0
            elif defect == "prefix":
                del changed["potion.mlp.2.bias"]
            else:
                changed["hp.hp.0.weight"] = np.zeros((64, 72), np.float32)
            with self.subTest(defect=defect), self.assertRaises(ValueError):
                loader.ArtifactTorch(metadata, changed, "synthetic")
        changed = copy.deepcopy(tensors)
        changed["ritual.context.0.bias"][0] = np.nan
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "synthetic.native"
            # Write finite bytes, then replace one float in its tensor payload.
            ctm_escape.write_artifact(path, metadata, tensors)
            original = path.read_bytes()
            target = tensors["ritual.context.0.bias"].tobytes()
            offset = original.rfind(target)
            self.assertGreaterEqual(offset, 0)
            path.write_bytes(original[:offset] + changed["ritual.context.0.bias"].tobytes()
                             + original[offset + len(target):])
            with self.assertRaisesRegex(ValueError, "nonfinite"):
                loader.load_artifact(path, hashlib.sha256(path.read_bytes()).hexdigest())

    def test_hp_uses_escape_bit_and_exact_legality(self):
        metadata, tensors = fixture()
        artifact = loader.ArtifactTorch(metadata, tensors, "synthetic")
        z = torch.zeros((2, 64))
        delta, pre, maximum = np.array([0, 1]), np.array([1, 3]), np.array([3, 3])
        for escaped in (0, 1):
            probabilities = artifact.hp_probabilities(z, delta, pre, maximum, escaped)
            features = torch.cat((z, torch.from_numpy(tensors["hp.delta_embedding.weight"])[delta],
                                  torch.full((2, 1), float(escaped))), -1)
            hidden = torch.relu(features @ torch.from_numpy(tensors["hp.hp.0.weight"]).T
                                + torch.from_numpy(tensors["hp.hp.0.bias"]))
            logits = hidden @ torch.from_numpy(tensors["hp.hp.2.weight"]).T + torch.from_numpy(tensors["hp.hp.2.bias"])
            legal = (pre[:, None] + artifact.classes[None] >= 1) & (pre[:, None] + artifact.classes[None] <= maximum[:, None])
            expected = torch.softmax(logits.masked_fill(~torch.from_numpy(legal), -torch.inf), -1).numpy()
            np.testing.assert_allclose(probabilities, expected, atol=1e-7, rtol=1e-6)
            self.assertTrue(np.all(probabilities[~legal] == 0))
        self.assertFalse(np.allclose(artifact.hp_probabilities(z, delta, pre, maximum, 0),
                                     artifact.hp_probabilities(z, delta, pre, maximum, 1)))

    def test_potion_and_ritual_match_existing_factories(self):
        metadata, tensors = fixture()
        artifact = loader.ArtifactTorch(metadata, tensors, "synthetic")
        with torch.random.fork_rng(devices=[]):
            potion = trajectory.new_decoder(2).eval()
            potion.load_state_dict(loader._state(tensors, "potion."), strict=True)
            ritual = sparse.net()
            ritual.context[0] = torch.nn.Linear(80, 64)
            ritual.load_state_dict(loader._state(tensors, "ritual."), strict=True)
            ritual.eval()
        z = torch.zeros((2, 64))
        inventory = np.array([[37, 1, 1, 1, 1], [17, 37, 1, 1, 1]])
        for escaped in (None, np.array([0, 1])):
            arguments = (z, inventory, np.array([3, 3]), np.array([0, 1]), np.array([.25, .75]), np.array([False, False]))
            with torch.inference_mode():
                expected = trajectory.log_probabilities(potion, *arguments, escape=escaped)
                actual = trajectory.log_probabilities(artifact.potion_net, *arguments, escape=escaped)
            torch.testing.assert_close(actual, expected)
        candidates = [np.array([[[.1, 0, 0]], [[.1, 0, .15]]], np.float32)] * 2
        arguments = (np.zeros((2, 64), np.float32), np.zeros((2, 3), np.float32),
                     np.zeros((2, 5), np.float32), np.zeros((2, 8), np.float32),
                     candidates, [np.array([True, False]), np.array([True, True])])
        with torch.inference_mode():
            np.testing.assert_allclose(sampler.batch_event_probabilities(artifact.ritual_net, *arguments),
                                       sampler.batch_event_probabilities(ritual, *arguments))


if __name__ == "__main__":
    unittest.main()
