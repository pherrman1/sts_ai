#!/usr/bin/env python3
"""Compare PR #298 W encoder/trajectory probabilities with its native export."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_potion_trajectory as trajectory
from tools import combat_transition_surrogate as base

CHECKPOINT_SHA = "71d88a71cf7579e1092c3b3c27e000538a6aafe35bbf5228c10c15fa0edd4ace"
TOLERANCE = 1e-4


def input_arrays(predictor: dict) -> dict:
    g = predictor["globals"]
    arrays = {
        "globals_continuous": np.asarray([[g[name] for name in base.CONTINUOUS_GLOBAL_FIELDS]], np.float32),
        "global_categories": np.asarray([[
            g["characterClass"], g["encounter"], g["roomClass"], g["lastRoom"]
        ]], np.int64),
    }
    cards = predictor["cards"]
    relics = predictor["relics"]
    arrays["cards"] = np.zeros((1, max(1, len(cards)), 4), np.float32)
    arrays["card_mask"] = np.zeros((1, max(1, len(cards))), bool)
    for i, token in enumerate(cards):
        arrays["cards"][0, i] = [token["cardId"], token["upgraded"], token["misc"], token["bottleBinding"] + 1]
        arrays["card_mask"][0, i] = True
    arrays["relics"] = np.zeros((1, max(1, len(relics)), 3), np.float32)
    arrays["relic_mask"] = np.zeros((1, max(1, len(relics))), bool)
    for i, token in enumerate(relics):
        arrays["relics"][0, i] = [token["relicId"], token["data"], token["orderIndex"]]
        arrays["relic_mask"][0, i] = True
    potions = sorted(predictor["potions"], key=lambda token: token["slot"])
    arrays["potions"] = np.asarray([[[token["slot"], token["potionId"]] for token in potions]], np.float32)
    return arrays


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--probe", type=Path, required=True)
    parser.add_argument("--artifact", type=Path, required=True)
    parser.add_argument("--checkpoint", type=Path, required=True)
    parser.add_argument("--fixtures", type=Path, required=True)
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    actual = hashlib.sha256(args.checkpoint.read_bytes()).hexdigest()
    if actual != CHECKPOINT_SHA:
        raise ValueError(f"required W checkpoint SHA mismatch: {actual}")
    bundle = torch.load(args.checkpoint, map_location="cpu", weights_only=False)
    if bundle.get("selectedEpoch") != 27:
        raise ValueError("W checkpoint selected epoch is not 27")
    encoder = base.DeepSetsEncoder(torch.nn, torch, np.zeros(10, np.float32), np.ones(10, np.float32)).net
    encoder.load_state_dict(bundle["encoderStateDict"], strict=True)
    decoder = trajectory.new_decoder(11)
    decoder.load_state_dict(bundle["decoderStateDict"], strict=True)
    encoder.eval(); decoder.eval(); torch.set_num_threads(1)

    rows = [json.loads(line) for line in args.fixtures.read_text().splitlines() if line.strip()]
    raw = subprocess.run([str(args.probe), "--potion-parity", str(args.artifact), str(args.fixtures)],
        check=True, text=True, capture_output=True)
    native_rows = [json.loads(line) for line in raw.stdout.splitlines() if line.strip()]
    if len(native_rows) != len(rows) or not rows:
        raise ValueError("native probe fixture count differs or is empty")

    max_z_error = 0.0
    max_probability_error = 0.0
    max_legal_mismatches = 0
    capacities, acts, boss_states, occupied_counts = set(), set(), set(), set()
    smoke_rows = brew_rows = 0
    for index, (row, native) in enumerate(zip(rows, native_rows)):
        predictor = row["predictorInput"]
        arrays = input_arrays(predictor)
        with torch.inference_mode():
            tensors = base._torch_inputs(arrays, np.asarray([0], np.int64), "cpu", torch, trim_padding=True)
            z = encoder(*tensors)
            delta = int(native["delta"])
            fraction = np.asarray([native["fraction"]], np.float32)
            inventory = np.asarray([[token["potionId"] for token in sorted(
                predictor["potions"], key=lambda token: token["slot"])]], np.int64)
            capacity = np.asarray([predictor["globals"]["potionCapacity"]], np.int64)
            # The native probe reports the exact simulator boss predicate.
            logp = trajectory.log_probabilities(decoder, z, inventory, capacity,
                np.asarray([delta], np.int64), fraction, np.asarray([native["boss"]], bool))
            probabilities = logp.exp().cpu().numpy()[0]
            expected_legal = np.isfinite(logp.cpu().numpy()[0])
        z_error = float(np.max(np.abs(z.cpu().numpy()[0] - np.asarray(native["z"], np.float32))))
        p_error = float(np.max(np.abs(probabilities - np.asarray(native["probabilities"], np.float64))))
        legal_mismatches = int(np.count_nonzero(expected_legal != np.asarray(native["legal"], bool)))
        max_z_error = max(max_z_error, z_error)
        max_probability_error = max(max_probability_error, p_error)
        max_legal_mismatches = max(max_legal_mismatches, legal_mismatches)
        if z_error > TOLERANCE or p_error > TOLERANCE or legal_mismatches:
            raise AssertionError(f"fixture {index} parity failed: z={z_error}, p={p_error}, legal={legal_mismatches}")
        globals_ = predictor["globals"]
        capacities.add(int(globals_["potionCapacity"]))
        acts.add(int(globals_["act"]))
        boss_states.add(bool(native["boss"]))
        occupied = sum(token["potionId"] > base.EMPTY_POTION_SLOT_ID for token in predictor["potions"])
        occupied_counts.add(occupied)
        smoke_rows += any(token["potionId"] == base._POTION_IDS["SMOKE_BOMB"] for token in predictor["potions"])
        brew_rows += any(token["potionId"] == base._POTION_IDS["ENTROPIC_BREW"] for token in predictor["potions"])

    if not {3, 5}.issubset(capacities) or not {1, 2, 3}.issubset(acts) or len(boss_states) != 2:
        raise ValueError("frozen fixtures do not cover capacities 3/5, acts 1/2/3, and boss/non-boss")
    if not any(count > 1 for count in occupied_counts) or not smoke_rows or not brew_rows:
        raise ValueError("frozen fixtures do not cover multiple occupied slots, Smoke, and Brew")
    report = {
        "checkpointSha256": actual, "selectedEpoch": 27, "fixtures": len(rows),
        "capacityValues": sorted(capacities), "acts": sorted(acts), "bossStates": sorted(boss_states),
        "occupiedPotionCounts": sorted(occupied_counts), "smokeFixtures": smoke_rows,
        "brewFixtures": brew_rows, "tolerance": TOLERANCE, "maxEncoderAbsoluteError": max_z_error,
        "maxProbabilityAbsoluteError": max_probability_error, "legalMaskMismatches": max_legal_mismatches,
        "pythonNativeParity": "PASS",
    }
    encoded = json.dumps(report, indent=2, sort_keys=True)
    if args.output:
        args.output.write_text(encoded + "\n")
    print(encoded)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
