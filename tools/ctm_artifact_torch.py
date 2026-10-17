"""Read-only FP32 inference from an identity-pinned near-full CTM artifact.

This reconstructs the ordinary Attention/DeepSets child, including its escape
conditioned HP head. Initial-Brew routing and active-Lizard composition belong
to the caller. No checkpoints, prepared arrays, labels or training are loaded.
"""
from __future__ import annotations

import hashlib
from pathlib import Path
import re

import numpy as np
import torch

from tools import combat_transition_attention_ablation as attention
from tools import combat_transition_composed as composed
from tools import combat_transition_surrogate as surrogate
from tools import ctm_escape


def _require(condition, message):
    if not condition:
        raise ValueError(message)


class _PotionHead(torch.nn.Module):
    """The existing trajectory decoder's output_logits contract."""
    def __init__(self, delta_count):
        super().__init__()
        self.delta = torch.nn.Embedding(delta_count, 8)
        self.potion = torch.nn.Embedding(surrogate.POTION_COUNT, 8)
        self.slot = torch.nn.Embedding(5, 4)
        self.mlp = torch.nn.Sequential(torch.nn.Linear(133, 64), torch.nn.ReLU(),
                                       torch.nn.Linear(64, 64))

    def output_logits(self, z, inventory, delta, fraction):
        shared = torch.cat((z.detach(), self.delta(delta), fraction[:, None]), -1)
        items = torch.cat((self.potion(inventory),
                           self.slot.weight[None].expand(len(z), -1, -1)), -1)
        return self.mlp(torch.cat((shared, items.flatten(1)), -1))


class _RitualHead(torch.nn.Module):
    """The existing conditioned sparse event scorer (80 -> 64 -> 32)."""
    def __init__(self):
        super().__init__()
        self.context = torch.nn.Sequential(torch.nn.Linear(80, 64), torch.nn.ReLU(),
                                           torch.nn.Linear(64, 32))
        self.event = torch.nn.Sequential(torch.nn.Linear(3, 32), torch.nn.Tanh())

    def forward(self, z, hp, bits, features, candidates, legal):
        _require(bool(legal.any(-1).all()), "empty native event support")
        context = self.context(torch.cat((z.detach(), hp, bits, features), -1))
        embedded = self.event(candidates).sum(-2)
        logits = (embedded * context[:, None]).sum(-1) / np.sqrt(32)
        return torch.log_softmax(logits.masked_fill(~legal, -torch.inf), -1)


def _state(tensors, prefix):
    result = {name[len(prefix):]: torch.from_numpy(value.copy())
              for name, value in tensors.items() if name.startswith(prefix)}
    _require(bool(result), "artifact tensor prefix missing: " + prefix)
    return result


def _load(module, tensors, prefix):
    try:
        module.load_state_dict(_state(tensors, prefix), strict=True)
    except RuntimeError as exc:
        raise ValueError("artifact tensor schema differs: " + prefix) from exc
    return module.eval().requires_grad_(False)


def _encoder(tensors, prefix):
    state = _state(tensors, prefix)
    _require("scalar_mean" in state and "scalar_inv" in state,
             "encoder normalization missing: " + prefix)
    mean, inverse = state["scalar_mean"].numpy(), state["scalar_inv"].numpy()
    _require(mean.shape == (10,) and inverse.shape == (10,)
             and np.isfinite(mean).all() and np.isfinite(inverse).all()
             and (inverse > 0).all(), "invalid encoder normalization: " + prefix)
    if "card_mlp.0.weight" in state:
        module = surrogate.DeepSetsEncoder(torch.nn, torch, mean, 1.0 / inverse).net
    else:
        module = attention.AttentionEncoder(torch, mean, 1.0 / inverse).net
    return _load(module, tensors, prefix)


