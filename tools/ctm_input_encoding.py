"""CTM input encodings: the reference for the native runtime's global and card-misc features.

An artifact without metadata ``inputEncoding`` uses ``ctm_input_v1``, the encoding of every
shipped CTM. ``ctm_input_v2`` (``CombatTransitionRuntime::kInputEncodingV2``) changes three
inputs and nothing else:

* act is a category (``act - 1`` for acts 1..4) instead of a scalar, so an Act-4 row trains its
  own embedding instead of extrapolating a slope fitted on acts 1..3; floor stays the raw run
  floor (Act 4's 52..55 lies just past Act 3's 35..51);
* card misc is ``sign(m) * log(1 + |m|) / log(101)`` with ``|m| <= 10000`` instead of
  ``clip(m, -20, 20) / 20``, so a Ritual Dagger keeps counting after two kills;
* ``potionKeepValue`` (the output of another model) is not an input.

Prepared arrays keep the raw v1 layout (``globals_continuous`` in ``RAW_CONTINUOUS_FIELDS`` order,
``global_categories`` in ``RAW_CATEGORICAL_FIELDS`` order, raw misc in ``cards[..., 2]``); the
functions below derive each encoding's model inputs from them, in numpy or torch.
"""
from __future__ import annotations

import math

import numpy as np

V1 = "ctm_input_v1"
V2 = "ctm_input_v2"
ENCODINGS = (V1, V2)
RAW_CONTINUOUS_FIELDS = (
    "ascension", "act", "floor", "curHp", "maxHp", "gold", "potionCount", "potionCapacity",
    "potionKeepValue", "isBurningElite",
)
RAW_CATEGORICAL_FIELDS = ("characterClass", "encounter", "roomClass", "lastRoom")
V2_CONTINUOUS_FIELDS = (
    "ascension", "floor", "curHp", "maxHp", "gold", "potionCount", "potionCapacity",
    "isBurningElite",
)
ACT_CATEGORIES = 4
MISC_BOUND = 10000
_V2_FROM_RAW = [RAW_CONTINUOUS_FIELDS.index(name) for name in V2_CONTINUOUS_FIELDS]
_ACT = RAW_CONTINUOUS_FIELDS.index("act")
_LOG_101 = math.log1p(100.0)


def check(encoding: str) -> str:
    if encoding not in ENCODINGS:
        raise ValueError(f"unknown CTM input encoding {encoding!r}")
    return encoding


def continuous_fields(encoding: str) -> tuple[str, ...]:
    return RAW_CONTINUOUS_FIELDS if check(encoding) == V1 else V2_CONTINUOUS_FIELDS


def category_counts(encoding: str, raw_counts: dict[str, int]) -> list[int]:
    """Embedding sizes in model order: the raw categories, then act for v2."""
    counts = [int(raw_counts[field]) for field in RAW_CATEGORICAL_FIELDS]
    return counts if check(encoding) == V1 else counts + [ACT_CATEGORIES]


def runtime_metadata(encoding: str, raw_counts: dict[str, int]) -> dict:
    """The runtime header fields that declare an encoding (v1 declares no inputEncoding)."""
    out = {"continuousFields": list(continuous_fields(encoding)),
           "globalCategoryCounts": category_counts(encoding, raw_counts)}
    if encoding == V2:
        out["inputEncoding"] = V2
    return out


def _is_torch(x) -> bool:
    return type(x).__module__.split(".")[0] == "torch"


def globals_features(raw, raw_categories, encoding: str):
    """(continuous, categories) model inputs from raw globals; numpy or torch, last axis fields."""
    if check(encoding) == V1:
        return raw, raw_categories
    act = raw[..., _ACT]
    if _is_torch(raw):
        import torch
        if bool(((act < 1) | (act > ACT_CATEGORIES) | (act != act.round())).any()):
            raise ValueError("ctm_input_v2 needs integer acts in 1..4")
        continuous = raw[..., _V2_FROM_RAW]
        categories = torch.cat((raw_categories, (act - 1).to(raw_categories.dtype).unsqueeze(-1)), -1)
        return continuous, categories
    raw = np.asarray(raw); raw_categories = np.asarray(raw_categories)
    if np.any((act < 1) | (act > ACT_CATEGORIES) | (act != np.round(act))):
        raise ValueError("ctm_input_v2 needs integer acts in 1..4")
    continuous = raw[..., _V2_FROM_RAW]
    categories = np.concatenate(
        (raw_categories, (act - 1).astype(raw_categories.dtype)[..., None]), -1)
    return continuous, categories


def scalar_stats(raw_rows, encoding: str) -> tuple[np.ndarray, np.ndarray]:
    """Training mean/std of the continuous inputs (raw ``globals_continuous`` rows)."""
    raw_rows = np.asarray(raw_rows)
    continuous, _ = globals_features(raw_rows, np.zeros((len(raw_rows), 4), np.int64), encoding)
    return continuous.mean(0), continuous.std(0)


def misc_feature(misc, encoding: str):
    """Card misc feature from raw misc; numpy (float64 reference) or a float torch tensor."""
    if _is_torch(misc):
        if check(encoding) == V1:
            return misc.clamp(-20, 20) / 20
        key = misc.clamp(-MISC_BOUND, MISC_BOUND)
        return key.sign() * key.abs().log1p() / _LOG_101
    misc = np.asarray(misc, np.float64)
    if check(encoding) == V1:
        return np.clip(misc, -20, 20) / 20
    key = np.clip(misc, -MISC_BOUND, MISC_BOUND)
    return np.sign(key) * np.log1p(np.abs(key)) / _LOG_101
