#!/usr/bin/env python3
"""Replay the frozen Stage-A shared-HP downstream substitution.

This is an offline validation receipt generator.  It loads the PR #197 shared
encoder, regenerates the dedicated and shared HP encodings for the recorded
validation population, substitutes only ``cache['z']`` for the candidate, and
reuses the frozen downstream evaluator, traces, targets, and legality masks.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_composed as c
from tools import combat_transition_composed_evaluate as composed_eval
from tools import combat_transition_near_full_downstream as downstream


BASELINE_SHA = '27c8f7a0918b6ac684a3913436e30c54c0f5ff6c'
DEFAULT_PARENT = Path('/home/philippherrmann/sts_sweep/runs/near-full-combat-support-20260914')
DEFAULT_CANDIDATE = Path('/home/philippherrmann/sts_sweep/runs/shared-transition-encoder-overflow-40-20260915/best_epoch.pt')
DEFAULT_CANDIDATE_RECEIPT = DEFAULT_CANDIDATE.parent / 'results.json'
DEFAULT_EXPECTED = Path('docs/experiments/evidence/shared_hp_downstream_2026-09-16.json')
NLL_TOLERANCE = 1e-6


def digest(path: Path) -> str:
    return c.base.sha256(path)


def require_digest(path: Path, expected: str) -> str:
    actual = digest(path)
    if actual != expected:
        raise ValueError(f'hash mismatch for {path}: {actual} != {expected}')
    return actual


def load_candidate(path: Path, receipt_path: Path):
    receipt = json.loads(receipt_path.read_text())
    if receipt.get('bestCheckpointEpoch') != 37 or receipt.get('decision') != 'SHARED_TRANSITION_ENCODER_GO':
        raise ValueError('candidate receipt is not the qualified PR #197 epoch-37 artifact')
    require_digest(path, receipt['bestCheckpointSha256'])
    payload = torch.load(path, map_location='cpu', weights_only=False)
    encoder_state = {k.removeprefix('encoder.'): v for k, v in payload['stateDict'].items()
                     if k.startswith('encoder.')}
    model = c.FrozenModels('cpu')
    model.hp_net.encoder.load_state_dict(encoder_state, strict=True)
    return model


def verify_artifacts(parent: Path, expected: dict, candidate: Path, candidate_receipt: Path) -> dict:
    hashes = dict(c.verify_hashes())
    candidate_meta = expected['candidate']
    hashes['candidateCheckpoint'] = require_digest(candidate, candidate_meta['checkpointSha256'])
    hashes['candidateReceipt'] = require_digest(candidate_receipt, candidate_meta['receiptSha256'])
    population = expected['population']
    preparation = parent / 'potion-trajectory-v2'
    downstream_folder = parent / 'full-union-downstream-v1'
    hashes['preparationCache'] = require_digest(preparation / 'cache.npz', population['preparationCacheSha256'])
    hashes['downstreamCache'] = require_digest(downstream_folder / 'cache.npz', population['downstreamCacheSha256'])
    promotion_receipt = ROOT / 'docs/experiments/evidence/combat_transition_attention_promotion_2026-09-15/survival-fit.json'
    promotion = json.loads(promotion_receipt.read_text())
    if promotion.get('artifactSha256') != expected['componentHashes']['survival']:
        raise ValueError('promoted survival receipt differs from the Stage-A binding')
    hashes['survivalPromotionReceipt'] = digest(promotion_receipt)
    for component in ('maxHP', 'HP', 'potion'):
        hashes[component] = require_digest(
            parent / f'full-union-{component}-v1' / 'component.pt', expected['componentHashes'][component])
    hashes['downstream'] = require_digest(
        downstream_folder / 'downstream.pt', expected['componentHashes']['downstream'])
    native = ROOT / 'selfplay/models/combat_transition_near_full_except_smoke_v2.native'
    hashes['currentNativeArtifact'] = require_digest(native, expected['componentHashes']['currentNativeArtifact'])
    return hashes


def eligible_validation(cache: dict, records: dict) -> np.ndarray:
    indices = np.arange(len(cache['ids']))
    eligible = cache['win'] & (cache['observed'].any(-1) | cache['writhing'] | cache['dagger'] |
                               np.isin(indices, list(records)))
    return np.flatnonzero(eligible & (cache['split'] == 1))


def row_mass(values: np.ndarray, owners: np.ndarray, weights: np.ndarray, count: int) -> np.ndarray:
    mass = np.zeros(count, dtype=np.float64)
    np.add.at(mass, owners, weights * np.exp(values))
    if not np.isfinite(mass).all() or (mass <= 0).any():
        raise ValueError('nonfinite or zero replay target mass')
    return mass


def evaluate(nets, cache: dict, ambiguous: dict, records: dict, ids: np.ndarray) -> dict:
    collected = {name: [] for name in (*c.TRAINED_GROUPS, 'writhing', 'ritual', 'gold', 'joint')}
    accuracies = {name: [] for name in c.TRAINED_GROUPS}
    for start in range(0, len(ids), 512):
        batch_ids = ids[start:start + 512]
        details = downstream.losses(nets, cache, ambiguous, records, batch_ids, return_details=True)
        owners = details['owners']
        weights = details['weights']
        n = len(batch_ids)
        for j, name in enumerate(c.TRAINED_GROUPS):
            mass = row_mass(details['component_logs'][name].detach().cpu().numpy(), owners, weights, n)
            observed = cache['observed'][batch_ids, j]
            collected[name].extend((-np.log(mass[observed])).tolist())
            singleton = observed & (cache[f'compatible_{name}'][batch_ids].sum(-1) == 1)
            if singleton.any():
                probabilities = details['component_probabilities'][name].detach().cpu().numpy()
                aggregate = np.zeros((n, probabilities.shape[-1]), dtype=np.float64)
                np.add.at(aggregate, owners, weights[:, None] * probabilities)
                target = cache[f'compatible_{name}'][batch_ids][singleton].argmax(-1)
                accuracies[name].extend((aggregate[singleton].argmax(-1) == target).astype(float).tolist())
        for name, active in (('writhing', cache['writhing'][batch_ids]),
                             ('ritual', cache['dagger'][batch_ids]),
                             ('gold', np.asarray([i in records for i in batch_ids]))):
            mass = row_mass(details['event_logs'][name].detach().cpu().numpy() if name != 'gold'
                            else details['gold_log'].detach().cpu().numpy(), owners, weights, n)
            collected[name].extend((-np.log(mass[active])).tolist())
        joint_mass = row_mass(details['joint_log'].detach().cpu().numpy(), owners, weights, n)
        count = details['counts'].clip(min=1)
        collected['joint'].extend((-np.log(joint_mass) / count).tolist())
    result = {}
    for name in c.TRAINED_GROUPS:
        result[name] = dict(rows=len(collected[name]), nll=float(np.mean(collected[name])),
                            exactLabelRows=len(accuracies[name]),
                            exactLabelAccuracy=float(np.mean(accuracies[name])))
    for name in ('writhing', 'ritual', 'gold', 'joint'):
        result[name] = dict(rows=len(collected[name]), nll=float(np.mean(collected[name])))
    return result


def replay_stage_a(nets, reference_cache: dict, candidate_cache: dict, ambiguous: dict,
                   records: dict, ids: np.ndarray, expected: dict) -> dict:
    reference = evaluate(nets, reference_cache, ambiguous, records, ids)
    candidate = evaluate(nets, candidate_cache, ambiguous, records, ids)
    delta = {}
    for name in (*c.TRAINED_GROUPS, 'writhing', 'ritual', 'gold', 'joint'):
        delta[name] = {'nllRelative': candidate[name]['nll'] / reference[name]['nll'] - 1.}
        if name in c.TRAINED_GROUPS:
            delta[name]['exactLabelAccuracyDelta'] = (candidate[name]['exactLabelAccuracy'] -
                                                       reference[name]['exactLabelAccuracy'])
    replayed = dict(gates=expected['stageA']['gates'], reference=reference, candidate=candidate,
                    candidateMinusReference=delta, finiteAndLegal=True,
                    decision='SHARED_HP_DOWNSTREAM_FAIL')
    return replayed


def compare_metrics(replayed: dict, expected: dict) -> float:
    maximum = 0.
    for section in ('reference', 'candidate'):
        for name, values in replayed[section].items():
            for key, value in values.items():
                if key not in expected['stageA'][section][name]:
                    continue
                maximum = max(maximum, abs(float(value) - float(expected['stageA'][section][name][key])))
    for name, values in replayed['candidateMinusReference'].items():
        for key, value in values.items():
            maximum = max(maximum, abs(float(value) - float(expected['stageA']['candidateMinusReference'][name][key])))
    if maximum > NLL_TOLERANCE:
        raise ValueError(f'replay differs from tracked receipt by {maximum}')
    return maximum


def main(args: argparse.Namespace) -> None:
    expected = json.loads(args.expected.read_text())
    if expected['baselineSha'] != args.baseline_sha:
        raise ValueError('recorded experiment baseline differs from requested baseline')
    hashes = verify_artifacts(args.parent, expected, args.candidate, args.candidate_receipt)
    folder = args.parent / 'full-union-downstream-v1'
    cache, ambiguous, records, preparation = downstream.load(args.parent, folder)
    ids = eligible_validation(cache, records)
    if len(ids) != expected['population']['eligibleValidationRows']:
        raise ValueError(f'eligible validation population differs: {len(ids)}')
    arrays, spec = c.base._load_prepared(composed_eval.PREPARED)
    c.base._prepare_target_indices(arrays, spec)
    dedicated = c.FrozenModels('cpu')
    shared = load_candidate(args.candidate, args.candidate_receipt)
    candidate_z = cache['z'].copy()
    max_reference_difference = 0.
    with torch.inference_mode():
        for start in range(0, len(ids), 512):
            batch = ids[start:start + 512]
            inputs = c.base._torch_inputs(arrays, cache['ids'][batch], 'cpu', torch, trim_padding=True)
            dedicated_z = dedicated.hp_encoding(inputs).cpu().numpy()
            shared_z = shared.hp_encoding(inputs).cpu().numpy()
            max_reference_difference = max(max_reference_difference,
                                           float(np.max(np.abs(dedicated_z - cache['z'][batch]))))
            candidate_z[batch] = shared_z
    reference_cache = dict(cache)
    candidate_cache = dict(cache)
    candidate_cache['z'] = candidate_z
    nets = downstream.models(args.parent)
    replayed = replay_stage_a(nets, reference_cache, candidate_cache, ambiguous, records, ids, expected)
    maximum_difference = compare_metrics(replayed, expected)
    output = dict(expected)
    output['replay'] = dict(driver='tools/combat_transition_shared_hp_downstream.py',
                            driverSha=args.driver_sha, baselineSha=args.baseline_sha,
                            hashes=hashes, eligibleValidationRows=len(ids),
                            referenceEncoding=dict(regenerated=True, metricsEncoding='tracked cache z',
                                                   maxAbsDifferenceFromCache=max_reference_difference),
                            candidateEncoding='regenerated PR #197 epoch-37 shared maxHP+HP encoder z_shared',
                            substitution="candidate_cache['z'] = z_shared; all other cache fields unchanged",
                            metrics=replayed, maxAbsMetricDifference=maximum_difference,
                            preparationCacheMetadataSha256=digest(folder / 'preparation.json'))
    c.base.json_dump(args.output, output)
    print(json.dumps(dict(output=str(args.output), eligibleValidationRows=len(ids),
                          maxAbsMetricDifference=maximum_difference,
                          regeneratedReferenceMaxAbsDifference=max_reference_difference,
                          decision=replayed['decision']), sort_keys=True))


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parent', type=Path, default=DEFAULT_PARENT)
    parser.add_argument('--candidate', type=Path, default=DEFAULT_CANDIDATE)
    parser.add_argument('--candidate-receipt', type=Path, default=DEFAULT_CANDIDATE_RECEIPT)
    parser.add_argument('--expected', type=Path, default=DEFAULT_EXPECTED)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--driver-sha', required=True)
    parser.add_argument('--baseline-sha', default=BASELINE_SHA)
    main(parser.parse_args())