class ArtifactTorch:
    def __init__(self, metadata, tensors, digest, device="cpu"):
        self.metadata, self.tensors, self.artifact_sha256 = metadata, tensors, digest
        self.device = torch.device(device)
        _require(all(isinstance(metadata.get(key), list)
                     and all(type(value) is int for value in metadata[key])
                     for key in ("hpClasses", "maxHpClasses")), "invalid artifact HP classes")
        self.classes = np.asarray(metadata["hpClasses"], dtype=np.int64)
        self.delta_values = np.asarray(metadata["maxHpClasses"], dtype=np.int64)
        self.domain = metadata["domain"]
        self.trained_groups = composed.TRAINED_GROUPS
        self.encounter_names = composed.native_rng.encounter_names()
        self.ready = False
        _require(self.classes.ndim == self.delta_values.ndim == 1
                 and len(self.classes) > 0 and len(self.delta_values) > 0
                 and np.all(self.classes[1:] > self.classes[:-1])
                 and np.all(self.delta_values[1:] > self.delta_values[:-1]),
                 "invalid artifact HP classes")
        # Constructors initialize temporary weights. Preserve the caller's CPU
        # RNG; every initialized value is replaced through strict state loading.
        with torch.random.fork_rng(devices=[]):
            self.encoders = {name: _encoder(tensors, name + ".encoder.")
                             for name in ("survival", "max_hp", "hp", "potion_encoder")}
            self.survival_head = _load(torch.nn.Linear(64, 1), tensors, "survival.survival.")
            self.max_hp_head = _load(torch.nn.Linear(64, len(self.delta_values)), tensors,
                                     "max_hp.max_hp_delta.")
            self.potion_net = _load(_PotionHead(len(self.delta_values)), tensors, "potion.")
            self.ritual_net = _load(_RitualHead(), tensors, "ritual.")
        # Validate escape/HP tensor shapes before constructing its tensor adapter.
        shapes = {"hp.delta_embedding.weight": (len(self.delta_values), 8),
                  "hp.hp.0.weight": (64, 73), "hp.hp.0.bias": (64,),
                  "hp.hp.2.weight": (len(self.classes), 64),
                  "hp.hp.2.bias": (len(self.classes),),
                  "escape.escape.weight": (1, 64), "escape.escape.bias": (1,)}
        _require(all(name in tensors and tensors[name].shape == shape
                     for name, shape in shapes.items()), "escape/HP tensor schema differs")
        _require("escape" in metadata.get("capabilities", {}), "artifact is not escape capable")
        self.escape = ctm_escape.TorchEscape(tensors, self.device)
        for module in (*self.encoders.values(), self.survival_head, self.max_hp_head,
                       self.potion_net, self.ritual_net):
            module.to(device=self.device, dtype=torch.float32).eval().requires_grad_(False)
        self.ready = True

    @torch.inference_mode()
    def encode_inputs(self, inputs):
        """Encode seven public input tensors with each component's own weights."""
        _require(len(inputs) == 7, "expected seven predictor input tensors")
        inputs = tuple(value.to(self.device) for value in inputs)
        encoded = {}
        for name, encoder in self.encoders.items():
            # Preserve the historical per-component Attention arithmetic, using
            # FP32 for both architectures. This restores the global MHA switch.
            with composed.attention_backend(torch, name != "hp"):
                encoded[name] = encoder(*inputs).float()
        z, potion_z = encoded["hp"], encoded["potion_encoder"]
        p_delta = torch.softmax(self.max_hp_head(encoded["max_hp"]), -1).double().cpu().numpy()
        p_win = torch.sigmoid(self.survival_head(encoded["survival"])).flatten().double().cpu().numpy()
        return dict(z=z, potion_z=potion_z, p_delta=p_delta, p_win=p_win,
                    potionZ=potion_z, pDelta=p_delta, pWin=p_win)

    def encode_predictor(self, predictor_input):
        arrays = composed.visible_arrays(predictor_input)
        inputs = surrogate._torch_inputs(arrays, np.asarray([0]), str(self.device), torch,
                                         trim_padding=True)
        return self.encode_inputs(inputs)

    def escape_probability(self, z):
        return self.escape.probability(z)

    def hp_probabilities(self, z, delta, pre, maximum, escaped):
        return self.escape.probabilities(z, delta, pre, maximum, escaped, self.classes)


def load_artifact(path: Path, expected_sha256: str, device="cpu") -> ArtifactTorch:
    """Require exact artifact custody before deserializing its tensor payload."""
    _require(isinstance(expected_sha256, str)
             and re.fullmatch(r"[0-9a-f]{64}", expected_sha256), "expected SHA256 is required")
    path = Path(path)
    digest = hashlib.sha256(path.read_bytes()).hexdigest()
    _require(digest == expected_sha256, "artifact SHA256 differs")
    metadata, tensors = ctm_escape.read_artifact(path)
    _require(metadata.get("schema") == "COMBAT_TRANSITION_RUNTIME_V2"
             and metadata.get("version") == 2, "unsupported artifact schema")
    _require(all(np.isfinite(value).all() for value in tensors.values()),
             "nonfinite artifact tensor")
    return ArtifactTorch(metadata, tensors, digest, device)
