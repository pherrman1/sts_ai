#!/usr/bin/env python3
"""Source-grouped cross-fitted calibration diagnostic; never qualification."""
from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys

import numpy as np
from scipy.optimize import minimize
from scipy.special import expit
import torch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from tools import combat_transition_survival_deepset_train as fit

RUNS = Path('/home/philippherrmann/sts_sweep/runs')
CHECKPOINT_SHA = '3689593db85974f13b6313c495e7fde4ec4b4fa7d87f3442c8604a47f5e0f05b'


def source_folds(sources, folds=5, seed=20260912):
    unique = np.unique(sources)
    if folds < 2 or len(unique) < folds:
        raise ValueError('not enough sources for cross-fitting')
    shuffled = np.random.default_rng(seed).permutation(unique)
    mapping = {int(source): index % folds for index, source in enumerate(shuffled)}
    return np.array([mapping[int(source)] for source in sources])


def fit_platt(logits, labels):
    logits = np.asarray(logits, dtype=np.float64)
    labels = np.asarray(labels, dtype=np.float64)
    if (logits.shape != labels.shape or logits.ndim != 1 or
            not np.isfinite(logits).all() or set(np.unique(labels)) != {0., 1.}):
        raise ValueError('finite logits and both binary classes required')
    design = np.column_stack((logits, np.ones(len(logits))))

    def objective(parameters):
        transformed = design @ parameters
        loss = np.mean(np.logaddexp(0., transformed) - labels * transformed)
        gradient = design.T @ (expit(transformed) - labels) / len(labels)
        return loss, gradient

    result = minimize(objective, np.array([1., 0.]), jac=True, method='BFGS',
                      options={'gtol': 1e-9, 'maxiter': 1000})
    if not result.success or not np.isfinite(result.x).all():
        raise ValueError(f'Platt fit did not converge: {result.message}')
    return result.x, dict(iterations=int(result.nit), gradientMax=float(np.abs(result.jac).max()))


def cross_fit(logits, labels, sources):
    assignments = source_folds(sources)
    output = np.full(len(logits), np.nan, dtype=np.float64)
    receipts = []
    for fold in range(5):
        held = assignments == fold
        training = ~held
        if set(sources[held]) & set(sources[training]):
            raise ValueError('source leakage')
        parameters, convergence = fit_platt(logits[training], labels[training])
        output[held] = parameters[0] * logits[held].astype(np.float64) + parameters[1]
        receipts.append(dict(fold=fold, slope=float(parameters[0]), intercept=float(parameters[1]),
                             fitRows=int(training.sum()), heldRows=int(held.sum()),
                             heldSources=np.unique(sources[held]).tolist(), convergence=convergence))
    if not np.isfinite(output).all():
        raise ValueError('incomplete cross-fitted predictions')
    return output, assignments, receipts


def run(output):
    if output.exists():
        raise ValueError('refusing output overwrite')
    args = argparse.Namespace(
        cache=RUNS / 'near-full-combat-support-20260914/potion-trajectory-v2',
        reference_component=RUNS / 'near-full-combat-support-20260914/full-union-survival-v1/component.pt',
        deepset_run=RUNS / 'shared-transition-deepset-distill-corrected-20260916',
        deepset_evidence=ROOT / 'docs/experiments/evidence/shared_transition_deepset_distill_correction_2026-09-16.json')
    checkpoint = RUNS / 'survival-specific-deepset-sweep-20260917-final/strongWd/selected.pt'
    if fit.screen.digest(checkpoint) != CHECKPOINT_SHA:
        raise ValueError('strong-WD checkpoint differs')
    torch.set_num_threads(4)
    torch.backends.cuda.matmul.allow_tf32 = False
    torch.backends.cudnn.allow_tf32 = False
    cache, arrays, population, provenance = fit.load_population(args)
    validation = np.flatnonzero(cache['split'] == 1)
    encoder, _ = fit.screen.load_candidate_encoder(args)
    candidate = fit.SurvivalNet(encoder)
    payload = torch.load(checkpoint, map_location='cpu', weights_only=False)
    candidate.load_state_dict(payload['stateDict'], strict=True)
    candidate.requires_grad_(False).cuda().eval()
    before = fit.screen.state_digest(candidate.state_dict())
    logits = fit.predict(candidate, arrays, cache, validation, 'cuda')
    reference_encoder, reference_head, _ = fit.screen.load_reference(args)
    reference = fit.SurvivalNet(reference_encoder)
    reference.head = reference_head
    reference.requires_grad_(False).cuda().eval()
    reference_logits = fit.predict(reference, arrays, cache, validation, 'cuda')
    raw = fit.compare(reference_logits, logits, cache, validation)
    if abs(raw['metrics']['DeepSets']['nll'] - .06293081492185593) > 1e-7:
        raise ValueError('strong-WD metric reproduction failed')
    if abs(raw['metrics']['Attention']['nll'] - fit.screen.REFERENCE_NLL) > 1e-7:
        raise ValueError('reference metric reproduction failed')
    calibrated, assignments, folds = cross_fit(logits, cache['win'][validation], cache['source'][validation])
    comparison = fit.compare(reference_logits, calibrated, cache, validation)
    comparison.pop('decision')
    if before != fit.screen.state_digest(candidate.state_dict()):
        raise ValueError('frozen model mutated')
    output.mkdir(parents=True)
    np.savez(output / 'validation_predictions.npz', rowIds=validation,
             source=cache['source'][validation], labels=cache['win'][validation],
             rawLogits=logits, calibratedLogits=calibrated, referenceLogits=reference_logits, fold=assignments)
    receipt = dict(schema='survival_platt_crossfit_v1', sourceSha=fit.screen.current_head(),
        scriptSha256=fit.screen.digest(Path(__file__)), checkpoint=str(checkpoint),
        checkpointSha256=CHECKPOINT_SHA, selectedEpoch=payload['selectedEpoch'],
        modelStateUnchanged=True, encoderTrainingRows=0, population=population, provenance=provenance,
        protocol=dict(folds=5, seed=20260912, grouping='source', objective='unweighted BCE',
                      optimizer='FP64 BFGS, gtol 1e-9, maxiter 1000', regularization='none',
                      affine='unconstrained slope and intercept', selection='fixed strong-WD epoch 20'),
        raw=raw, crossFitted=comparison, folds=folds, decision='DIAGNOSTIC_ONLY_NO_QUALIFICATION',
        caveat='Calibrator is cross-fitted, but model and arm were selected on this same VALIDATION set; not nested holdout.',
        testEncodedRows=0, testInferenceRows=0, testScoredRows=0,
        predictionsSha256=fit.screen.digest(output / 'validation_predictions.npz'))
    fit.screen.composed.base.json_dump(output / 'results.json', receipt)
    print(json.dumps(comparison, indent=2))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, required=True)
    run(parser.parse_args().output)
